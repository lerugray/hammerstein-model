#!/usr/bin/env python3
"""v0.2 continued-LoRA training — Qwen2.5-7B-Instruct + v3a adapter +
   v0.2 additions (seeds + audit-trigger discrimination + restyled).

This is the v2 retrain of hammerstein-7b for the homelab. It picks up
from the existing v3a LoRA adapter (the model currently deployed as
`hammerstein-7b` via Ollama) and continues training on the v0.2 data
mix to fix v1's documented failure modes:

  1. auditify-casual: casual prompts get audit register
  2. fabricate-GSD: ambiguous prompts get fabricated manual refs
  3. refuse-then-fabricate: historical questions get refused then
     mid-answer fabricated specifics
  4. sentence-continuation: model continues user's prompt before pivoting

Plus the v2 voice spec: no engagement-pushing on casual responses.

Method
------
1. Load Qwen2.5-7B-Instruct base in 4-bit NF4 (vanilla peft + BitsAndBytes,
   NOT Unsloth — pod torch 2.4.1 + Unsloth incompatibility per the 24/7
   variant SFT run notes).
2. Load the v3a LoRA adapter from HuggingFace
   (`lerugray/hammerstein-7b-lora`) ON TOP of the base, set trainable.
3. Train on the v0.2 mix:
     - data/ray-stack-sft-v0.2-additions.jsonl (~300 pairs from seeds +
       discrimination + restyled, oversampled 2x → ~600 effective)
     - data/ray-stack-sft-v0.1-combined.jsonl (~541 pairs, Ray-stack
       familiarity layer; not seen by v3a adapter)
     - tools/distill/data/synthetic-v3a-2026-05-09.jsonl (sample 500 from
       the 1708 pairs to retain framework discipline)
4. 2 epochs, lr=1e-4 (lower than v3a's 2e-4 — we're continuing, not
   starting from scratch).
5. Save continued adapter + merge + GGUF conversion via the pod shell
   script.

Dry-run default. Pass --execute to fire.

Base model: Qwen/Qwen2.5-7B-Instruct (Apache 2.0)
Starting adapter: lerugray/hammerstein-7b-lora (v3a, public, MIT)
Output: training/24-7-variant/output/qwen7b-v02-continued/lora-adapter
NOT pushed to HuggingFace — homelab-private.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
V3A_ADAPTER_HF = "lerugray/hammerstein-7b-lora"

# Mirror v3a's LoRA target modules + rank to keep the continued adapter
# compatible with the existing weights.
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

# v3a used rank=32 alpha=32. We continue with the same shape — peft loads
# the adapter at that shape automatically. No new LoraConfig needed if
# we're continuing the existing adapter.

# Training: lower LR than v3a (2e-4) because we're continuing, not starting.
TRAIN_CONFIG = {
    "learning_rate": 1e-4,
    "per_device_train_batch_size": 2,
    "gradient_accumulation_steps": 4,    # eff batch = 8 (matches v3a)
    "max_seq_length": 2048,              # matches v3a
    "num_train_epochs": 2,               # tighter than v3a's 3 — continuing
    "warmup_ratio": 0.05,
    "weight_decay": 0.01,
    "lr_scheduler_type": "cosine",
    "bf16": True,
    "logging_steps": 20,
    "save_strategy": "epoch",
    "eval_strategy": "epoch",
    "save_total_limit": 2,
    "load_best_model_at_end": True,
    "seed": 42,
}

# Training mix targets (oversample applied at load time)
MIX_TARGETS = {
    "v02_additions_oversample": 2,   # ~300 pairs × 2 = 600
    "v01_ray_stack": "all",          # ~541 pairs, all
    "v3a_synthetic_sample": 500,     # 500 of 1708 to retain framework
}

EVAL_FRACTION = 0.10

# Cost estimate: RTX 4090 @ $0.34-0.69/hr × ~1-1.5 hrs
COST_LOW_USD = 1.0 * 0.34
COST_HIGH_USD = 1.5 * 0.69


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--v02-additions",
        default="data/ray-stack-sft-v0.2-additions.jsonl",
        help="Path to v0.2 additions JSONL (seeds + discrimination + restyled)",
    )
    p.add_argument(
        "--v01-ray-stack",
        default="data/ray-stack-sft-v0.1-combined.jsonl",
        help="Path to v0.1 Ray-stack combined JSONL (541 pairs)",
    )
    p.add_argument(
        "--v3a-synthetic",
        default="tools/distill/data/synthetic-v3a-2026-05-09.jsonl",
        help="Path to v3a synthetic (1708 pairs; we sample 500 for retention)",
    )
    p.add_argument(
        "--v3a-adapter",
        default=V3A_ADAPTER_HF,
        help="HF repo or local path of v3a LoRA adapter to continue from",
    )
    p.add_argument(
        "--output",
        default="training/24-7-variant/output/qwen7b-v02-continued",
        help="Output directory for continued LoRA adapter + merged model",
    )
    p.add_argument(
        "--execute",
        action="store_true",
        help="Actually train (default: dry-run with config + estimate)",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Dataset loading + formatting
# ---------------------------------------------------------------------------

def load_jsonl(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def format_example(row: dict) -> str:
    """Format a row into Qwen2.5 chat-template string.
    Handles three shapes: query/response (Hammerstein synthetic),
    messages (chat format — v0.1/v0.2), input/output (simpler shape)."""
    if "query" in row and "response" in row:
        return (
            f"<|im_start|>user\n{row['query']}<|im_end|>\n"
            f"<|im_start|>assistant\n{row['response']}<|im_end|>"
        )
    if "messages" in row:
        parts = []
        for msg in row["messages"]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        return "\n".join(parts)
    if "input" in row and "output" in row:
        return (
            f"<|im_start|>user\n{row['input']}<|im_end|>\n"
            f"<|im_start|>assistant\n{row['output']}<|im_end|>"
        )
    return ""


def build_mix(args: argparse.Namespace) -> tuple[list[str], dict]:
    """Build training mix per MIX_TARGETS. Returns (formatted_examples, counts)."""
    examples: list[str] = []
    counts: dict = {}

    # 1. v0.2 additions, oversampled
    v02_path = Path(args.v02_additions)
    if v02_path.exists():
        v02_rows = load_jsonl(args.v02_additions)
        os_mult = MIX_TARGETS["v02_additions_oversample"]
        for _ in range(os_mult):
            for row in v02_rows:
                text = format_example(row)
                if text:
                    examples.append(text)
        counts["v02_additions"] = len(v02_rows) * os_mult
    else:
        print(f"  WARN: v0.2 additions not found at {args.v02_additions}")
        counts["v02_additions"] = 0

    # 2. v0.1 Ray-stack (all)
    v01_path = Path(args.v01_ray_stack)
    if v01_path.exists():
        v01_rows = load_jsonl(args.v01_ray_stack)
        for row in v01_rows:
            text = format_example(row)
            if text:
                examples.append(text)
        counts["v01_ray_stack"] = len(v01_rows)
    else:
        print(f"  WARN: v0.1 Ray-stack not found at {args.v01_ray_stack}")
        counts["v01_ray_stack"] = 0

    # 3. v3a synthetic sample
    v3a_path = Path(args.v3a_synthetic)
    if v3a_path.exists():
        v3a_rows = load_jsonl(args.v3a_synthetic)
        sample_n = min(MIX_TARGETS["v3a_synthetic_sample"], len(v3a_rows))
        random.seed(42)
        sampled = random.sample(v3a_rows, sample_n)
        for row in sampled:
            text = format_example(row)
            if text:
                examples.append(text)
        counts["v3a_synthetic_sample"] = sample_n
    else:
        print(f"  WARN: v3a synthetic not found at {args.v3a_synthetic}")
        counts["v3a_synthetic_sample"] = 0

    return examples, counts


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def run_training(args: argparse.Namespace) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel
    from trl import SFTTrainer, SFTConfig
    from datasets import Dataset

    output = Path(args.output)
    adapter_dir = output / "lora-adapter"
    merged_dir = output / "merged"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    merged_dir.mkdir(parents=True, exist_ok=True)

    print("\nBuilding training mix...")
    examples, counts = build_mix(args)
    total = len(examples)
    for k, v in counts.items():
        print(f"  {k:30s}  {v:,}")
    print(f"  {'TOTAL':30s}  {total:,}")

    if total == 0:
        print("ERROR: No training examples assembled. Check data paths.")
        sys.exit(1)

    random.seed(42)
    random.shuffle(examples)
    n_eval = max(1, int(EVAL_FRACTION * total))
    eval_examples = examples[:n_eval]
    train_examples = examples[n_eval:]
    print(f"  Train: {len(train_examples):,}   Eval: {len(eval_examples):,}")

    train_ds = Dataset.from_dict({"text": train_examples})
    eval_ds = Dataset.from_dict({"text": eval_examples})

    # 4-bit NF4 base load
    print(f"\nLoading base {BASE_MODEL} (4-bit NF4)...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    base.config.use_cache = False

    # Continue from v3a — load adapter ON TOP, trainable
    print(f"\nLoading v3a adapter from {args.v3a_adapter} (trainable=True)...")
    model = PeftModel.from_pretrained(
        base,
        args.v3a_adapter,
        is_trainable=True,
    )
    model.enable_input_require_grads()
    model.gradient_checkpointing_enable()
    model.print_trainable_parameters()

    sft_config = SFTConfig(
        output_dir=str(output / "trainer-checkpoints"),
        num_train_epochs=TRAIN_CONFIG["num_train_epochs"],
        per_device_train_batch_size=TRAIN_CONFIG["per_device_train_batch_size"],
        gradient_accumulation_steps=TRAIN_CONFIG["gradient_accumulation_steps"],
        learning_rate=TRAIN_CONFIG["learning_rate"],
        warmup_ratio=TRAIN_CONFIG["warmup_ratio"],
        weight_decay=TRAIN_CONFIG["weight_decay"],
        lr_scheduler_type=TRAIN_CONFIG["lr_scheduler_type"],
        bf16=TRAIN_CONFIG["bf16"],
        logging_steps=TRAIN_CONFIG["logging_steps"],
        save_strategy=TRAIN_CONFIG["save_strategy"],
        eval_strategy=TRAIN_CONFIG["eval_strategy"],
        save_total_limit=TRAIN_CONFIG["save_total_limit"],
        load_best_model_at_end=TRAIN_CONFIG["load_best_model_at_end"],
        report_to="none",
        seed=TRAIN_CONFIG["seed"],
        dataloader_num_workers=2,
        max_seq_length=TRAIN_CONFIG["max_seq_length"],
        dataset_text_field="text",
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        args=sft_config,
    )

    print("\nStarting continued training...")
    eff_batch = TRAIN_CONFIG["per_device_train_batch_size"] * TRAIN_CONFIG["gradient_accumulation_steps"]
    print(f"  Epochs: {TRAIN_CONFIG['num_train_epochs']}")
    print(f"  Effective batch: {eff_batch}")
    print(f"  Learning rate: {TRAIN_CONFIG['learning_rate']}")
    trainer.train()

    # Save continued adapter
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"\nContinued adapter saved to {adapter_dir}")

    # Merge into base for GGUF conversion
    print("\nMerging adapter into base (full precision)...")
    base_full = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    merged = PeftModel.from_pretrained(base_full, str(adapter_dir))
    merged = merged.merge_and_unload()
    merged.save_pretrained(str(merged_dir))
    tokenizer.save_pretrained(str(merged_dir))
    print(f"Merged model saved to {merged_dir}")
    print("Next: pod shell script handles GGUF Q5_K_M conversion.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    print("=== Qwen2.5-7B v0.2 continued-LoRA SFT ===")
    print(f"  Base model:       {BASE_MODEL}")
    print(f"  Starting adapter: {args.v3a_adapter}")
    print(f"  v0.2 additions:   {args.v02_additions} (×{MIX_TARGETS['v02_additions_oversample']} oversample)")
    print(f"  v0.1 Ray-stack:   {args.v01_ray_stack} (full)")
    print(f"  v3a synthetic:    {args.v3a_synthetic} (sample {MIX_TARGETS['v3a_synthetic_sample']})")
    print(f"  Epochs:           {TRAIN_CONFIG['num_train_epochs']}")
    print(f"  Learning rate:    {TRAIN_CONFIG['learning_rate']}")
    eff_batch = TRAIN_CONFIG["per_device_train_batch_size"] * TRAIN_CONFIG["gradient_accumulation_steps"]
    print(f"  Effective batch:  {eff_batch}")
    print(f"  Max seq:          {TRAIN_CONFIG['max_seq_length']}")
    print(f"  Output:           {args.output}")
    print(f"  Est. cost:        ${COST_LOW_USD:.2f}-${COST_HIGH_USD:.2f} on RTX 4090 (~1-1.5 hr)")
    print()

    # Validate data presence (warn rather than block for v3a since the path
    # may differ on pod vs local)
    if not Path(args.v02_additions).exists():
        print(f"ERROR: v0.2 additions not found at {args.v02_additions}")
        print("  Run scripts/v2_concat_sanitize.py first to assemble this file.")
        sys.exit(1)

    if not args.execute:
        # Build mix dry-run to surface counts
        examples, counts = build_mix(args)
        total = len(examples)
        print("Mix counts (dry-run):")
        for k, v in counts.items():
            print(f"  {k:30s}  {v:,}")
        print(f"  {'TOTAL':30s}  {total:,}")
        steps = (total * TRAIN_CONFIG["num_train_epochs"]) // eff_batch
        sec_per_step = 5  # RTX 4090 7B QLoRA continued, vanilla peft
        est_min = (steps * sec_per_step) / 60
        print(f"\n  Est. steps: {steps:,}")
        print(f"  Est. time:  {est_min:.0f} min")
        print("\nDry-run complete. Pass --execute to actually train.")
        return

    # Real-run guards
    try:
        import torch
        assert torch.cuda.is_available(), "No CUDA GPU detected"
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"\nGPU: {torch.cuda.get_device_name(0)} ({vram_gb:.1f} GB)")
        assert vram_gb >= 20, f"Need >=20 GB VRAM for 7B QLoRA continued; got {vram_gb:.1f}"
    except ImportError:
        print("ERROR: torch not installed.")
        sys.exit(1)

    run_training(args)


if __name__ == "__main__":
    main()
