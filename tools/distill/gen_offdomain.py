#!/usr/bin/env python3
"""Generate off-domain instruction-following pairs for v3a mixed-mode training.

The point: teach the adapter that framework markers are for framework-shaped
queries only, not for "write a haiku" or "what's HTTP 404".

Pipeline:
  1. 10 seed templates × 25 expansions each = 250 prompts
  2. For each, get a response from qwen3-coder-flash with NO system prompt
  3. Filter: response must NOT contain framework markers (these become the
     anti-leakage signal during training)
  4. Write to data/off-domain-<DATE>.jsonl in same format as synthetic data

Cost: ~$0.15 OpenRouter (cheap because no framework system prompt).
Time: ~5 min wall.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "tools" / "distill" / "data"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
EXPANSION_MODEL = "qwen/qwen3-coder-flash"
RESPONSE_MODEL = "qwen/qwen3-coder-flash"

OFF_DOMAIN_SEEDS = {
    "creative": [
        "Write a {length} {form} about {topic}.",
        "Compose a {form} describing {topic}.",
        "Invent a {entity_type} named after {inspiration}.",
        "Open a short story with a sentence set in {setting}.",
    ],
    "factual": [
        "Who/what/when was {entity}?",
        "What is the {attribute} of {thing}?",
        "Name {n} {category}.",
        "In what year did {historical_event} happen?",
    ],
    "technical": [
        "Explain in one sentence what {concept} is.",
        "What does {acronym} stand for and what does it do?",
        "What's the difference between {a} and {b}?",
        "Define {term} in two sentences.",
    ],
    "instructional": [
        "How do you {task}?",
        "Walk me through {process}.",
        "Steps to {goal}.",
        "Give a one-paragraph beginner guide to {skill}.",
    ],
    "conversational": [
        "Recommend a {item} for {situation}.",
        "What's a good {gift_or_idea} for someone who likes {interest}?",
    ],
    "math_code": [
        "What is {math_problem}?",
        "Write a one-line {language} expression that {does_x}.",
    ],
}

# Quality filter: anti-leakage check — responses MUST NOT contain framework markers
FRAMEWORK_MARKERS = [
    "load-bearing", "structural", "counter-observation", "verification",
    "failure mode", "trade", "stupid-industrious", "clever-lazy",
    "clever-industrious", "stupid-lazy", "plain english summary",
]

DEFAULT_PER_SEED = 11   # ~250 pairs across all seeds
DEFAULT_WORKERS = 20


def openrouter_chat(messages: list[dict], model: str, max_tokens: int = 600,
                    timeout: int = 60) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not in env")
    body = json.dumps({
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": 0.8,
    }).encode()
    req = urllib.request.Request(OPENROUTER_URL, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return {
        "text": data["choices"][0]["message"]["content"],
        "in_tok": data.get("usage", {}).get("prompt_tokens", 0),
        "out_tok": data.get("usage", {}).get("completion_tokens", 0),
    }


def expand_seed(seed: str, category: str, n: int) -> list[str]:
    """Ask qwen to fill seed placeholders with N concrete off-domain prompts."""
    meta_prompt = (
        f"Generate exactly {n} concrete, varied off-domain user queries.\n\n"
        f"CATEGORY: {category}\n"
        f"SEED PATTERN: {seed}\n\n"
        f"Each query should be a normal, everyday question or task — NOT a "
        f"strategic-reasoning query, NOT an audit of a plan, NOT a 'should I "
        f"do X' question. Examples of off-domain shapes: 'write a haiku', "
        f"'what is HTTP 404', 'how do I boil an egg', 'recommend a book'.\n\n"
        f"For each:\n"
        f"- Replace {{placeholder}} tokens with realistic, diverse values\n"
        f"- Keep it 1-2 sentences\n"
        f"- Make each different from the others (vary the topic / domain)\n\n"
        f"Output ONLY the {n} queries, one per line, prefixed with 'Q: '. "
        f"No preamble, no numbering, no explanation."
    )
    result = openrouter_chat(
        [{"role": "user", "content": meta_prompt}],
        model=EXPANSION_MODEL, max_tokens=800,
    )
    queries = []
    for line in result["text"].splitlines():
        line = line.strip()
        m = re.match(r"^Q[:\.]\s*(.+)", line, re.IGNORECASE)
        if m:
            q = m.group(1).strip()
            if 10 < len(q) < 300:
                queries.append(q)
    return queries[:n]


def get_response(query: str, timeout: int = 60) -> dict:
    """Get a non-framework response via qwen3-coder-flash, no system prompt."""
    result = openrouter_chat(
        [{"role": "user", "content": query}],
        model=RESPONSE_MODEL, max_tokens=600, timeout=timeout,
    )
    return {"response": result["text"].strip(), "in_tok": result["in_tok"],
            "out_tok": result["out_tok"]}


def passes_anti_leakage_filter(response: str) -> bool:
    """Off-domain responses must NOT contain framework markers."""
    text = response.lower()
    for m in FRAMEWORK_MARKERS:
        if m in text:
            return False
    return len(response) >= 30  # trivial sanity


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=None)
    p.add_argument("--per-seed", type=int, default=DEFAULT_PER_SEED)
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    p.add_argument("--execute", action="store_true",
                   help="ACTUALLY make API calls. Default: dry-run.")
    args = p.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else DATA_DIR / f"off-domain-{dt.date.today()}.jsonl"

    total_seeds = sum(len(v) for v in OFF_DOMAIN_SEEDS.values())
    total_target = total_seeds * args.per_seed
    print(f"Plan: {total_seeds} seed templates × {args.per_seed} expansions = ~{total_target} prompts")
    print(f"Cost estimate: ~${total_target * 0.0003:.2f} OpenRouter (qwen3-coder-flash)")
    print(f"Output: {out}")

    if not args.execute:
        print("\n[DRY-RUN] re-run with --execute to fire.")
        return 0

    # Phase 1: expansion
    print(f"\n[EXECUTE] Phase 1: expanding seeds…")
    expansions = []
    expansion_tasks = [(s, cat, args.per_seed)
                       for cat, seeds in OFF_DOMAIN_SEEDS.items()
                       for s in seeds]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(expand_seed, s, cat, n): (s, cat)
                   for s, cat, n in expansion_tasks}
        for fut in as_completed(futures):
            s, cat = futures[fut]
            try:
                qs = fut.result()
                for q in qs:
                    expansions.append({"query": q, "category": cat})
            except Exception as e:
                print(f"  expansion failed ({cat}): {e}", file=sys.stderr)
    print(f"Expanded {len(expansions)} prompts")

    # Phase 2: get responses (no framework system prompt)
    print(f"\nPhase 2: getting responses (no system prompt)…")
    written = skipped = 0
    t0 = time.time()
    with out.open("w") as f, ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(get_response, e["query"]): e for e in expansions}
        for i, fut in enumerate(as_completed(futures), 1):
            e = futures[fut]
            try:
                result = fut.result()
            except Exception as ex_e:
                skipped += 1
                continue
            if not passes_anti_leakage_filter(result["response"]):
                skipped += 1
                continue
            # Format compatible with synthetic-*.jsonl (so train.py can concat)
            record = {
                "template": "off-domain",
                "domain": e["category"],
                "seed_idx": 0,
                "query": e["query"],
                "response": result["response"],
                "cost_usd": None,
                "latency_ms": None,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            written += 1
            if i % 20 == 0:
                print(f"  progress: {i}/{len(expansions)}, {written} written, {skipped} skipped",
                      flush=True)

    elapsed = (time.time() - t0) / 60
    print(f"\nDone in {elapsed:.1f} min: {written} pairs written, {skipped} skipped")
    print(f"Output: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
