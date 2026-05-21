#!/usr/bin/env python3
"""NCA pre-pre-training pilot — OLMo-1B on Emergent-NCA-Sequences-5M.

Defaults to dry-run (prints config + cost estimate). Pass --execute to actually train.

Goal: validate arXiv:2603.10055's 1.6x speedup claim on a small sandbox model.
Dataset: Tejaskumar/Emergent-NCA-Sequences-5M
  - 5M rollouts of NCA spatiotemporal sequences
  - 32-token symbolic vocabulary (quantized via MiniBatch KMeans)
  - Filtered by high-entropy rollouts (chaos > 0.6 per CSV metadata)
  - 100M token subset used here

Base model: allenai/OLMo-1B (Apache 2.0, fully open; standard reproducibility baseline)
Note: Unsloth OLMo support is incomplete as of 2026-05 — using vanilla HF Trainer
      with bitsandbytes 4-bit for memory efficiency.

Output: training/24-7-variant/output/olmo-1b-nca-pilot/
  - Full checkpoint (not LoRA — this is pre-training, not SFT)
  - Training loss curve
  - training_complete.flag on success
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
BASE_MODEL = "allenai/OLMo-1B"
NCA_VOCAB_SIZE = 32           # symbolic tokens per NCA quantization
TARGET_TOKENS = 100_000_000   # 100M token subset
HIGH_ENTROPY_THRESHOLD = 0.6  # chaos score filter from dataset CSV metadata

HYPERPARAMS = {
    "batch_size": 4,           # fits RTX 4090 24GB for 1B model
    "grad_accumulation": 8,    # effective batch = 32
    "learning_rate": 3e-4,
    "seq_length": 512,         # NCA rollout length matches dataset (500 frames; pad to 512)
    "warmup_ratio": 0.05,
    "weight_decay": 0.01,
    "eval_steps": 5000,
    "save_total_limit": 2,     # keep final + best
    "bf16": True,              # RTX 4090 supports BF16
    "gradient_checkpointing": True,
}

# Derived
_steps_estimate = TARGET_TOKENS // (
    HYPERPARAMS["batch_size"] * HYPERPARAMS["seq_length"]
    * HYPERPARAMS["grad_accumulation"]
)
# RTX 4090: ~4k NCA tokens/sec for 1B model (empirical estimate from comparable setups)
_hours_estimate = (_steps_estimate * HYPERPARAMS["batch_size"] * HYPERPARAMS["seq_length"]) / (
    4000 * 3600
)
COST_ESTIMATE_USD = _hours_estimate * 0.69  # $0.69/hr RTX 4090 (secure cloud)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default="training/24-7-variant/output/olmo-1b-nca-pilot",
                   help="Output directory for checkpoint")
    p.add_argument("--target-tokens", type=int, default=TARGET_TOKENS,
                   help="Token count for training subset (default: 100M)")
    p.add_argument("--entropy-threshold", type=float, default=HIGH_ENTROPY_THRESHOLD,
                   help="Minimum chaos score for NCA rollout filtering")
    p.add_argument("--execute", action="store_true",
                   help="Actually run training (default: dry-run only)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Dataset loading + entropy filter
# ---------------------------------------------------------------------------

def load_nca_dataset(target_tokens: int, entropy_threshold: float):
    """Download NCA dataset subset, filter high-entropy rollouts, tokenize."""
    from datasets import load_dataset
    import numpy as np

    print(f"Loading {DATASET_REPO} …")
    print(f"  Filter: chaos_entropy > {entropy_threshold}")
    print(f"  Target: {target_tokens:,} tokens")

    # The dataset stores rollout sequences as compressed .npz shards.
    # The HuggingFace dataset card exposes them via the 'train' split with
    # fields: sequence_tokens (List[int], len=500), chaos_entropy (float),
    # spatial_complexity (float), activity_level (float).
    # If the dataset card changes structure, check sample_usage.py in the HF repo.
    ds = load_dataset(
        DATASET_REPO,
        split="train",
        streaming=True,  # stream to avoid downloading 565 MB upfront
        trust_remote_code=True,
    )

    # Filter: high-entropy rollouts benefit reasoning tasks (per NCA eval doc)
    ds_filtered = ds.filter(lambda x: x.get("chaos_entropy", 0.0) > entropy_threshold)

    # Collect sequences up to target token budget
    sequences = []
    token_count = 0
    for example in ds_filtered:
        tokens = example.get("sequence_tokens") or example.get("tokens") or []
        if not tokens:
            # Fallback: try to parse the raw array field
            raw = example.get("sequence") or example.get("data")
            if raw is not None:
                tokens = list(np.array(raw).flatten().astype(int))
        sequences.append(tokens)
        token_count += len(tokens)
        if token_count >= target_tokens:
            break

    print(f"  Loaded {len(sequences):,} rollouts ({token_count:,} tokens)")
    return sequences, token_count


def build_hf_dataset(sequences: list[list[int]], seq_length: int):
    """Convert token sequences to HuggingFace Dataset for Trainer."""
    from datasets import Dataset
    import numpy as np

    # Concatenate all sequences into a flat token stream, then chunk into seq_length
    flat = []
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
# Model setup
# ---------------------------------------------------------------------------

def load_model_and_tokenizer():
    """Load OLMo-1B with bitsandbytes 4-bit (memory-efficient, no Unsloth needed)."""
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

    print(f"Loading base model: {BASE_MODEL}")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    # OLMo's tokenizer may not have a pad token — use eos
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    # NCA uses a 32-token symbolic vocabulary ON TOP OF the existing vocab.
    # We extend the embedding layer to accommodate NCA token IDs if they exceed
    # the existing vocab size. This mirrors the approach in the MIT paper.
    current_vocab = len(tokenizer)
    nca_max_token = 31  # 0-indexed, 32 symbols
    if nca_max_token >= current_vocab:
        print(f"  Extending vocab from {current_vocab} → {nca_max_token + 1} for NCA symbols")
        tokenizer.add_tokens([f"<nca_{i}>" for i in range(NCA_VOCAB_SIZE)])
        model.resize_token_embeddings(len(tokenizer))

    return model, tokenizer


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def run_training(args: argparse.Namespace) -> None:
    import torch
    from transformers import TrainingArguments, Trainer, DataCollatorForLanguageModeling

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    sequences, actual_tokens = load_nca_dataset(args.target_tokens, args.entropy_threshold)
    dataset = build_hf_dataset(sequences, HYPERPARAMS["seq_length"])
    val_size = max(1, int(0.02 * len(dataset)))  # 2% eval split
    dataset = dataset.train_test_split(test_size=val_size, seed=42)

    print(f"  Train examples: {len(dataset['train']):,}  Eval: {len(dataset['test']):,}")

    model, tokenizer = load_model_and_tokenizer()

    steps = max(1, actual_tokens // (
        HYPERPARAMS["batch_size"] * HYPERPARAMS["seq_length"]
        * HYPERPARAMS["grad_accumulation"]
    ))
    print(f"  Estimated steps: {steps:,}")

    training_args = TrainingArguments(
        output_dir=str(output),
        num_train_epochs=1,             # pre-pre-training: one pass over the subset
        per_device_train_batch_size=HYPERPARAMS["batch_size"],
        gradient_accumulation_steps=HYPERPARAMS["grad_accumulation"],
        learning_rate=HYPERPARAMS["learning_rate"],
        warmup_ratio=HYPERPARAMS["warmup_ratio"],
        weight_decay=HYPERPARAMS["weight_decay"],
        bf16=HYPERPARAMS["bf16"],
        gradient_checkpointing=HYPERPARAMS["gradient_checkpointing"],
        evaluation_strategy="steps",
        eval_steps=HYPERPARAMS["eval_steps"],
        save_strategy="steps",
        save_steps=HYPERPARAMS["eval_steps"],
        save_total_limit=HYPERPARAMS["save_total_limit"],
        load_best_model_at_end=True,
        logging_steps=500,
        logging_dir=str(output / "logs"),
        report_to="none",               # no wandb — offline pod
        dataloader_num_workers=2,
        seed=42,
    )

    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["test"],
        data_collator=collator,
    )

    print("\nStarting training…")
    trainer.train()
    trainer.save_model(str(output))
    tokenizer.save_pretrained(str(output))

    # Write completion flag (shell script checks this for idempotency)
    (output / "training_complete.flag").write_text(
        f"NCA pilot complete. Tokens trained: {actual_tokens:,}\n"
    )
    print(f"\nCheckpoint saved to {output}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    steps = _steps_estimate
    hours = _hours_estimate

    print("=== NCA pre-pre-training pilot (dry-run) ===")
    print(f"  Base model:       {BASE_MODEL}")
    print(f"  Dataset:          {DATASET_REPO}")
    print(f"  Token target:     {args.target_tokens:,}")
    print(f"  Entropy filter:   chaos > {args.entropy_threshold}")
    print(f"  Seq length:       {HYPERPARAMS['seq_length']}")
    print(f"  Batch size:       {HYPERPARAMS['batch_size']} × grad_accum {HYPERPARAMS['grad_accumulation']} = {HYPERPARAMS['batch_size'] * HYPERPARAMS['grad_accumulation']} effective")
    print(f"  Learning rate:    {HYPERPARAMS['learning_rate']}")
    print(f"  Estimated steps:  {steps:,}")
    print(f"  Estimated time:   {hours:.1f} hrs on RTX 4090")
    print(f"  Estimated cost:   ${COST_ESTIMATE_USD:.2f} (at $0.69/hr)")
    print(f"  Output:           {args.output}")
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
        assert vram_gb >= 20, f"Need ≥20 GB VRAM for OLMo-1B 4-bit; got {vram_gb:.1f} GB"
    except ImportError:
        print("ERROR: torch not installed. Run setup first.")
        sys.exit(1)

    run_training(args)


if __name__ == "__main__":
    main()
