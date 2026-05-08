#!/usr/bin/env python3
"""QLoRA training scaffold for the Hammerstein distillation experiment.

Defaults to dry-run (prints config + cost estimate, no training).
Pass --execute to actually fire training.

Backends (auto-selected by --backend):
  - 'unsloth'  — NVIDIA GPU (8-12GB+ VRAM). Best speed/memory trade.
  - 'mlx'      — Apple Silicon Mac. Native, no NVIDIA needed.
  - 'kaggle'   — same as 'unsloth' but with Kaggle-friendly paths.

Inputs:
  data/synthetic-<DATE>.jsonl  ← from gen_data.py
Outputs:
  output/<MODEL>-hammerstein-lora/  ← LoRA adapter + tokenizer
  output/<MODEL>-hammerstein.gguf   ← merged + quantized (optional)

This is a SCAFFOLD. The training calls are stubbed because (a) the
synthetic data isn't generated yet, and (b) Ray's PC GPU spec hasn't
been confirmed. Once both are in, this script runs the experiment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "tools" / "distill" / "data"
OUTPUT_DIR = ROOT / "tools" / "distill" / "output"

DEFAULTS = {
    "qwen-7b": {
        "base_model": "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
        "lora_rank": 32,
        "lora_alpha": 32,
        "epochs": 3,
        "batch_size": 2,
        "grad_accum": 4,
        "max_seq_length": 2048,
        "learning_rate": 2e-4,
        "min_vram_gb": 10,
    },
    "llama-3b": {
        "base_model": "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
        "lora_rank": 16,
        "lora_alpha": 16,
        "epochs": 3,
        "batch_size": 4,
        "grad_accum": 2,
        "max_seq_length": 2048,
        "learning_rate": 2e-4,
        "min_vram_gb": 6,
    },
}


def format_for_training(record: dict) -> dict:
    """Convert a (query, response) row into chat-format training data.
    Per behavior-cloning frame: NO system prompt — framework is what
    we're teaching the student to bake in."""
    return {
        "messages": [
            {"role": "user", "content": record["query"]},
            {"role": "assistant", "content": record["response"]},
        ]
    }


def load_data(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"data not found at {path}; run gen_data.py --execute first")
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def estimate_train_time(n_rows: int, epochs: int, batch_size: int, grad_accum: int,
                       backend: str) -> dict:
    """Rough estimate. Actual times vary by hardware and seq length."""
    effective_batch = batch_size * grad_accum
    steps = (n_rows * epochs) // effective_batch
    # Empirical guesses (seconds per step on different backends, 7B model):
    sec_per_step = {
        "unsloth": 4.0,    # RTX 4090 with Unsloth
        "mlx": 8.0,        # M-series Mac
        "kaggle": 6.0,     # T4/P100
    }.get(backend, 5.0)
    total_minutes = (steps * sec_per_step) / 60
    return {"steps": steps, "estimated_minutes": int(total_minutes)}


def main() -> int:
    p = argparse.ArgumentParser(description="QLoRA training scaffold")
    p.add_argument("--data", default=str(DATA_DIR / "synthetic-latest.jsonl"))
    p.add_argument("--model-key", default="qwen-7b", choices=list(DEFAULTS.keys()))
    p.add_argument("--backend", default="unsloth", choices=["unsloth", "mlx", "kaggle"])
    p.add_argument("--output", default=None)
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--execute", dest="dry_run", action="store_false",
                   help="ACTUALLY train. Default: dry-run.")
    args = p.parse_args()

    config = DEFAULTS[args.model_key]
    out_dir = Path(args.output) if args.output else OUTPUT_DIR / f"{args.model_key}-hammerstein-lora"

    data_path = Path(args.data)
    if data_path.exists():
        rows = load_data(data_path)
        n_rows = len(rows)
        sample = rows[0] if rows else None
    else:
        n_rows = 2000  # estimate
        sample = None

    timing = estimate_train_time(n_rows, config["epochs"], config["batch_size"],
                                 config["grad_accum"], args.backend)

    print(f"Plan:")
    print(f"  Data: {data_path}")
    print(f"  Rows: {n_rows}{' (estimated; data not generated yet)' if not data_path.exists() else ''}")
    print(f"  Model: {args.model_key} ({config['base_model']})")
    print(f"  Backend: {args.backend}")
    print(f"  LoRA: rank={config['lora_rank']}, alpha={config['lora_alpha']}")
    print(f"  Training: {config['epochs']} epochs, batch={config['batch_size']}×{config['grad_accum']}")
    print(f"  Steps: {timing['steps']}")
    print(f"  Estimated time: ~{timing['estimated_minutes']} minutes")
    print(f"  Min VRAM: {config['min_vram_gb']} GB")
    print(f"  Output: {out_dir}")

    if sample:
        print(f"\n  Data sample:")
        print(f"    query: {(sample.get('query') or '')[:80]}…")
        print(f"    response: {(sample.get('response') or '')[:80]}…")

    if args.dry_run:
        print(f"\n[DRY-RUN] No training. Re-run with --execute to fire.")
        if args.backend == "unsloth":
            print(f"\nFor unsloth backend, pip install dependencies first:")
            print(f"  pip install unsloth")
        elif args.backend == "mlx":
            print(f"\nFor mlx backend on Apple Silicon:")
            print(f"  pip install mlx-lm")
        return 0

    # Real execution path — only entered with --execute
    print(f"\n[EXECUTE] training {args.model_key} via {args.backend}…")

    if args.backend == "unsloth":
        # Unsloth + TRL pipeline. The standard pattern:
        # from unsloth import FastLanguageModel
        # from trl import SFTTrainer
        # model, tok = FastLanguageModel.from_pretrained(config['base_model'], ...)
        # model = FastLanguageModel.get_peft_model(model, r=config['lora_rank'], ...)
        # trainer = SFTTrainer(model=model, train_dataset=..., args=...)
        # trainer.train()
        # model.save_pretrained(out_dir)
        sys.exit("unsloth training not yet wired; install + implement after data is generated")
    elif args.backend == "mlx":
        # mlx_lm.lora --model {base} --train --data {data_path} --adapter-path {out_dir}
        sys.exit("mlx training not yet wired; install + implement after data is generated")
    elif args.backend == "kaggle":
        # Same as unsloth but with /kaggle/working/ paths
        sys.exit("kaggle path not yet wired; configure when running on Kaggle")

    return 0


if __name__ == "__main__":
    sys.exit(main())
