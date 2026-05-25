#!/usr/bin/env python3
"""v0.2.7.2 continued-LoRA training — iteration on v0.2.7.1.

Per docs/handoffs/v0.2.7.2-from-privategs-orchestrator-2026-05-25.md:
  Primary fix: tool-use XML-in-content format
  Secondary fix: pure-question extraction discrimination

Training mix (target ~3,690 examples):
- 933 v0.2.7.2 additions x 3 baseline = 2,799
- 541 v0.1 ray-stack x 1               = 541
- 250 v3a synthetic sample             = 250
- TOTAL                                = 3,590

Continued from v0.2.7.1 adapter (preserves the self-state fix).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"

BASE_ADAPTER_PATH_DEFAULT = "/workspace/v027-1-adapter"
V027_1_HF_REPO = "lerugray/hammerstein-7b-v027-1"
V027_1_ADAPTER_TAR = "lora-adapter-v027-1.tar.gz"

LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

TRAIN_CONFIG = {
    "learning_rate": 2e-4,
    "per_device_train_batch_size": 2,
    "gradient_accumulation_steps": 4,
    "max_seq_length": 2048,
    "num_train_epochs": 2,
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
    "v027_2_additions_oversample": 3,
    "v01_ray_stack": "all",
    "v3a_synthetic_sample": 250,
}

EVAL_FRACTION = 0.10


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v027-2-additions",
                   default="data/ray-stack-sft-v0.2.7.2-additions.jsonl")
    p.add_argument("--v01-ray-stack",
                   default="data/ray-stack-sft-v0.1-combined.jsonl")
    p.add_argument("--v3a-synthetic",
                   default="tools/distill/data/synthetic-v3a-2026-05-09.jsonl")
    p.add_argument("--base-adapter", default=BASE_ADAPTER_PATH_DEFAULT)
    p.add_argument("--output",
                   default="training/24-7-variant/output/qwen7b-v027-2-continued")
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

    v_path = Path(args.v027_2_additions)
    if v_path.exists():
        v_rows = load_jsonl(args.v027_2_additions)
        for _ in range(MIX_TARGETS["v027_2_additions_oversample"]):
            for row in v_rows:
                text = format_example(row)
                if text:
                    examples.append(text)
        counts["v027_2_additions"] = len(v_rows) * MIX_TARGETS["v027_2_additions_oversample"]
    else:
        print(f"  ERROR: v0.2.7.2 additions missing: {args.v027_2_additions}")
        counts["v027_2_additions"] = 0

    v01_path = Path(args.v01_ray_stack)
    if v01_path.exists():
        rows = load_jsonl(args.v01_ray_stack)
        for row in rows:
            text = format_example(row)
            if text:
                examples.append(text)
        counts["v01_ray_stack"] = len(rows)
    else:
        counts["v01_ray_stack"] = 0

    v3a_path = Path(args.v3a_synthetic)
    if v3a_path.exists():
        rows = load_jsonl(args.v3a_synthetic)
        sample_n = min(MIX_TARGETS["v3a_synthetic_sample"], len(rows))
        random.seed(42)
        sampled = random.sample(rows, sample_n)
        for row in sampled:
            text = format_example(row)
            if text:
                examples.append(text)
        counts["v3a_synthetic_sample"] = sample_n
    else:
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

    print(f"\nLoading v0.2.7.1 base adapter from {args.base_adapter} (trainable=True)...")
    if not Path(args.base_adapter).exists():
        sys.exit(f"ERROR: base adapter dir not found at {args.base_adapter}. "
                 f"Pod bootstrap should extract HF tar {V027_1_HF_REPO}/{V027_1_ADAPTER_TAR} here.")
    model = PeftModel.from_pretrained(base, args.base_adapter, is_trainable=True)
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

    print("\nStarting continued training (v0.2.7.2)...")
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
    print("=== Qwen2.5-7B v0.2.7.2 continued-LoRA SFT ===")
    print(f"  Base model:          {BASE_MODEL}")
    print(f"  Base adapter:        {args.base_adapter}  (v0.2.7.1 continued)")
    print(f"  v0.2.7.2 additions:  {args.v027_2_additions} (x{MIX_TARGETS['v027_2_additions_oversample']} baseline oversample)")
    print(f"  v0.1 Ray-stack:      {args.v01_ray_stack} (full)")
    print(f"  v3a synthetic:       {args.v3a_synthetic} (sample {MIX_TARGETS['v3a_synthetic_sample']})")
    print(f"  Epochs:              {TRAIN_CONFIG['num_train_epochs']}")
    print(f"  Learning rate:       {TRAIN_CONFIG['learning_rate']}")
    eff_batch = TRAIN_CONFIG["per_device_train_batch_size"] * TRAIN_CONFIG["gradient_accumulation_steps"]
    print(f"  Effective batch:     {eff_batch}")
    print()

    if not Path(args.v027_2_additions).exists():
        print(f"ERROR: v0.2.7.2 additions not found at {args.v027_2_additions}")
        sys.exit(1)

    if not args.execute:
        examples, counts = build_mix(args)
        total = len(examples)
        print("Mix counts (dry-run):")
        for k, v in counts.items():
            print(f"  {k:30s}  {v:,}")
        print(f"  {'TOTAL':30s}  {total:,}")
        steps = (total * TRAIN_CONFIG["num_train_epochs"]) // eff_batch
        sec_per_step_a6000 = 2
        est_min_a6000 = (steps * sec_per_step_a6000) / 60
        print(f"\n  Est. steps:        {steps:,}")
        print(f"  Est. time (A6000): {est_min_a6000:.0f} min")
        print(f"  Est. time (H100):  {est_min_a6000 * 0.5:.0f} min")
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
