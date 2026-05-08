#!/usr/bin/env python3
"""Convert the trained Hammerstein-7B LoRA adapter to GGUF for Ollama.

Pipeline:
  1. Load base Qwen2.5-7B-Instruct + the LoRA adapter (from HF or local)
  2. Merge the adapter into the base weights
  3. Export to GGUF format (via llama.cpp, invoked by Unsloth)
  4. Quantize to Q4_K_M (default) — ~5 GB, runs on any Mac with 8GB+ RAM
  5. Push to the same HF repo as additional files

After this lands, anyone with Ollama can:
    ollama pull lerugray/hammerstein-7b-lora:q4_k_m
or copy the Modelfile.template and `ollama create` from the local GGUF.

Usage on a GPU pod:
    export HF_TOKEN=hf_xxxxxxxx
    python tools/distill/convert_gguf.py
    # Optional: --quants q4_k_m,q5_k_m,q8_0
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_ADAPTER = "lerugray/hammerstein-7b-lora"
DEFAULT_REPO = "lerugray/hammerstein-7b-lora"
DEFAULT_QUANTS = ["q4_k_m"]


def get_hf_token() -> str:
    """Read HF token from env var or ~/.huggingface_token."""
    if env := os.environ.get("HF_TOKEN"):
        return env.strip()
    token_file = Path.home() / ".huggingface_token"
    if token_file.exists():
        return token_file.read_text().strip()
    sys.exit("HF_TOKEN not set and ~/.huggingface_token not found")


def main() -> int:
    p = argparse.ArgumentParser(description="Convert Hammerstein-7B LoRA to GGUF")
    p.add_argument("--adapter", default=DEFAULT_ADAPTER,
                   help=f"Adapter HF id or local path (default: {DEFAULT_ADAPTER})")
    p.add_argument("--repo", default=DEFAULT_REPO,
                   help=f"Target HF repo for GGUF files (default: {DEFAULT_REPO})")
    p.add_argument("--quants", default=",".join(DEFAULT_QUANTS),
                   help=f"Comma-separated quantization methods (default: {DEFAULT_QUANTS[0]}). "
                        "Options include: q2_k, q3_k_m, q4_0, q4_k_m, q5_k_m, q6_k, q8_0, f16")
    p.add_argument("--local-only", action="store_true",
                   help="Save GGUF files locally only; skip HF push")
    p.add_argument("--output-dir", default="/workspace/gguf-output",
                   help="Local output dir for intermediate files")
    args = p.parse_args()

    quants = [q.strip() for q in args.quants.split(",") if q.strip()]
    print(f"Converting {args.adapter} → GGUF, quants: {quants}", flush=True)

    hf_token = None
    if not args.local_only:
        hf_token = get_hf_token()
        print(f"  HF token loaded ({len(hf_token)} chars)", flush=True)

    try:
        from unsloth import FastLanguageModel
    except ImportError:
        sys.exit("missing dep: unsloth\n  pip install unsloth")

    print(f"\n[1/3] Loading base + adapter from {args.adapter}…", flush=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.adapter,
        max_seq_length=2048,
        load_in_4bit=True,  # 4-bit load is fine since we're targeting Q4_K_M anyway
    )
    FastLanguageModel.for_inference(model)
    print("  loaded", flush=True)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for q in quants:
        print(f"\n[2/3] Converting + quantizing → {q}…", flush=True)
        # Unsloth handles: merge adapter into base → export GGUF via
        # llama.cpp's convert_hf_to_gguf.py → quantize via llama.cpp's
        # quantize binary. This compiles llama.cpp on first run (~3 min).
        if args.local_only:
            model.save_pretrained_gguf(
                str(out_dir),
                tokenizer,
                quantization_method=q,
            )
            print(f"  saved locally to {out_dir}", flush=True)
        else:
            print(f"\n[3/3] Pushing {q} to {args.repo}…", flush=True)
            model.push_to_hub_gguf(
                args.repo,
                tokenizer,
                quantization_method=q,
                token=hf_token,
            )
            print(f"  pushed: https://huggingface.co/{args.repo}", flush=True)

    print("\n=== Done ===")
    if not args.local_only:
        print(f"Files at: https://huggingface.co/{args.repo}/tree/main")
        print()
        print("To use locally with Ollama:")
        print(f"  1. Download the GGUF: huggingface-cli download {args.repo} --include '*.gguf'")
        print(f"  2. Create Modelfile (see tools/distill/Modelfile.template)")
        print(f"  3. ollama create hammerstein -f Modelfile")
    return 0


if __name__ == "__main__":
    sys.exit(main())
