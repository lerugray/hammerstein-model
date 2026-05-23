#!/usr/bin/env python3
"""v0.2.1 continued-LoRA training with the hypotheses from the v0.2 verdict.

Changes vs train_v02_continued.py:
- LR 2e-4 (was 1e-4) - more aggressive continuation
- 3 epochs (was 2) - more learning on new pairs
- v0.2.1 oversample 3x (was 2x) - let new voice dominate
- Drop v3a synthetic retention sample entirely - v3a may be the source
  of the persistent fabrication patterns we still saw in v0.2
- Add 20 short-prompt-no-continuation pairs + 40 fabrication-discrimination
  pairs (via v0.2.1 additions)

Training mix:
- data/ray-stack-sft-v0.2.1-additions.jsonl (313 pairs, oversampled 3x = 939)
- data/ray-stack-sft-v0.1-combined.jsonl (541 pairs, full)
- No v3a synthetic. The v3a adapter is still loaded as the starting
  point; we just don't retrain on its synthetic data.

Estimated cost: ~$0.40-0.70 on RTX A5000 SECURE (~1.5-2hr).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
V3A_ADAPTER_HF = "lerugray/hammerstein-7b-lora"

LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

TRAIN_CONFIG = {
    "learning_rate": 2e-4,
    "per_device_train_batch_size": 2,
    "gradient_accumulation_steps": 4,
    "max_seq_length": 2048,
    "num_train_epochs": 3,
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

MIX_TARGETS = {
    "v021_additions_oversample": 3,
    "v01_ray_stack": "all",
    "v3a_synthetic_sample": 0,
}

EVAL_FRACTION = 0.10


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v021-additions",
                   default="data/ray-stack-sft-v0.2.1-additions.jsonl")
    p.add_argument("--v01-ray-stack",
                   default="data/ray-stack-sft-v0.1-combined.jsonl")
    p.add_argument("--v3a-adapter", default=V3A_ADAPTER_HF)
    p.add_argument("--output",
                   default="training/24-7-variant/output/qwen7b-v021-continued")
    p.add_argument("--execute", action="store_true")
    return p.parse_args()


def load_jsonl(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def format_example(row: dict) -> str:
    if "query" in row and "response" in row:
        return (f"<|im_start|>user\n{row['query']}<|im_end|>\n"
                f"<|im_start|>assistant\n{row['response']}<|im_end|>")
    if "messages" in row:
        return "\n".join(
            f"<|im_start|>{m.get('role','user')}\n{m.get('content','')}<|im_end|>"
            for m in row["messages"]
        )
    if "input" in row and "output" in row:
        return (f"<|im_start|>user\n{row['input']}<|im_end|>\n"
                f"<|im_start|>assistant\n{row['output']}<|im_end|>")
    return ""


def build_mix(args: argparse.Namespace) -> tuple[list[str], dict]:
    examples: list[str] = []
    counts: dict = {}

    v021_path = Path(args.v021_additions)
    if v021_path.exists():
        v021_rows = load_jsonl(args.v021_additions)
        for _ in range(MIX_TARGETS["v021_additions_oversample"]):
            for row in v021_rows:
                text = format_example(row)
                if text:
                    examples.append(text)
        counts["v021_additions"] = len(v021_rows) * MIX_TARGETS["v021_additions_oversample"]
    else:
        print(f"  WARN: v0.2.1 additions missing: {args.v021_additions}")
        counts["v021_additions"] = 0

    v01_path = Path(args.v01_ray_stack)
    if v01_path.exists():
        for row in load_jsonl(args.v01_ray_stack):
            text = format_example(row)
            if text:
                examples.append(text)
        counts["v01_ray_stack"] = sum(1 for _ in v01_path.read_text(encoding="utf-8").splitlines() if _.strip())
    else:
        counts["v01_ray_stack"] = 0

    counts["v3a_synthetic_sample"] = 0
    return examples, counts


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
        print("ERROR: no examples.")
        sys.exit(1)

    random.seed(42)
    random.shuffle(examples)
    n_eval = max(1, int(EVAL_FRACTION * total))
    eval_examples = examples[:n_eval]
    train_examples = examples[n_eval:]
    print(f"  Train: {len(train_examples):,}   Eval: {len(eval_examples):,}")

    train_ds = Dataset.from_dict({"text": train_examples})
    eval_ds = Dataset.from_dict({"text": eval_examples})

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

    print(f"\nLoading v3a adapter from {args.v3a_adapter} (trainable=True)...")
    model = PeftModel.from_pretrained(base, args.v3a_adapter, is_trainable=True)
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

    print("\nStarting continued training (v0.2.1)...")
    eff_batch = TRAIN_CONFIG["per_device_train_batch_size"] * TRAIN_CONFIG["gradient_accumulation_steps"]
    print(f"  Epochs: {TRAIN_CONFIG['num_train_epochs']}")
    print(f"  Effective batch: {eff_batch}")
    print(f"  Learning rate: {TRAIN_CONFIG['learning_rate']}")
    trainer.train()

    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"\nContinued adapter saved to {adapter_dir}")

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


def main() -> None:
    args = parse_args()

    print("=== Qwen2.5-7B v0.2.1 continued-LoRA SFT ===")
    print(f"  Base model:       {BASE_MODEL}")
    print(f"  Starting adapter: {args.v3a_adapter}")
    print(f"  v0.2.1 additions: {args.v021_additions} (x{MIX_TARGETS['v021_additions_oversample']} oversample)")
    print(f"  v0.1 Ray-stack:   {args.v01_ray_stack} (full)")
    print(f"  v3a synthetic:    NONE (dropped per v0.2 verdict)")
    print(f"  Epochs:           {TRAIN_CONFIG['num_train_epochs']}")
    print(f"  Learning rate:    {TRAIN_CONFIG['learning_rate']}")
    eff_batch = TRAIN_CONFIG["per_device_train_batch_size"] * TRAIN_CONFIG["gradient_accumulation_steps"]
    print(f"  Effective batch:  {eff_batch}")
    print()

    if not Path(args.v021_additions).exists():
        print(f"ERROR: v0.2.1 additions not found at {args.v021_additions}")
        sys.exit(1)

    if not args.execute:
        examples, counts = build_mix(args)
        total = len(examples)
        print("Mix counts (dry-run):")
        for k, v in counts.items():
            print(f"  {k:30s}  {v:,}")
        print(f"  {'TOTAL':30s}  {total:,}")
        steps = (total * TRAIN_CONFIG["num_train_epochs"]) // eff_batch
        sec_per_step = 4
        est_min = (steps * sec_per_step) / 60
        print(f"\n  Est. steps: {steps:,}")
        print(f"  Est. time:  {est_min:.0f} min")
        print("\nDry-run complete. Pass --execute to train.")
        return

    try:
        import torch
        assert torch.cuda.is_available()
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"\nGPU: {torch.cuda.get_device_name(0)} ({vram_gb:.1f} GB)")
        assert vram_gb >= 20
    except ImportError:
        sys.exit("torch not installed")

    run_training(args)


if __name__ == "__main__":
    main()
