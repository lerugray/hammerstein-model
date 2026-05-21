#!/usr/bin/env python3
"""Main SFT — Qwen3.6-3B-Instruct + Unsloth QLoRA for 24/7 homelab bot.

Defaults to dry-run (prints config + cost estimate). Pass --execute to actually train.

Training data (combined):
  1. Hammerstein synthetic (~5k examples) — v3a battle-tested data from tools/distill/
  2. Ray-stack SFT (~500-2000 examples) — curated Q/A from Ray's working substrate
     Path-configurable via --ray-stack-data; gracefully skips if missing.

Model: Qwen3.6-3B-Instruct (Apache 2.0, [LOCK])
Method: QLoRA rank-16 via Unsloth (~70% less VRAM, 2× faster than vanilla LoRA)

Output:
  training/24-7-variant/output/qwen3b-homelab-lora/lora-adapter/  ← LoRA weights
  (GGUF Q5_K_M conversion handled by run_main_sft_pod.sh after training)

NOT pushed to HuggingFace. Homelab-private.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config — mirrors v3a train.py conventions
# ---------------------------------------------------------------------------

BASE_MODEL = "unsloth/Qwen2.5-3B-Instruct-bnb-4bit"
# Note: Qwen3.6-3B is the [LOCK] target; using unsloth's 4-bit variant for pod training.
# If unsloth ships a native Qwen3.6-3B-Instruct-bnb-4bit, swap the string above.

LORA_CONFIG = {
    "r": 16,                     # rank [LOCK]
    "lora_alpha": 32,            # alpha [LOCK]
    "lora_dropout": 0.05,
    "bias": "none",
    "use_gradient_checkpointing": "unsloth",  # Unsloth's optimized checkpointing
    "random_state": 42,
    "use_rslora": False,
    # target_modules="all-linear" is Unsloth's ALL-modules default [LOCK]
}

TRAIN_CONFIG = {
    "learning_rate": 2e-4,           # [hyperparams recommendation]
    "per_device_train_batch_size": 2, # fits RTX 4090 at 3B + 4-bit + grad checkpt
    "gradient_accumulation_steps": 16,# effective batch = 32 [LOCK]
    "max_seq_length": 4096,           # [LOCK]
    "num_train_epochs": 3,            # [LOCK]
    "warmup_ratio": 0.05,
    "weight_decay": 0.01,
    "lr_scheduler_type": "cosine",
    "bf16": True,
    "logging_steps": 50,
    "save_strategy": "epoch",
    "save_total_limit": 2,
    "seed": 42,
}

# Eval split
EVAL_FRACTION = 0.10  # [LOCK: 10% eval split]

# Cost estimate (rough): 4-6 hrs at $0.34-0.69/hr RTX 4090
COST_LOW_USD = 4 * 0.34
COST_HIGH_USD = 6 * 0.69


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--hammerstein-data",
        default="tools/distill/data/synthetic-v3a-2026-05-09.jsonl",
        help="Path to Hammerstein synthetic JSONL (v3a data)",
    )
    p.add_argument(
        "--ray-stack-data",
        default="data/ray-stack-sft-2026-05-21.jsonl",
        help="Path to Ray-stack SFT JSONL (gracefully skipped if missing)",
    )
    p.add_argument(
        "--output",
        default="training/24-7-variant/output/qwen3b-homelab-lora",
        help="Output directory for LoRA adapter",
    )
    p.add_argument(
        "--execute",
        action="store_true",
        help="Actually run training (default: dry-run only)",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Dataset loading + formatting
# ---------------------------------------------------------------------------

def load_jsonl(path: str) -> list[dict]:
    """Load JSONL; raise with a clear message if file is missing."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Data file not found: {path}\n"
            f"  Check that the file exists and the path is correct.\n"
            f"  Ray-stack SFT can be set via --ray-stack-data."
        )
    rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    return rows


