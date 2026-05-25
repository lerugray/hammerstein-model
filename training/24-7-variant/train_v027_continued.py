#!/usr/bin/env python3
"""v0.2.7 continued-LoRA training — iteration on v0.2.6.2.

Methodology shift from v0.2.6.x:
  - Per-axis oversample lives in concat-sanitize (per the 11-axis data
    design pass on the Mac side). The additions file already has
    oversample baked in.
  - The base adapter is v0.2.6.2 (continued LoRA), not v3a. v0.2.6.2
    is Ray's stated regression floor — the best-talking version yet —
    so v0.2.7 builds on it rather than re-deriving the voice gains.
  - "Iter pairs extra oversample" logic from v0.2.6.x is gone; the
    file-level oversample dict in v027_concat_sanitize.py covers it.

Training mix (target ~2,400-2,600 examples):
- ~600 v0.2.7 additions (oversample baked in) x 3 baseline = ~1,800
- 541 v0.1 ray-stack x 1                                   = 541
- 250 v3a synthetic sample                                 = 250
- TOTAL                                                    = ~2,600

Estimated train time:
- A6000 ~25-30 min
- H100 SXM5 ~12-18 min  (Ray's "burn the runpod account" override)
- H200 SXM ~10-15 min

Revert point: v0.2.6.2 if v0.2.7 fails the cutover gate.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"

# v0.2.7 STARTS from the v0.2.6.2 adapter — not v3a. Pod-side bootstrap
# downloads the tar from HF and extracts to BASE_ADAPTER_PATH before training.
BASE_ADAPTER_PATH_DEFAULT = "/workspace/v026-2-adapter"
V026_2_HF_REPO = "lerugray/hammerstein-7b-v026-2"
V026_2_ADAPTER_TAR = "lora-adapter-v026-2.tar.gz"

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
    "v027_additions_oversample": 3,   # applied on top of the per-file oversample
    "v01_ray_stack": "all",
    "v3a_synthetic_sample": 250,
}

EVAL_FRACTION = 0.10


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v027-additions",
                   default="data/ray-stack-sft-v0.2.7-additions.jsonl")
    p.add_argument("--v01-ray-stack",
                   default="data/ray-stack-sft-v0.1-combined.jsonl")
    p.add_argument("--v3a-synthetic",
                   default="tools/distill/data/synthetic-v3a-2026-05-09.jsonl")
    p.add_argument("--base-adapter", default=BASE_ADAPTER_PATH_DEFAULT,
                   help="Path to the v0.2.6.2 adapter dir (pod-side; pre-extracted from HF tar).")
    p.add_argument("--output",
                   default="training/24-7-variant/output/qwen7b-v027-continued")
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

    # 1) v0.2.7 additions at 3x baseline oversample (on top of per-file
    # oversample already baked in by concat-sanitize).
    v_path = Path(args.v027_additions)
    if v_path.exists():
        v_rows = load_jsonl(args.v027_additions)
        for _ in range(MIX_TARGETS["v027_additions_oversample"]):
            for row in v_rows:
                text = format_example(row)
                if text:
                    examples.append(text)
        counts["v027_additions"] = len(v_rows) * MIX_TARGETS["v027_additions_oversample"]
    else:
        print(f"  ERROR: v0.2.7 additions missing: {args.v027_additions}")
        counts["v027_additions"] = 0

    # 2) v0.1 Ray-stack baseline (full). Carryover anchor.
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

    # 3) v3a synthetic English-voice anchor (sample 250). Carryover; per
    # memory project_v3a_synthetic_is_english_anchor.md — dropping this
    # caused mode collapse on Chinese-text prompts in v0.2.1.
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

    print(f"\nLoading v0.2.6.2 base adapter from {args.base_adapter} (trainable=True)...")
    if not Path(args.base_adapter).exists():
        sys.exit(f"ERROR: base adapter dir not found at {args.base_adapter}. "
                 f"Pod bootstrap should extract HF tar {V026_2_HF_REPO}/{V026_2_ADAPTER_TAR} here.")
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

    print("\nStarting continued training (v0.2.7)...")
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
    print("=== Qwen2.5-7B v0.2.7 continued-LoRA SFT ===")
    print(f"  Base model:        {BASE_MODEL}")
    print(f"  Base adapter:      {args.base_adapter}  (v0.2.6.2 continued)")
    print(f"  v0.2.7 additions:  {args.v027_additions} (x{MIX_TARGETS['v027_additions_oversample']} baseline oversample)")
    print(f"  v0.1 Ray-stack:    {args.v01_ray_stack} (full)")
    print(f"  v3a synthetic:     {args.v3a_synthetic} (sample {MIX_TARGETS['v3a_synthetic_sample']})")
    print(f"  Epochs:            {TRAIN_CONFIG['num_train_epochs']}")
    print(f"  Learning rate:     {TRAIN_CONFIG['learning_rate']}")
    eff_batch = TRAIN_CONFIG["per_device_train_batch_size"] * TRAIN_CONFIG["gradient_accumulation_steps"]
    print(f"  Effective batch:   {eff_batch}")
    print()

    if not Path(args.v027_additions).exists():
        print(f"ERROR: v0.2.7 additions not found at {args.v027_additions}")
        print(f"  Run: python scripts/v027_concat_sanitize.py")
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
        print(f"  Est. time (H100):  {est_min_a6000 * 0.5:.0f} min  (rough ~2x speedup)")
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
