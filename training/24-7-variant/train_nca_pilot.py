#!/usr/bin/env python3
"""NCA pre-pre-training pilot — valid A/B experiment (OLMo-1B, bf16 full FT).

Usage:
  python train_nca_pilot.py --arm nca     [--execute]   # Arm A: NCA tokens
  python train_nca_pilot.py --arm control [--execute]   # Arm B: C4 natural text

Dry-run by default (prints config + cost estimate). Pass --execute to train.

EXPERIMENT DESIGN
-----------------
Goal: validate arXiv:2603.10055's 1.6× convergence speedup + downstream reasoning
lift claim (GSM8K / HumanEval) at the 1B scale.

Arm A (nca):     continue-train OLMo-1B-hf on 100M NCA tokens
                 (Tejaskumar/Emergent-NCA-Sequences-5M, high-entropy rollouts).
Arm B (control): continue-train IDENTICAL stock OLMo-1B-hf on 100M C4 tokens
                 (allenai/c4 "en", streaming — matched token budget).

Everything else is identical: same base checkpoint, same hyperparameters,
same eval suite. The ONLY variable is the training data.

WHY C4 FOR THE CONTROL
-----------------------
The MIT paper (arXiv:2603.10055) uses C4 as its natural-language baseline.
Matching that choice makes our results directly comparable to the paper's
reported numbers rather than requiring a secondary translation step.

WHY BF16 FULL FT (no quantization, no LoRA)
--------------------------------------------
Pre-pre-training must update the actual model weights to instill the
reasoning prior the paper describes. LoRA-on-frozen or quantized-frozen
weights would defeat the experiment's purpose by preventing the NCA sequences
from reshaping the base representation. A 1B model is ~2 GB in bf16 — fits
a 24 GB RTX 4090 comfortably with gradient + optimizer state.

MEMORY BUDGET (RTX 4090, 24 GB)
  Weights (bf16):              ~2.0 GB
  Gradients (bf16):            ~2.0 GB
  AdamW optimizer (8-bit):     ~2.0 GB   ← 8-bit AdamW halves the 4 GB full-precision cost
  Activations + overhead:      ~6-8 GB   (gradient checkpointing reduces this)
  ─────────────────────────────────────
  Estimated peak:              ~12-14 GB  (well within 24 GB)

Base model: allenai/OLMo-1B-hf
  - Apache 2.0, fully open weights + training code
  - transformers-native (OlmoForCausalLM in transformers 4.40+)
  - Standard reproducibility baseline at 1B scale

Output:
  training/24-7-variant/output/olmo-1b-nca-pilot/   (Arm A)
  training/24-7-variant/output/olmo-1b-control/     (Arm B)
  training/24-7-variant/results/loss_curve_nca.jsonl
  training/24-7-variant/results/loss_curve_control.jsonl
  training/24-7-variant/results/RESULTS-NCA-pilot-<date>.md  (written after both arms eval)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATASET_REPO = "Tejaskumar/Emergent-NCA-Sequences-5M"
BASE_MODEL = "allenai/OLMo-1B-hf"
NCA_VOCAB_SIZE = 32           # symbolic tokens per NCA quantization
TARGET_TOKENS = 100_000_000   # 100M token subset (matched budget for both arms)
HIGH_ENTROPY_THRESHOLD = 0.6  # chaos score filter: keep rollouts above this percentile

HYPERPARAMS = {
    "batch_size": 4,              # fits RTX 4090 24 GB for 1B bf16 full FT
    "grad_accumulation": 8,       # effective batch = 32
    "learning_rate": 3e-4,
    "seq_length": 512,            # NCA rollout length (500 frames padded to 512)
    "warmup_ratio": 0.05,
    "weight_decay": 0.01,
    "eval_steps": 5000,
    "save_total_limit": 2,        # keep final + best
    "bf16": True,                 # RTX 4090 supports BF16
    "gradient_checkpointing": True,
    "optim": "adamw_bnb_8bit",    # 8-bit AdamW via bitsandbytes: halves optimizer memory
                                  # vs full-precision AdamW; no quantized weights needed
}

# Derived cost estimate (used for pre-flight check)
_steps_estimate = TARGET_TOKENS // (
    HYPERPARAMS["batch_size"] * HYPERPARAMS["seq_length"]
    * HYPERPARAMS["grad_accumulation"]
)
_hours_estimate = (_steps_estimate * HYPERPARAMS["batch_size"] * HYPERPARAMS["seq_length"]) / (
    4000 * 3600  # RTX 4090: ~4k NCA tokens/sec (empirical estimate from comparable setups)
)
COST_ESTIMATE_USD = _hours_estimate * 0.69  # $0.69/hr RTX 4090 (secure cloud)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", choices=["nca", "control"], required=True,
                   help="Which arm to train: 'nca' (NCA tokens) or 'control' (C4 natural text)")
    p.add_argument("--output-base", default="training/24-7-variant/output",
                   help="Base directory for checkpoints (arm name appended)")
    p.add_argument("--results-dir", default="training/24-7-variant/results",
                   help="Directory for loss curves and eval results")
    p.add_argument("--target-tokens", type=int, default=TARGET_TOKENS,
                   help="Token count for training subset (default: 100M)")
    p.add_argument("--entropy-threshold", type=float, default=HIGH_ENTROPY_THRESHOLD,
                   help="NCA entropy percentile filter (nca arm only; default: 0.6)")
    p.add_argument("--execute", action="store_true",
                   help="Actually run training (default: dry-run only)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Dataset loading — Arm A (NCA)
# ---------------------------------------------------------------------------

def load_nca_dataset(target_tokens: int, entropy_threshold: float):
    """Download NCA dataset subset from .npz shards, filter high-entropy rollouts.

    The dataset is NOT a HuggingFace-standard format; load_dataset() fails on it.
    Actual structure (inspected 2026-05-21):
      - nca_dataset/data/shard_NNNNN.npz        (20 shards, set 1)
      - nca_dataset_set2/data/shard_NNNNN.npz   (40 shards)
      - nca_dataset_set3/data/shard_NNNNN.npz   (40 shards)
    Each .npz has keys: frames (object array of rollouts), w (int16), h (int16)
      frames[i]: shape (500, H, W), dtype int8, values 0-31 (already quantized tokens)
    Metadata: dataset_labels_set{,2,3}.csv with columns including:
      shard_name, rollout_idx, entropy (Shannon entropy, range ~3.45-3.75)
    Note: entropy_threshold (default 0.6) is treated as a PERCENTILE cutoff (0-1).
    All rollouts have entropy well above 0.6 on the raw scale; the arg is reused
    as "keep rollouts above the Nth percentile of entropy across all metadata rows."
    E.g. entropy_threshold=0.6 → keep rollouts above the 60th-percentile entropy value.
    """
    import numpy as np
    import pandas as pd
    from huggingface_hub import hf_hub_download

    print(f"Loading {DATASET_REPO} via .npz shards …")
    print(f"  Filter: entropy above {entropy_threshold:.0%} percentile")
    print(f"  Target: {target_tokens:,} tokens")

    # --- 1. Load all CSV metadata and compute the entropy cutoff ---
    csv_frames = []
    for suffix, set_dir in [("", "nca_dataset"), ("2", "nca_dataset_set2"), ("3", "nca_dataset_set3")]:
        csv_name = f"dataset_labels_set{suffix}.csv"
        local = hf_hub_download(DATASET_REPO, csv_name, repo_type="dataset")
        df = pd.read_csv(local)
        df["_set_dir"] = set_dir
        csv_frames.append(df)
    meta = pd.concat(csv_frames, ignore_index=True)

    # entropy_threshold is a percentile (0-1); compute the raw entropy cutoff
    entropy_cutoff = float(meta["entropy"].quantile(entropy_threshold))
    high_entropy = meta[meta["entropy"] >= entropy_cutoff].copy()
    # Sort by entropy descending so we consume the highest-quality rollouts first
    high_entropy = high_entropy.sort_values("entropy", ascending=False).reset_index(drop=True)
    print(f"  Entropy cutoff (p{entropy_threshold:.0%}): {entropy_cutoff:.4f}  "
          f"({len(high_entropy):,} / {len(meta):,} rollouts pass)")

    # --- 2. Iterate rollouts across shards until token budget is met ---
    # Group by (set_dir, shard_name) to minimise redundant shard downloads
    sequences: list[list[int]] = []
    token_count = 0
    loaded_shards: dict[str, object] = {}  # cache open npz handles

    for _, row in high_entropy.iterrows():
        set_dir: str = row["_set_dir"]
        shard_name: str = row["shard_name"]
        rollout_idx: int = int(row["rollout_idx"])

        shard_key = f"{set_dir}/{shard_name}"
        if shard_key not in loaded_shards:
            hf_path = f"{set_dir}/data/{shard_name}"
            local_path = hf_hub_download(DATASET_REPO, hf_path, repo_type="dataset")
            loaded_shards[shard_key] = np.load(local_path, allow_pickle=True)

        data = loaded_shards[shard_key]
        frames = data["frames"][rollout_idx]  # shape: (500, H, W), dtype int8

        # Flatten the full rollout (all frames, all cells) into a 1D token sequence.
        # Each cell is already a quantized symbolic token in [0, 31].
        tokens = frames.flatten().astype(np.int64).tolist()

        sequences.append(tokens)
        token_count += len(tokens)
        if token_count >= target_tokens:
            break

    print(f"  Loaded {len(sequences):,} rollouts ({token_count:,} tokens)")
    return sequences, token_count


def build_hf_dataset_from_sequences(sequences: list[list[int]], seq_length: int):
    """Convert NCA token sequences to HuggingFace Dataset for Trainer."""
    from datasets import Dataset

    flat: list[int] = []
    for seq in sequences:
        flat.extend(seq)

    chunks = [flat[i:i + seq_length] for i in range(0, len(flat) - seq_length, seq_length)]
    # Labels = inputs (CLM objective; predict next NCA token)
    data = {
        "input_ids": [c for c in chunks],
        "labels": [c for c in chunks],
    }
    return Dataset.from_dict(data)


# ---------------------------------------------------------------------------
# Dataset loading — Arm B (C4 control)
# ---------------------------------------------------------------------------

def load_c4_dataset(tokenizer, target_tokens: int, seq_length: int):
    """Stream 100M tokens from allenai/c4 "en" — matched control arm.

    Why C4:
      The MIT paper (arXiv:2603.10055) uses C4 as its natural-language baseline.
      Matching that choice makes our A/B results directly comparable to the paper's
      reported numbers rather than requiring cross-dataset translation.

    Uses streaming=True to avoid downloading the full 300 GB dataset.
    Tokenizes on-the-fly and packs into seq_length chunks.
    """
    from datasets import load_dataset, Dataset

    print("Loading allenai/c4 'en' (streaming) for control arm …")
    print(f"  Target: {target_tokens:,} tokens  (seq_length={seq_length})")

    c4 = load_dataset("allenai/c4", "en", split="train", streaming=True)

    flat_ids: list[int] = []
    token_count = 0
    doc_count = 0

    for example in c4:
        text = example.get("text", "")
        if not text:
            continue
        ids = tokenizer.encode(text, add_special_tokens=False)
        flat_ids.extend(ids)
        token_count += len(ids)
        doc_count += 1
        if token_count >= target_tokens:
            break

    flat_ids = flat_ids[:target_tokens]
    print(f"  Consumed {doc_count:,} documents ({len(flat_ids):,} tokens)")

    chunks = [flat_ids[i:i + seq_length] for i in range(0, len(flat_ids) - seq_length, seq_length)]
    data = {
        "input_ids": [c for c in chunks],
        "labels": [c for c in chunks],
    }
    return Dataset.from_dict(data), len(flat_ids)


# ---------------------------------------------------------------------------
# Model setup — bf16 full fine-tuning (no quantization, no LoRA)
# ---------------------------------------------------------------------------

def load_model_and_tokenizer(arm: str):
    """Load OLMo-1B-hf in bf16 for full fine-tuning.

    No bitsandbytes quantization — the Trainer cannot update purely-quantized
    model weights (ValueError: You cannot perform fine-tuning on purely
    quantized models). A 1B model is ~2 GB in bf16 and fits a 24 GB RTX 4090
    with ample headroom for gradients and AdamW optimizer state.

    For the NCA arm: extend the embedding layer to cover the 32 NCA symbolic
    tokens if they exceed the existing vocabulary size.
    For the control arm: no vocab extension needed (C4 uses the native vocab).
    """
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    print(f"Loading base model: {BASE_MODEL}  (bf16, full FT, arm={arm})")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,   # bf16 full precision — no quantization
        device_map="auto",
        trust_remote_code=True,
    )

    if arm == "nca":
        # NCA uses a 32-token symbolic vocabulary ON TOP OF the existing vocab.
        # Extend the embedding layer to accommodate NCA token IDs if they exceed
        # the existing vocab size. This mirrors the approach in the MIT paper.
        current_vocab = len(tokenizer)
        nca_max_token = 31  # 0-indexed, 32 symbols
        if nca_max_token >= current_vocab:
            print(f"  Extending vocab from {current_vocab} → {nca_max_token + 1} for NCA symbols")
            tokenizer.add_tokens([f"<nca_{i}>" for i in range(NCA_VOCAB_SIZE)])
            model.resize_token_embeddings(len(tokenizer))

    param_count = sum(p.numel() for p in model.parameters()) / 1e9
    print(f"  Model parameters: {param_count:.2f}B  dtype: {next(model.parameters()).dtype}")
    return model, tokenizer


# ---------------------------------------------------------------------------
# Loss-curve logging callback
# ---------------------------------------------------------------------------

class LossCurveLogger:
    """Write per-step loss to a JSONL file for convergence comparison.

    The convergence-speedup claim from the MIT paper requires comparing
    Arm A vs Arm B loss curves. This callback records every logged step
    so we have the full curve, not just the final loss.
    """

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # Truncate on start (fresh run)
        self.log_path.write_text("")

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return
        if "loss" not in logs:
            return
        record = {
            "step": state.global_step,
            "loss": logs.get("loss"),
            "eval_loss": logs.get("eval_loss"),
            "epoch": logs.get("epoch"),
            "learning_rate": logs.get("learning_rate"),
        }
        with self.log_path.open("a") as f:
            f.write(json.dumps(record) + "\n")


def make_loss_callback(log_path: Path):
    """Return a transformers TrainerCallback that logs per-step loss."""
    from transformers import TrainerCallback

    logger = LossCurveLogger(log_path)

    class _Callback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            logger.on_log(args, state, control, logs=logs, **kwargs)

    return _Callback()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def run_training(args: argparse.Namespace) -> None:
    import torch
    from transformers import TrainingArguments, Trainer, DataCollatorForLanguageModeling

    arm = args.arm
    output = Path(args.output_base) / f"olmo-1b-{arm}-pilot"
    results_dir = Path(args.results_dir)
    output.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    loss_curve_path = results_dir / f"loss_curve_{arm}.jsonl"

    model, tokenizer = load_model_and_tokenizer(arm)

    if arm == "nca":
        sequences, actual_tokens = load_nca_dataset(args.target_tokens, args.entropy_threshold)
        dataset = build_hf_dataset_from_sequences(sequences, HYPERPARAMS["seq_length"])
    else:  # control
        dataset, actual_tokens = load_c4_dataset(tokenizer, args.target_tokens, HYPERPARAMS["seq_length"])

    val_size = max(1, int(0.02 * len(dataset)))
    dataset = dataset.train_test_split(test_size=val_size, seed=42)
    print(f"  Train examples: {len(dataset['train']):,}  Eval: {len(dataset['test']):,}")

    steps = max(1, actual_tokens // (
        HYPERPARAMS["batch_size"] * HYPERPARAMS["seq_length"]
        * HYPERPARAMS["grad_accumulation"]
    ))
    print(f"  Estimated steps: {steps:,}")
    print(f"  Loss curve → {loss_curve_path}")

    training_args = TrainingArguments(
        output_dir=str(output),
        num_train_epochs=1,
        per_device_train_batch_size=HYPERPARAMS["batch_size"],
        gradient_accumulation_steps=HYPERPARAMS["grad_accumulation"],
        learning_rate=HYPERPARAMS["learning_rate"],
        warmup_ratio=HYPERPARAMS["warmup_ratio"],
        weight_decay=HYPERPARAMS["weight_decay"],
        bf16=HYPERPARAMS["bf16"],
        gradient_checkpointing=HYPERPARAMS["gradient_checkpointing"],
        optim=HYPERPARAMS["optim"],          # adamw_bnb_8bit — halves optimizer memory
        evaluation_strategy="steps",
        eval_steps=HYPERPARAMS["eval_steps"],
        save_strategy="steps",
        save_steps=HYPERPARAMS["eval_steps"],
        save_total_limit=HYPERPARAMS["save_total_limit"],
        load_best_model_at_end=True,
        logging_steps=200,                   # frequent logging for smooth loss curve
        logging_dir=str(output / "logs"),
        report_to="none",                    # no wandb — offline pod
        dataloader_num_workers=2,
        seed=42,
    )

    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
    loss_callback = make_loss_callback(loss_curve_path)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["test"],
        data_collator=collator,
        callbacks=[loss_callback],
    )

    print(f"\nStarting training (arm={arm})…")
    trainer.train()
    trainer.save_model(str(output))
    tokenizer.save_pretrained(str(output))

    (output / "training_complete.flag").write_text(
        f"arm={arm}  tokens={actual_tokens:,}\n"
    )
    print(f"\nCheckpoint saved to {output}")
    print(f"Loss curve written to {loss_curve_path}")


# ---------------------------------------------------------------------------
# Eval — run both checkpoints side-by-side, write RESULTS markdown
# ---------------------------------------------------------------------------

def run_eval(results_dir: Path, output_base: Path) -> None:
    """Evaluate both arm checkpoints on GSM8K + HumanEval subsets.

    Loads each checkpoint, runs the same prompts, reports scores side-by-side.
    Writes results/RESULTS-NCA-pilot-<date>.md.
    """
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from datetime import datetime

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    results_path = results_dir / f"RESULTS-NCA-pilot-{date_str}.md"

    gsm_problems = [
        ("Janet's ducks lay 16 eggs per day. She eats 3 for breakfast and bakes 4 into "
         "muffins. She sells the remainder for $2 each. How much does she make per day?",
         "18"),
        ("A store has 3 times as many apples as oranges. If there are 48 pieces of fruit "
         "total, how many oranges are there?",
         "12"),
        ("Tom has 5 more marbles than twice the number Jerry has. Jerry has 8 marbles. "
         "How many marbles does Tom have?",
         "21"),
        ("A train travels 60 mph for 2.5 hours. How far does it travel?",
         "150"),
        ("If 4 workers take 6 days to build a wall, how many days would 3 workers take?",
         "8"),
    ]

    humaneval_problems = [
        ("def add(a, b):\n    \"\"\"Return the sum of a and b.\"\"\"\n", "return a + b"),
        ("def is_even(n):\n    \"\"\"Return True if n is even.\"\"\"\n", "return n % 2 == 0"),
        ("def factorial(n):\n    \"\"\"Return n!. Assume n >= 0.\"\"\"\n", "if n == 0: return 1\n    return n * factorial(n-1)"),
    ]

    arm_results: dict[str, dict] = {}

    for arm in ["nca", "control"]:
        checkpoint = output_base / f"olmo-1b-{arm}-pilot"
        if not checkpoint.exists():
            print(f"  Checkpoint not found for arm={arm}: {checkpoint} — skipping")
            arm_results[arm] = {"skipped": True, "reason": "checkpoint missing"}
            continue

        print(f"\nEvaluating arm={arm} from {checkpoint} …")
        tok = AutoTokenizer.from_pretrained(str(checkpoint), trust_remote_code=True)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            str(checkpoint),
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True,
        )
        model.eval()

        # GSM8K spot eval
        gsm_correct = 0
        gsm_outputs = []
        for problem, expected in gsm_problems:
            prompt = f"### Problem\n{problem}\n\n### Solution\nLet me work through this step by step.\n"
            inputs = tok(prompt, return_tensors="pt").to(model.device)
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=250, do_sample=False,
                                     pad_token_id=tok.pad_token_id)
            answer = tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
            correct = expected in answer
            if correct:
                gsm_correct += 1
            gsm_outputs.append({"problem": problem[:80], "expected": expected,
                                 "generated": answer[:200], "correct": correct})

        # HumanEval spot eval
        he_correct = 0
        he_outputs = []
        for stub, expected_fragment in humaneval_problems:
            prompt = f"Complete the following Python function:\n\n{stub}"
            inputs = tok(prompt, return_tensors="pt").to(model.device)
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=100, do_sample=False,
                                     pad_token_id=tok.pad_token_id)
            completion = tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
            # Simple fragment check — not full execution eval; indicative only
            correct = expected_fragment.replace(" ", "") in completion.replace(" ", "")
            if correct:
                he_correct += 1
            he_outputs.append({"stub": stub.strip(), "expected_fragment": expected_fragment,
                                "generated": completion[:200], "correct": correct})

        arm_results[arm] = {
            "gsm_score": gsm_correct / len(gsm_problems),
            "gsm_correct": gsm_correct,
            "gsm_total": len(gsm_problems),
            "he_score": he_correct / len(humaneval_problems),
            "he_correct": he_correct,
            "he_total": len(humaneval_problems),
            "gsm_outputs": gsm_outputs,
            "he_outputs": he_outputs,
        }

        # Save arm-level detail
        detail_path = results_dir / f"eval_detail_{arm}_{date_str}.jsonl"
        with detail_path.open("w") as f:
            for item in gsm_outputs + he_outputs:
                f.write(json.dumps(item) + "\n")
        print(f"  GSM8K: {gsm_correct}/{len(gsm_problems)}  HumanEval: {he_correct}/{len(humaneval_problems)}")
        print(f"  Detail → {detail_path}")

        del model  # free VRAM before loading next checkpoint

    # Load loss curves for convergence comparison
    def load_loss_curve(arm: str) -> list[dict]:
        p = results_dir / f"loss_curve_{arm}.jsonl"
        if not p.exists():
            return []
        lines = []
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return lines

    nca_curve = load_loss_curve("nca")
    ctrl_curve = load_loss_curve("control")

    def curve_summary(curve: list[dict]) -> str:
        if not curve:
            return "no data"
        losses = [r["loss"] for r in curve if r.get("loss") is not None]
        if not losses:
            return "no loss entries"
        return (f"steps={len(curve)}, "
                f"initial={losses[0]:.4f}, "
                f"final={losses[-1]:.4f}, "
                f"drop={losses[0]-losses[-1]:.4f}")

    def arm_score_line(arm: str) -> str:
        r = arm_results.get(arm, {})
        if r.get("skipped"):
            return f"checkpoint missing — {r.get('reason', '')}"
        return (f"GSM8K {r['gsm_correct']}/{r['gsm_total']} "
                f"({r['gsm_score']:.0%})  |  "
                f"HumanEval {r['he_correct']}/{r['he_total']} "
                f"({r['he_score']:.0%})")

    # Verdict heuristic
    nca_r = arm_results.get("nca", {})
    ctrl_r = arm_results.get("control", {})
    if nca_r.get("skipped") or ctrl_r.get("skipped"):
        verdict = "INCOMPLETE — one or both checkpoints missing."
    else:
        gsm_delta = nca_r["gsm_score"] - ctrl_r["gsm_score"]
        he_delta = nca_r["he_score"] - ctrl_r["he_score"]
        if gsm_delta > 0.1 or he_delta > 0.1:
            verdict = (f"NCA ARM OUTPERFORMS control on at least one benchmark "
                       f"(GSM8K delta={gsm_delta:+.0%}, HE delta={he_delta:+.0%}). "
                       "Supports the MIT paper's claim at 1B scale. "
                       "Consider Phase 0 for the Qwen2.5-3B variant.")
        elif gsm_delta > 0 and he_delta >= 0:
            verdict = (f"NCA arm shows modest positive trend "
                       f"(GSM8K delta={gsm_delta:+.0%}, HE delta={he_delta:+.0%}). "
                       "Inconclusive at this eval subset size — run lm-eval harness "
                       "on the full GSM8K test set before deciding on Phase 0.")
        elif gsm_delta < -0.1 and he_delta < -0.1:
            verdict = (f"Control arm outperforms NCA on both benchmarks "
                       f"(GSM8K delta={gsm_delta:+.0%}, HE delta={he_delta:+.0%}). "
                       "MIT claim did NOT reproduce at 1B scale with 100M tokens. "
                       "Skip Phase 0 for the Qwen2.5-3B variant.")
        else:
            verdict = (f"Mixed results (GSM8K delta={gsm_delta:+.0%}, HE delta={he_delta:+.0%}). "
                       "Recommend running full lm-eval harness before committing.")

    md = f"""# NCA Pre-Pre-Training Pilot — Results

