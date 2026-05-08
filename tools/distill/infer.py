#!/usr/bin/env python3
"""Quick inference test for the trained Hammerstein LoRA adapter.

Loads base + LoRA adapter, generates a response with NO system prompt
(framework should be baked into weights). Used to spot-check the
fine-tune before running the full eval harness.

Usage:
    python tools/distill/infer.py --adapter <path/to/lora-adapter> \
        "Audit this plan: rebuild our auth system in Rust"

Or for batch sanity check (5 prompts from eval set):
    python tools/distill/infer.py --adapter <path/to/lora-adapter> --sample 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_SET = ROOT / "tools" / "distill" / "data" / "eval-set.jsonl"


def load_model_and_tokenizer(adapter_path: str):
    try:
        from unsloth import FastLanguageModel
    except ImportError:
        sys.exit("missing dependency: unsloth\n"
                 "Install: pip install unsloth")
    print(f"  loading base + adapter from {adapter_path}…")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=adapter_path,
        max_seq_length=2048,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    return model, tokenizer


def generate(model, tokenizer, query: str, max_new_tokens: int = 800) -> str:
    msgs = [{"role": "user", "content": query}]
    prompt = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    out = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        temperature=0.7,
        top_p=0.9,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
    )
    text = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return text.strip()


def main() -> int:
    p = argparse.ArgumentParser(description="Inference test for trained Hammerstein LoRA")
    p.add_argument("--adapter", required=True, help="Path to trained LoRA adapter")
    p.add_argument("--sample", type=int, default=0,
                   help="Run N prompts from the eval set (0 = use positional query arg)")
    p.add_argument("query", nargs="?", help="A single query to run")
    args = p.parse_args()

    if args.sample == 0 and not args.query:
        sys.exit("Provide a query or --sample N")

    model, tokenizer = load_model_and_tokenizer(args.adapter)

    if args.sample > 0:
        eval_rows = []
        with EVAL_SET.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    eval_rows.append(json.loads(line))
        sample = eval_rows[:args.sample]
        for i, row in enumerate(sample, 1):
            print(f"\n=== Eval prompt {i}/{args.sample} [{row['template']} | {row['domain']}] ===")
            print(f"Q: {row['query']}\n")
            response = generate(model, tokenizer, row["query"])
            print(f"R:\n{response}\n")
    else:
        print(f"\nQ: {args.query}\n")
        response = generate(model, tokenizer, args.query)
        print(f"R:\n{response}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
