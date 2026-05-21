#!/usr/bin/env python3
"""Main SFT — Qwen2.5-3B-Instruct vanilla peft QLoRA for 24/7 homelab bot.

Base model fallback: Qwen/Qwen2.5-3B-Instruct
  Qwen3.6-3B-Instruct and Qwen3-3B-Instruct do not exist on HuggingFace
  as of 2026-05-21 (verified via HfApi). Using Qwen2.5-3B-Instruct per the
  scoping doc's fallback ordering.

Defaults to dry-run (prints config + cost estimate). Pass --execute to actually train.

Training data (combined):
  1. Hammerstein synthetic (~5k examples) — v3a battle-tested data from tools/distill/
  2. Ray-stack SFT (~202 pairs) — curated Q/A from Ray's working substrate
     Path-configurable via --ray-stack-data; gracefully skips if missing.

Model: Qwen/Qwen2.5-3B-Instruct (Apache 2.0)
Method: vanilla peft QLoRA — BitsAndBytesConfig 4-bit NF4 + LoraConfig r=16
        (Unsloth dropped: incompatible with pod torch 2.4.1+cu124)

Output:
  training/24-7-variant/output/qwen3b-homelab-lora/lora-adapter/  <- LoRA weights
  training/24-7-variant/output/qwen3b-homelab-lora/merged/        <- merged HF model
  (GGUF Q5_K_M conversion handled by run_main_sft_pod.sh after training)

NOT pushed to HuggingFace. Homelab-private.

trl version assumption: trl>=0.12.0,<0.17.0 (SFTConfig/SFTTrainer stable API).
  SFTTrainer moved dataset_text_field + max_seq_length into SFTConfig in trl>=0.8.
  This script targets that interface.
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

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
# Scoping doc [LOCK] was Qwen3.6-3B-Instruct. Fallback applied:
#   Qwen/Qwen3.6-3B-Instruct  — does not exist on HF (verified 2026-05-21)
#   Qwen/Qwen3-3B-Instruct    — does not exist on HF (verified 2026-05-21)
#   Qwen/Qwen2.5-3B-Instruct  — EXISTS, Apache 2.0, same family [LOCK updated]

LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

LORA_CONFIG = {
    "r": 16,           # rank [LOCK]
    "lora_alpha": 32,  # alpha [LOCK]
    "lora_dropout": 0.05,
    "bias": "none",
    "task_type": "CAUSAL_LM",
}

TRAIN_CONFIG = {
    "learning_rate": 2e-4,
    "per_device_train_batch_size": 2,    # fits RTX 4090 at 3B + 4-bit + grad checkpt
    "gradient_accumulation_steps": 16,  # effective batch = 32 [LOCK]
    "max_seq_length": 4096,              # [LOCK]
    "num_train_epochs": 3,               # [LOCK]
    "warmup_ratio": 0.03,
    "weight_decay": 0.01,
    "lr_scheduler_type": "cosine",
    "bf16": True,
    "logging_steps": 50,
    "save_strategy": "epoch",
    "eval_strategy": "epoch",
    "save_total_limit": 2,
    "load_best_model_at_end": True,
    "seed": 42,
}

EVAL_FRACTION = 0.10  # [LOCK: 10% eval split]

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
        help="Output directory for LoRA adapter + merged model",
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
    """Format a training example as a chat-style string for Qwen2.5.

    Handles two JSONL shapes:
      1. Hammerstein synthetic: {"query": str, "response": str, ...}
      2. Ray-stack SFT: {"messages": [{"role": str, "content": str}], ...}
         OR {"input": str, "output": str}  (simpler shape)
    """
    # Shape 1: Hammerstein synthetic
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

    # Fallback
    print(f"  WARN: Unrecognized row shape (keys: {list(row.keys())}) — skipping")
    return ""


def build_dataset(hammerstein_path: str, ray_stack_path: str) -> tuple[list[str], int, int]:
    """Load + combine both data sources. Returns (formatted_examples, n_ham, n_ray)."""
    examples: list[str] = []

    # Hammerstein synthetic (required)
    ham_rows = load_jsonl(hammerstein_path)
    n_ham = 0
    for row in ham_rows:
        text = format_example(row)
        if text:
            examples.append(text)
            n_ham += 1

    # Ray-stack SFT (optional)
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
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )
    from peft import LoraConfig, get_peft_model
    from trl import SFTTrainer, SFTConfig
    from datasets import Dataset

    output = Path(args.output)
    adapter_dir = output / "lora-adapter"
    merged_dir = output / "merged"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    merged_dir.mkdir(parents=True, exist_ok=True)

    # Load + format data
    print("\nLoading training data...")
    examples, n_ham, n_ray = build_dataset(args.hammerstein_data, args.ray_stack_data)
    total = len(examples)
    print(f"  Hammerstein synthetic: {n_ham:,} examples")
    print(f"  Ray-stack SFT:        {n_ray:,} examples")
    print(f"  Combined:             {total:,} examples")

    if total == 0:
        print("ERROR: No training examples loaded. Check data paths.")
        sys.exit(1)

    # Eval split
    random.seed(42)
    random.shuffle(examples)
    n_eval = max(1, int(EVAL_FRACTION * total))
    eval_examples = examples[:n_eval]
    train_examples = examples[n_eval:]
    print(f"  Train: {len(train_examples):,}  Eval: {len(eval_examples):,}")

    train_ds = Dataset.from_dict({"text": train_examples})
    eval_ds = Dataset.from_dict({"text": eval_examples})

    # 4-bit NF4 quantization config (vanilla BitsAndBytes)
    print(f"\nLoading {BASE_MODEL} with 4-bit NF4 quantization...")
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

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    model.config.use_cache = False  # required for gradient checkpointing

    # Apply LoRA via peft
    print(f"Applying LoRA (r={LORA_CONFIG['r']}, alpha={LORA_CONFIG['lora_alpha']}, "
          f"target_modules={LORA_TARGET_MODULES})...")
    lora_config = LoraConfig(
        r=LORA_CONFIG["r"],
        lora_alpha=LORA_CONFIG["lora_alpha"],
        lora_dropout=LORA_CONFIG["lora_dropout"],
        bias=LORA_CONFIG["bias"],
        task_type=LORA_CONFIG["task_type"],
        target_modules=LORA_TARGET_MODULES,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Enable gradient checkpointing (vanilla approach post-get_peft_model)
    model.enable_input_require_grads()
    model.gradient_checkpointing_enable()

    # SFTConfig — trl>=0.8 moved dataset_text_field + max_seq_length here
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
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        args=sft_config,
    )

    print("\nStarting training...")
    print(f"  Epochs: {TRAIN_CONFIG['num_train_epochs']}")
    eff_batch = TRAIN_CONFIG["per_device_train_batch_size"] * TRAIN_CONFIG["gradient_accumulation_steps"]
    print(f"  Effective batch: {eff_batch}")
    trainer.train()

    # Save LoRA adapter
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"\nLoRA adapter saved to {adapter_dir}")

    # Merge adapter into base model and save
    print("\nMerging LoRA adapter into base model (full precision)...")
    from peft import PeftModel

    # Reload base in bf16 (no quantization) for clean merge
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    merged_model = PeftModel.from_pretrained(base_model, str(adapter_dir))
    merged_model = merged_model.merge_and_unload()
    merged_model.save_pretrained(str(merged_dir))
    tokenizer.save_pretrained(str(merged_dir))
    print(f"Merged model saved to {merged_dir}")
    print("Next: run_main_sft_pod.sh will convert merged model to GGUF Q5_K_M")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    print("=== Qwen2.5-3B Main SFT (vanilla peft QLoRA) ===")
    print(f"  Base model:       {BASE_MODEL}")
    print(f"  Note:             Qwen3.6-3B-Instruct not on HF; using Qwen2.5-3B-Instruct")
    print(f"  LoRA rank/alpha:  {LORA_CONFIG['r']}/{LORA_CONFIG['lora_alpha']}")
    print(f"  Target modules:   {LORA_TARGET_MODULES}")
    print(f"  Epochs:           {TRAIN_CONFIG['num_train_epochs']}")
    eff_batch = TRAIN_CONFIG["per_device_train_batch_size"] * TRAIN_CONFIG["gradient_accumulation_steps"]
    print(f"  Batch size:       {TRAIN_CONFIG['per_device_train_batch_size']} x grad_accum "
          f"{TRAIN_CONFIG['gradient_accumulation_steps']} = {eff_batch} effective")
    print(f"  Learning rate:    {TRAIN_CONFIG['learning_rate']}")
    print(f"  Max seq length:   {TRAIN_CONFIG['max_seq_length']}")
    print(f"  Eval split:       {int(EVAL_FRACTION * 100)}%")
    print(f"  Hammerstein data: {args.hammerstein_data}")
    print(f"  Ray-stack data:   {args.ray_stack_data}")
    print(f"  Output:           {args.output}")
    print(f"  Est. cost:        ${COST_LOW_USD:.2f}-${COST_HIGH_USD:.2f} (4-6 hrs @ $0.34-0.69/hr)")
    print()

    if COST_HIGH_USD > 20:
        print(f"ERROR: High-end cost estimate ${COST_HIGH_USD:.2f} exceeds $20 ceiling.")
        sys.exit(1)

    # Validate Hammerstein data (required)
    ham_path = Path(args.hammerstein_data)
    if not ham_path.exists():
        print(f"ERROR: Hammerstein synthetic data not found: {args.hammerstein_data}")
        print("  This file should be committed in the repo (v3a training run).")
        sys.exit(1)

    ham_count = sum(1 for line in ham_path.read_text().splitlines() if line.strip())
    print(f"  Hammerstein data: {ham_count:,} examples OK")

    ray_path = Path(args.ray_stack_data)
    if ray_path.exists():
        ray_count = sum(1 for line in ray_path.read_text().splitlines() if line.strip())
        print(f"  Ray-stack data:   {ray_count:,} examples OK")
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
        assert vram_gb >= 20, f"Need >=20 GB VRAM for Qwen3B QLoRA; got {vram_gb:.1f} GB"
    except ImportError:
        print("ERROR: torch not installed. Run setup first.")
        sys.exit(1)

    run_training(args)


if __name__ == "__main__":
    main()