**Date:** {date_str}
**Base model:** {BASE_MODEL}
**Token budget:** {TARGET_TOKENS:,} tokens per arm (matched)
**Hypothesis:** arXiv:2603.10055 claims 1.6× convergence speedup + GSM8K/HumanEval lift
from NCA pre-pre-training vs. matched-budget natural-text (C4) training.

---

## Arm A — NCA tokens (Tejaskumar/Emergent-NCA-Sequences-5M, high-entropy rollouts)

**Scores:** {arm_score_line("nca")}

**Loss curve:** {curve_summary(nca_curve)}

## Arm B — C4 natural text (allenai/c4 "en", matched 100M tokens)

**Scores:** {arm_score_line("control")}

**Loss curve:** {curve_summary(ctrl_curve)}

---

## Comparison

| Metric | Arm A (NCA) | Arm B (C4 control) | Delta (A − B) |
|--------|-------------|-------------------|---------------|
| GSM8K spot ({nca_r.get("gsm_total", "?")} problems) | {nca_r.get("gsm_correct", "—")}/{nca_r.get("gsm_total", "?")} | {ctrl_r.get("gsm_correct", "—")}/{ctrl_r.get("gsm_total", "?")} | {f'{nca_r.get("gsm_score",0)-ctrl_r.get("gsm_score",0):+.0%}' if not nca_r.get("skipped") and not ctrl_r.get("skipped") else "—"} |
| HumanEval spot ({nca_r.get("he_total", "?")} stubs) | {nca_r.get("he_correct", "—")}/{nca_r.get("he_total", "?")} | {ctrl_r.get("he_correct", "—")}/{ctrl_r.get("he_total", "?")} | {f'{nca_r.get("he_score",0)-ctrl_r.get("he_score",0):+.0%}' if not nca_r.get("skipped") and not ctrl_r.get("skipped") else "—"} |

