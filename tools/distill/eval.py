#!/usr/bin/env python3
"""Evaluation harness for the distilled Hammerstein model.

Per MODEL-EXPERIMENT.md eval methodology, runs each held-out test prompt
through three configurations:

  1. vanilla    — bare base model, no framework, no fine-tune
  2. student    — fine-tuned model (no system prompt; framework baked in)
  3. gold       — Qwen3.6 + Hammerstein system prompt (the wrapper today)

Then scores each response on:
  - Structural shape (Boolean: contains ≥3 framework markers)
  - Length (comparable to gold within ±50%)
  - Hallucination indicators (manual flag pass)

Outputs:
  - data/eval-<DATE>.jsonl with all responses
  - data/eval-<DATE>.summary.md with the comparison table

This file is a SCAFFOLD until E3 (training) ships. The vanilla and
student backends require local model paths that don't yet exist.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "tools" / "distill" / "data"
EVAL_SET = DATA_DIR / "eval-set.jsonl"

QUALITY_MARKERS = [
    "load-bearing", "structural", "counter-observation", "verification",
    "failure mode", "trade", "scope", "stupid-industrious", "clever-lazy",
    "clever-industrious", "stupid-lazy",
]
PASS_THRESHOLD_GOLD = 0.80     # student must score ≥80% of gold
PASS_THRESHOLD_HALLUC = 0.15   # ≤15% hallucination rate


def structural_score(response: str) -> float:
    """Fraction of QUALITY_MARKERS present in response. 0..1."""
    text = response.lower()
    hits = sum(1 for m in QUALITY_MARKERS if m in text)
    return min(hits / 4.0, 1.0)  # 4+ markers = full score


def call_gold(query: str, template: str) -> dict:
    """Run query through current wrapper (gold standard)."""
    import subprocess
    from hp_lib import HAMMERSTEIN_BIN  # type: ignore
    cmd = [HAMMERSTEIN_BIN, "--template", template, query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    if r.returncode != 0:
        return {"error": r.stderr.strip()}
    cost_m = re.search(r"cost_usd=\$(\d+\.\d+)", r.stderr)
    return {"response": r.stdout.strip(),
            "cost_usd": float(cost_m.group(1)) if cost_m else None}


def call_student(query: str, model_path: str) -> dict:
    """Run query through the fine-tuned model. Stub — implement after E3."""
    # When the LoRA adapter exists:
    #   - Use mlx_lm or transformers to load base + adapter
    #   - Run inference with no system prompt (framework baked in)
    return {"error": "student backend not implemented; complete E3 first",
            "stub": True, "model_path": model_path}


def call_vanilla(query: str, model_path: str) -> dict:
    """Run query through bare base model. Stub — implement after E3."""
    return {"error": "vanilla backend not implemented; complete E3 first",
            "stub": True, "model_path": model_path}


def main() -> int:
    p = argparse.ArgumentParser(description="Evaluate distilled Hammerstein model")
    p.add_argument("--eval-set", default=str(EVAL_SET))
    p.add_argument("--student-path", default=None,
                   help="Path to fine-tuned model + adapter (post-E3)")
    p.add_argument("--vanilla-path", default=None, help="Path to base model")
    p.add_argument("--skip-gold", action="store_true",
                   help="Skip gold-standard calls (cached from prior run)")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    eval_path = Path(args.eval_set)
    if not eval_path.exists():
        sys.exit(f"eval-set not found at {eval_path}; create it first (manual curation)")

    sys.path.insert(0, str(ROOT))

    eval_prompts = []
    with eval_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                eval_prompts.append(json.loads(line))
    if args.limit:
        eval_prompts = eval_prompts[:args.limit]

    print(f"Loaded {len(eval_prompts)} eval prompts from {eval_path}")
    print(f"Configurations: gold={'skip' if args.skip_gold else 'run'}, "
          f"student={'run' if args.student_path else 'skip'}, "
          f"vanilla={'run' if args.vanilla_path else 'skip'}")

    out = DATA_DIR / f"eval-{dt.date.today()}.jsonl"
    summary = {"gold": [], "student": [], "vanilla": []}

    with out.open("w") as f:
        for i, prompt in enumerate(eval_prompts, 1):
            query = prompt["query"]
            template = prompt.get("template", "audit-this-plan")
            print(f"  [{i}/{len(eval_prompts)}] {query[:60]}...")
            row = {"query": query, "template": template}

            if not args.skip_gold:
                gold = call_gold(query, template)
                row["gold"] = gold
                if "response" in gold:
                    summary["gold"].append(structural_score(gold["response"]))

            if args.student_path:
                student = call_student(query, args.student_path)
                row["student"] = student
                if "response" in student:
                    summary["student"].append(structural_score(student["response"]))

            if args.vanilla_path:
                vanilla = call_vanilla(query, args.vanilla_path)
                row["vanilla"] = vanilla
                if "response" in vanilla:
                    summary["vanilla"].append(structural_score(vanilla["response"]))

            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Print summary
    print(f"\nResults written to {out}")
    print()
    for name, scores in summary.items():
        if scores:
            avg = sum(scores) / len(scores)
            print(f"  {name:8s}: avg structural score {avg:.2f} (n={len(scores)})")

    if summary["student"] and summary["gold"]:
        gold_avg = sum(summary["gold"]) / len(summary["gold"])
        student_avg = sum(summary["student"]) / len(summary["student"])
        ratio = student_avg / gold_avg if gold_avg > 0 else 0
        print(f"\n  Student vs gold ratio: {ratio:.2f}")
        print(f"  Pass threshold: {PASS_THRESHOLD_GOLD:.2f}")
        if ratio >= PASS_THRESHOLD_GOLD:
            print(f"  Verdict: PASS — fine-tune retains framework structure")
        else:
            print(f"  Verdict: FAIL — fine-tune lost framework structure; publish failure log")

    return 0


if __name__ == "__main__":
    sys.exit(main())
