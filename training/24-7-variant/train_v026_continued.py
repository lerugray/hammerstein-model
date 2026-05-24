#!/usr/bin/env python3
"""v0.2.6 continued-LoRA training — empathy + moral-weight + extraction reliability
on top of v0.2.5.

Problem v0.2.6 fixes:
- v0.2.5 shipped voice + safety + Layer 2 + history-mimicry hardening
  and validated cleanly. Two residual axes that v0.2.5 didn't touch are
  now load-bearing for daily-driver promotion:
  1. EMPATHY + MORAL-WEIGHT REGISTER (8th pillar). Engage personal-
     emotional content with the engagement-shape constraint from
     homelab/docs/handoffs/hammerstein-v026-empathy-principles-2026-05-24.md
     — hold weight without pulling on it, no generic-empathy fillers,
     no excavation prompts, route grief into adjacent-care.
  2. EXTRACTION SCHEMA STABILITY + DENSITY FLOOR. Stop inventing
     `[AI]`-style hallucinated types in JSON-array extraction output;
     emit `[]` (empty array) for low-signal chunks instead of meta-
     comment entries. Brief at
     homelab/docs/handoffs/hammerstein-v026-extraction-reliability-2026-05-24.md.

Changes vs train_v025_continued.py:
- v0.2.6 additions = v0.2.5 additions (643 after sanitize) + 20 empathy
  + 7 extraction (one extraction pair dropped by name-regex sanitizer)
  = 670 pairs in data/ray-stack-sft-v0.2.6-additions.jsonl.
- The COMBINED file gets the v0.2.5 baseline 3x oversample.
- The 27 NEW PAIRS get an additional 3x oversample on top (so 9x
  effective) — this implements the brief's "3x oversample the 28 new
  pairs so they have proportional influence on the loss curve" while
  keeping the v0.2.5 pattern intact. Without the extra boost, the new
  pairs are only ~3% of the additions mix and the new axes don't reliably
  imprint on the weights.
- Math: 670 × 3 + 27 × 3 = 2,010 + 81 = 2,091 additions examples; the
  27 new pairs contribute 27 × (3 + 3) = 162 of those, ~7.7% of the
  additions slice and ~5.5% of the full mix (including v0.1 + v3a).

Kept from v0.2.5 (validated):
- LR 2e-4, 2 epochs, eff batch 8, max_seq 2048
- v3a 250-pair English-voice anchor
- v0.1 Ray-stack baseline (all 541)
- Bnb 4-bit NF4 base, LoRA on q/k/v/o + gate/up/down projections

Total mix ~2,800 pairs. Estimated A5000 ~$0.80 / ~38 min train.
Revert point: v0.2.5-validated tag if v0.2.6 regresses on voice probe
or v2 failure modes.
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
    "v026_additions_oversample": 3,         # v0.2.5 baseline pattern
    "v026_new_pairs_extra_oversample": 3,   # extra boost for the 27 new pairs
    "v01_ray_stack": "all",
    "v3a_synthetic_sample": 250,
}

EVAL_FRACTION = 0.10


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v026-additions",
                   default="data/ray-stack-sft-v0.2.6-additions.jsonl")
    p.add_argument("--v026-empathy",
                   default="data/v0.2.6-empathy-additions.jsonl")
    p.add_argument("--v026-extraction",
                   default="data/v0.2.6-extraction-reliability-additions.jsonl")
    p.add_argument("--v01-ray-stack",
                   default="data/ray-stack-sft-v0.1-combined.jsonl")
    p.add_argument("--v3a-synthetic",
                   default="tools/distill/data/synthetic-v3a-2026-05-09.jsonl")
    p.add_argument("--v3a-adapter", default=V3A_ADAPTER_HF)
    p.add_argument("--output",
                   default="training/24-7-variant/output/qwen7b-v026-continued")
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

    # 1) Full combined v0.2.6 additions at baseline 3x oversample.
    v026_path = Path(args.v026_additions)
    if v026_path.exists():
        v026_rows = load_jsonl(args.v026_additions)
        for _ in range(MIX_TARGETS["v026_additions_oversample"]):
            for row in v026_rows:
                text = format_example(row)
                if text:
                    examples.append(text)
        counts["v026_additions"] = len(v026_rows) * MIX_TARGETS["v026_additions_oversample"]
    else:
        print(f"  WARN: v0.2.6 additions missing: {args.v026_additions}")
        counts["v026_additions"] = 0

    # 2) Extra oversample on the 27 new pairs (20 empathy + 7 extraction
    # after sanitize). These already appear in the combined v0.2.6
    # additions; this loop adds 3x more so the new axes have proportional
    # influence on the loss curve (per handoff brief).
    new_pair_rows: list[dict] = []
    for new_path in [args.v026_empathy, args.v026_extraction]:
        p = Path(new_path)
        if not p.exists():
            print(f"  WARN: new-pair source missing: {new_path}")
            continue
        new_pair_rows.extend(load_jsonl(new_path))

    # Re-apply the same name-regex sanitization to keep the boosted set
    # consistent with what's in the combined file.
    import re
    SANITIZE_REGEX = re.compile(
        r"(Jason|Ricky|Kunal|James Rodgers|Ryan Fyr|sk-[a-zA-Z0-9]{10,}|hf_[A-Za-z0-9]+)"
    )
    sanitized_new_rows = []
    for r in new_pair_rows:
        if SANITIZE_REGEX.search(json.dumps(r, ensure_ascii=False)):
            continue
        sanitized_new_rows.append(r)

    for _ in range(MIX_TARGETS["v026_new_pairs_extra_oversample"]):
        for row in sanitized_new_rows:
            text = format_example(row)
            if text:
                examples.append(text)
    counts["v026_new_pairs_extra_oversample"] = (
        len(sanitized_new_rows) * MIX_TARGETS["v026_new_pairs_extra_oversample"]
    )

    # 3) v0.1 Ray-stack baseline (full).
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

    # 4) v3a synthetic English-voice anchor (sample 250).
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

    print("\nStarting continued training (v0.2.6)...")
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
    print("=== Qwen2.5-7B v0.2.6 continued-LoRA SFT ===")
    print(f"  Base model:       {BASE_MODEL}")
    print(f"  Starting adapter: {args.v3a_adapter}")
    print(f"  v0.2.6 additions: {args.v026_additions} (x{MIX_TARGETS['v026_additions_oversample']} oversample)")
    print(f"  v0.2.6 new pairs: empathy + extraction (x{MIX_TARGETS['v026_new_pairs_extra_oversample']} extra oversample)")
    print(f"  v0.1 Ray-stack:   {args.v01_ray_stack} (full)")
    print(f"  v3a synthetic:    {args.v3a_synthetic} (sample {MIX_TARGETS['v3a_synthetic_sample']})")
    print(f"  Epochs:           {TRAIN_CONFIG['num_train_epochs']}")
    print(f"  Learning rate:    {TRAIN_CONFIG['learning_rate']}")
    eff_batch = TRAIN_CONFIG["per_device_train_batch_size"] * TRAIN_CONFIG["gradient_accumulation_steps"]
    print(f"  Effective batch:  {eff_batch}")
    print()

    if not Path(args.v026_additions).exists():
        print(f"ERROR: v0.2.6 additions not found at {args.v026_additions}")
        print(f"  Run: python scripts/v026_concat_sanitize.py")
        sys.exit(1)

    if not args.execute:
        examples, counts = build_mix(args)
        total = len(examples)
        print("Mix counts (dry-run):")
        for k, v in counts.items():
            print(f"  {k:30s}  {v:,}")
        print(f"  {'TOTAL':30s}  {total:,}")
        steps = (total * TRAIN_CONFIG["num_train_epochs"]) // eff_batch
        sec_per_step = 3
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