**Convergence (loss curve):**
- NCA arm:     {curve_summary(nca_curve)}
- Control arm: {curve_summary(ctrl_curve)}

---

## Verdict

{verdict}

---

## Caveats

- Spot eval (5 GSM8K + 3 HumanEval problems) is indicative, not statistically rigorous.
  Delta of ±1 correct answer swings the score ±20% on GSM8K. Run the full lm-eval
  harness (`lm_eval --model hf --model_args pretrained=<checkpoint> --tasks gsm8k,humaneval`)
  for production-quality numbers before making a firm go/no-go call on Phase 0.
- 100M tokens is 2–5% of a typical pre-training budget. The paper's claimed lift
  manifests on *downstream* perplexity after subsequent natural-language training.
  These spot scores reflect the model immediately after NCA/C4 pre-pre-training,
  before any SFT — so lower absolute scores are expected; the *delta* is the signal.
- Loss curve convergence comparison requires both curves to be present. If one arm
  crashed mid-run, the convergence verdict is unreliable.

**Detail files:**
- `training/24-7-variant/results/eval_detail_nca_{date_str}.jsonl`
- `training/24-7-variant/results/eval_detail_control_{date_str}.jsonl`
- `training/24-7-variant/results/loss_curve_nca.jsonl`
- `training/24-7-variant/results/loss_curve_control.jsonl`
"""

    results_path.write_text(md)
    print(f"\nResults written to {results_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    steps = _steps_estimate
    hours = _hours_estimate

    arm_label = "NCA tokens (Arm A)" if args.arm == "nca" else "C4 natural text (Arm B — control)"

    print("=== NCA pre-pre-training pilot ===")
    print(f"  Arm:              {args.arm}  ({arm_label})")
    print(f"  Base model:       {BASE_MODEL}  [bf16, full FT — no quantization]")
    print(f"  Optimizer:        adamw_bnb_8bit  (8-bit AdamW, ~half optimizer memory)")
    print(f"  Token target:     {args.target_tokens:,}")
    if args.arm == "nca":
        print(f"  Dataset:          {DATASET_REPO}")
        print(f"  Entropy filter:   chaos > {args.entropy_threshold} percentile")
    else:
        print(f"  Dataset:          allenai/c4 'en' (streaming)")
    print(f"  Seq length:       {HYPERPARAMS['seq_length']}")
    print(f"  Batch size:       {HYPERPARAMS['batch_size']} × grad_accum {HYPERPARAMS['grad_accumulation']} = {HYPERPARAMS['batch_size'] * HYPERPARAMS['grad_accumulation']} effective")
    print(f"  Learning rate:    {HYPERPARAMS['learning_rate']}")
    print(f"  Estimated steps:  {steps:,}")
    print(f"  Estimated time:   {hours:.1f} hrs on RTX 4090")
    print(f"  Estimated cost:   ${COST_ESTIMATE_USD:.2f} (at $0.69/hr)")
    print(f"  Output:           {args.output_base}/olmo-1b-{args.arm}-pilot/")
    print()

    if COST_ESTIMATE_USD > 20:
        print(f"ERROR: Estimated cost ${COST_ESTIMATE_USD:.2f} exceeds $20 single-run ceiling.")
        print("Reduce --target-tokens or check hyperparams.")
        sys.exit(1)

    if not args.execute:
        print("Dry-run complete. Pass --execute to train.")
        return

    try:
        import torch
        assert torch.cuda.is_available(), "No CUDA GPU detected. RTX 4090 required."
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"GPU: {torch.cuda.get_device_name(0)} ({vram_gb:.1f} GB)")
        assert vram_gb >= 20, f"Need ≥20 GB VRAM for OLMo-1B bf16 full FT; got {vram_gb:.1f} GB"
    except ImportError:
        print("ERROR: torch not installed. Run setup first.")
        sys.exit(1)

    run_training(args)


if __name__ == "__main__":
    main()