def format_example(row: dict) -> str:
    """Format a training example as a chat-style prompt for Qwen3.6.

    Handles two JSONL shapes:
      1. Hammerstein synthetic: {"query": str, "response": str, ...}
      2. Ray-stack SFT: {"messages": [{"role": str, "content": str}], ...}
         OR {"input": str, "output": str}  (simpler shape)
    """
    # Shape 1: Hammerstein synthetic (matches tools/distill/data/*.jsonl format)
    if "query" in row and "response" in row:
        return (
            f"<|im_start|>user\n{row['query']}<|im_end|>\n"
            f"<|im_start|>assistant\n{row['response']}<|im_end|>"
        )

    # Shape 2a: OpenAI-style messages array
    if "messages" in row:
        parts = []
        for msg in row["messages"]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        return "\n".join(parts)

    # Shape 2b: simple input/output
    if "input" in row and "output" in row:
        return (
            f"<|im_start|>user\n{row['input']}<|im_end|>\n"
            f"<|im_start|>assistant\n{row['output']}<|im_end|>"
        )

    # Fallback: skip with warning
    print(f"  WARN: Unrecognized row shape (keys: {list(row.keys())}) — skipping")
    return ""


def build_dataset(hammerstein_path: str, ray_stack_path: str) -> tuple[list[str], int, int]:
    """Load + combine both data sources. Returns (formatted_examples, n_ham, n_ray)."""
    examples = []

    # Hammerstein synthetic (required)
    ham_rows = load_jsonl(hammerstein_path)
    n_ham = 0
    for row in ham_rows:
        text = format_example(row)
        if text:
            examples.append(text)
            n_ham += 1

    # Ray-stack SFT (optional — graceful skip)
    n_ray = 0
    ray_path = Path(ray_stack_path)
    if ray_path.exists():
        ray_rows = load_jsonl(ray_stack_path)
        for row in ray_rows:
            text = format_example(row)
            if text:
                examples.append(text)
                n_ray += 1
    else:
        print(f"  Ray-stack SFT not found at {ray_stack_path} — skipping (Hammerstein only)")

    return examples, n_ham, n_ray


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def run_training(args: argparse.Namespace) -> None:
    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments
    from datasets import Dataset
    import torch

    output = Path(args.output)
    adapter_dir = output / "lora-adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)

    # Load + format data
    print("\nLoading training data…")
    examples, n_ham, n_ray = build_dataset(args.hammerstein_data, args.ray_stack_data)
    total = len(examples)
    print(f"  Hammerstein synthetic: {n_ham:,} examples")
    print(f"  Ray-stack SFT:        {n_ray:,} examples")
    print(f"  Combined:             {total:,} examples")

    if total == 0:
        print("ERROR: No training examples loaded. Check data paths.")
        sys.exit(1)

    # Eval split
    import random
    random.seed(42)
    random.shuffle(examples)
    n_eval = max(1, int(EVAL_FRACTION * total))
    eval_examples = examples[:n_eval]
    train_examples = examples[n_eval:]
    print(f"  Train: {len(train_examples):,}  Eval: {len(eval_examples):,}")

    train_ds = Dataset.from_dict({"text": train_examples})
    eval_ds = Dataset.from_dict({"text": eval_examples})

    # Load model via Unsloth
    print(f"\nLoading {BASE_MODEL} via Unsloth…")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=TRAIN_CONFIG["max_seq_length"],
        dtype=torch.bfloat16,
        load_in_4bit=True,
    )

    # Apply LoRA
    print("Applying LoRA (rank=16, alpha=32, target_modules=all-linear)…")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_CONFIG["r"],
        lora_alpha=LORA_CONFIG["lora_alpha"],
        lora_dropout=LORA_CONFIG["lora_dropout"],
        bias=LORA_CONFIG["bias"],
        use_gradient_checkpointing=LORA_CONFIG["use_gradient_checkpointing"],
        random_state=LORA_CONFIG["random_state"],
        use_rslora=LORA_CONFIG["use_rslora"],
        target_modules="all-linear",  # [LOCK: ALL modules]
    )

    training_args = TrainingArguments(
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
        save_total_limit=TRAIN_CONFIG["save_total_limit"],
        evaluation_strategy="epoch",
        load_best_model_at_end=True,
        report_to="none",               # no wandb
        seed=TRAIN_CONFIG["seed"],
        dataloader_num_workers=2,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        dataset_text_field="text",
        max_seq_length=TRAIN_CONFIG["max_seq_length"],
        dataset_num_proc=2,
        args=training_args,
    )

    print("\nStarting training…")
    print(f"  Epochs: {TRAIN_CONFIG['num_train_epochs']}")
    print(f"  Effective batch: {TRAIN_CONFIG['per_device_train_batch_size'] * TRAIN_CONFIG['gradient_accumulation_steps']}")
    trainer.train()

    # Save LoRA adapter
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"\nLoRA adapter saved to {adapter_dir}")
    print("Next: run_main_sft_pod.sh will merge + convert to GGUF Q5_K_M")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    print("=== Qwen3.6-3B Main SFT (dry-run) ===")
    print(f"  Base model:       {BASE_MODEL}")
    print(f"  LoRA rank/alpha:  {LORA_CONFIG['r']}/{LORA_CONFIG['lora_alpha']}")
    print(f"  Target modules:   all-linear [LOCK]")
    print(f"  Epochs:           {TRAIN_CONFIG['num_train_epochs']}")
    print(f"  Batch size:       {TRAIN_CONFIG['per_device_train_batch_size']} × grad_accum {TRAIN_CONFIG['gradient_accumulation_steps']} = {TRAIN_CONFIG['per_device_train_batch_size'] * TRAIN_CONFIG['gradient_accumulation_steps']} effective")
    print(f"  Learning rate:    {TRAIN_CONFIG['learning_rate']}")
    print(f"  Max seq length:   {TRAIN_CONFIG['max_seq_length']}")
    print(f"  Eval split:       {int(EVAL_FRACTION * 100)}%")
    print(f"  Hammerstein data: {args.hammerstein_data}")
    print(f"  Ray-stack data:   {args.ray_stack_data}")
    print(f"  Output:           {args.output}")
    print(f"  Est. cost:        ${COST_LOW_USD:.2f}–${COST_HIGH_USD:.2f} (4-6 hrs @ $0.34-0.69/hr)")
    print()

    if COST_HIGH_USD > 20:
        print(f"ERROR: High-end cost estimate ${COST_HIGH_USD:.2f} exceeds $20 ceiling. Check config.")
        sys.exit(1)

    # Validate Hammerstein data exists (required)
    ham_path = Path(args.hammerstein_data)
    if not ham_path.exists():
        print(f"ERROR: Hammerstein synthetic data not found: {args.hammerstein_data}")
        print("  This file should be committed in the repo (v3a training run).")
        sys.exit(1)

    ham_count = sum(1 for line in ham_path.read_text().splitlines() if line.strip())
    print(f"  Hammerstein data: {ham_count:,} examples ✓")

    ray_path = Path(args.ray_stack_data)
    if ray_path.exists():
        ray_count = sum(1 for line in ray_path.read_text().splitlines() if line.strip())
        print(f"  Ray-stack data:   {ray_count:,} examples ✓")
    else:
        print(f"  Ray-stack data:   NOT FOUND (will train Hammerstein-only)")

    if not args.execute:
        print("\nDry-run complete. Pass --execute to train.")
        return

    try:
        import torch
        assert torch.cuda.is_available(), "No CUDA GPU detected. RTX 4090 required."
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"\nGPU: {torch.cuda.get_device_name(0)} ({vram_gb:.1f} GB)")
        assert vram_gb >= 20, f"Need ≥20 GB VRAM for Qwen3B QLoRA; got {vram_gb:.1f} GB"
    except ImportError:
        print("ERROR: torch not installed. Run setup first.")
        sys.exit(1)

    run_training(args)


if __name__ == "__main__":
    main()
