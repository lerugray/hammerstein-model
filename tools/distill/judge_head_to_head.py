#!/usr/bin/env python3
"""Blind head-to-head LLM judge: v1 vs v3a strategic responses.

Marker counts measure FORM (does the response contain "load-bearing",
"verification", etc.). They don't measure QUALITY (is the reasoning
actually better?).

This script:
  1. Loads v1 and v3a per-prompt eval results
  2. For each strategic prompt, randomly swaps A/B order (blind)
  3. Asks qwen3.6-plus to judge "which response is more framework-correct
     and useful as strategic reasoning?"
  4. Reports v3a's win-rate (counting ties)

Cost: 40 prompts × ~$0.01 = ~$0.40 OpenRouter.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "tools" / "distill" / "data"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
JUDGE_MODEL = "qwen/qwen3.6-plus"

JUDGE_PROMPT = """You are evaluating two responses to a strategic-reasoning query. Both responses are produced by AI assistants applying the Hammerstein framework (a strategic-thinking framework that uses concepts like clever-lazy, stupid-industrious, load-bearing risks, failure modes, and verification gates).

Pick the response that is MORE useful as strategic reasoning. Judge on:
- Identification of load-bearing risks
- Concrete failure modes (not generic)
- Actionable verification gates
- Honest disposition (don't framework-ify trivial decisions; do framework-correctly the hard ones)
- Calibrated recommendations (not too aggressive, not too cautious)

Output ONLY one of: "A", "B", or "TIE". No explanation.

QUERY:
{query}

RESPONSE A:
{a}

RESPONSE B:
{b}

VERDICT (A / B / TIE):"""


def openrouter_chat(messages: list[dict], model: str, max_tokens: int = 50,
                    timeout: int = 120) -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    body = json.dumps({
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(OPENROUTER_URL, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def judge_pair(query: str, a_resp: str, b_resp: str, idx: int) -> dict:
    """Returns dict with raw verdict + which slot held v3a (for blind tracking)."""
    rng = random.Random(idx)  # deterministic shuffle per prompt
    swap = rng.random() < 0.5
    if swap:
        a, b = b_resp, a_resp  # B is v1, A is v3a
        v3a_slot = "A"
    else:
        a, b = a_resp, b_resp  # A is v1, B is v3a
        v3a_slot = "B"

    prompt = JUDGE_PROMPT.format(query=query, a=a, b=b)
    raw = openrouter_chat(
        [{"role": "user", "content": prompt}],
        model=JUDGE_MODEL, max_tokens=10,
    )
    raw_upper = raw.upper().strip().rstrip(".")
    if "TIE" in raw_upper:
        verdict = "TIE"
    elif raw_upper.startswith("A") or "RESPONSE A" in raw_upper:
        verdict = "A"
    elif raw_upper.startswith("B") or "RESPONSE B" in raw_upper:
        verdict = "B"
    else:
        verdict = "UNCLEAR"

    if verdict == v3a_slot:
        outcome = "v3a_wins"
    elif verdict == "TIE":
        outcome = "tie"
    elif verdict == "UNCLEAR":
        outcome = "unclear"
    else:
        outcome = "v1_wins"

    return {
        "idx": idx, "query": query[:80],
        "v3a_slot": v3a_slot, "raw_judge": raw,
        "verdict": verdict, "outcome": outcome,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--v1", default=str(DATA_DIR / "eval-v1-rerun-v3a-2026-05-09.jsonl"))
    p.add_argument("--v3a", default=str(DATA_DIR / "eval-v3a-2026-05-09.jsonl"))
    p.add_argument("--workers", type=int, default=10)
    p.add_argument("--out", default=str(DATA_DIR / "judge-v1-vs-v3a-2026-05-09.json"))
    args = p.parse_args()

    with open(args.v1) as f:
        v1_rows = [json.loads(l) for l in f if l.strip()]
    with open(args.v3a) as f:
        v3a_rows = [json.loads(l) for l in f if l.strip()]

    # Strategic prompts only (skip _forgetting_check)
    pairs = []
    for i, (v1r, v3ar) in enumerate(zip(v1_rows, v3a_rows)):
        if v1r.get("_forgetting_check") or v3ar.get("_forgetting_check"):
            continue
        v1_resp = v1r.get("student", {}).get("response")
        v3a_resp = v3ar.get("student", {}).get("response")
        if not (v1_resp and v3a_resp):
            continue
        pairs.append((i, v1r["query"], v1_resp, v3a_resp))

    print(f"Judging {len(pairs)} strategic head-to-head pairs…")
    print(f"Cost estimate: ~${len(pairs) * 0.01:.2f}\n", flush=True)

    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(judge_pair, q, v1, v3a, i): i for i, q, v1, v3a in pairs}
        for fut in as_completed(futures):
            try:
                r = fut.result()
                results.append(r)
                if len(results) % 10 == 0:
                    print(f"  {len(results)}/{len(pairs)} judged…", flush=True)
            except Exception as e:
                print(f"  judge failed: {e}", file=sys.stderr)

    elapsed = (time.time() - t0) / 60
    print(f"\nDone in {elapsed:.1f} min")

    outcomes = {}
    for r in results:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1

    n = len(results)
    v3a_wins = outcomes.get("v3a_wins", 0)
    v1_wins = outcomes.get("v1_wins", 0)
    ties = outcomes.get("tie", 0)
    unclear = outcomes.get("unclear", 0)

    print("\n=== Head-to-head verdict ===")
    print(f"v3a wins: {v3a_wins}/{n} ({v3a_wins/n*100:.1f}%)")
    print(f"v1 wins:  {v1_wins}/{n} ({v1_wins/n*100:.1f}%)")
    print(f"Ties:     {ties}/{n} ({ties/n*100:.1f}%)")
    if unclear:
        print(f"Unclear:  {unclear}/{n}")

    # Conventional thresholds: >55% = significant preference, 50% ± 5% = roughly equal
    if v3a_wins / max(n - ties - unclear, 1) > 0.55:
        print(f"\n→ v3a is QUALITATIVELY PREFERRED (excluding ties: {v3a_wins / max(n-ties-unclear,1) * 100:.0f}%)")
    elif v1_wins / max(n - ties - unclear, 1) > 0.55:
        print(f"\n→ v1 is QUALITATIVELY PREFERRED (excluding ties)")
    else:
        print(f"\n→ ROUGHLY EQUAL — v3a's improvement on raw markers is form-level only")

    # Save full per-prompt results
    Path(args.out).write_text(json.dumps({
        "outcomes": outcomes, "n": n,
        "v3a_win_rate_excl_ties": v3a_wins / max(n - ties - unclear, 1),
        "details": results,
    }, indent=2))
    print(f"\n[wrote {args.out}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
