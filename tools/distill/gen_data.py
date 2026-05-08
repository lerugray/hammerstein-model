#!/usr/bin/env python3
"""Generate synthetic distillation data: seed → expansion → teacher.

Pipeline:
  1. Load seeds from seeds.py.
  2. For each (seed, domain), ask Qwen3.6 (direct OpenRouter, no
     framework) to fill placeholders with N concrete domain-specific
     queries. Cheap: ~$0.005/call.
  3. For each generated query, run the teacher (hammerstein CLI = Qwen3.6
     + framework + corpus retrieval) — concurrent via ThreadPoolExecutor.
     ~$0.01/call, ~75s/call latency.
  4. Filter for quality: response must contain ≥2 framework markers and
     ≥200 chars.
  5. Write to data/synthetic-<DATE>.jsonl with full metadata.

Defaults: 30 seeds × 8 domains × 3 expansions = 720 pairs.
Estimated cost: ~$8-10. Estimated time: ~1.5 hr with 10 concurrent workers.

Default mode is dry-run; pass --execute to actually fire.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from hp_lib import HAMMERSTEIN_BIN  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seeds import ALL_SEEDS, DOMAINS  # noqa: E402

DATA_DIR = ROOT / "tools" / "distill" / "data"
DEFAULT_DOMAINS = 8         # use first N from seeds.DOMAINS
DEFAULT_EXPANSIONS = 3      # per (seed, domain) pair
DEFAULT_WORKERS = 10        # concurrent teacher calls
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
EXPANSION_MODEL = "qwen/qwen3-coder-flash"  # cheap + fast for expansion
QUALITY_MARKERS = [
    "load-bearing", "structural", "counter-observation", "verification",
    "failure mode", "trade", "scope", "stupid-industrious", "clever-lazy",
]
MIN_QUALITY_MARKERS = 2
MIN_RESPONSE_CHARS = 200


def openrouter_chat(messages: list[dict], model: str, max_tokens: int = 1500,
                    timeout: int = 60) -> dict:
    """Direct OpenRouter call. Returns {"text": str, "cost_usd": float|None}."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not in env (source ~/.generalstaff/.env)")
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(OPENROUTER_URL, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    # Approximate cost from token counts. Real cost in /credits endpoint.
    in_tok = usage.get("prompt_tokens", 0)
    out_tok = usage.get("completion_tokens", 0)
    return {"text": text, "in_tok": in_tok, "out_tok": out_tok}


def expand_seed(seed: str, template: str, domain: str, n: int) -> list[str]:
    """Ask Qwen to fill seed placeholders with N concrete domain queries."""
    meta_prompt = (
        f"Generate exactly {n} concrete strategic-reasoning queries.\n\n"
        f"TEMPLATE TYPE: {template}\n"
        f"DOMAIN: {domain}\n"
        f"SEED PATTERN: {seed}\n\n"
        f"For each query:\n"
        f"- Replace any {{PLACEHOLDER}} tokens with realistic domain-specific values\n"
        f"- Make it a real strategic decision someone in {domain} might face\n"
        f"- Keep it 1-3 sentences\n"
        f"- Make each query different from the others\n\n"
        f"Output ONLY the {n} queries, one per line, prefixed with 'Q: '. "
        f"No preamble, no numbering, no explanation."
    )
    result = openrouter_chat(
        [{"role": "user", "content": meta_prompt}],
        model=EXPANSION_MODEL,
        max_tokens=600,
    )
    queries = []
    for line in result["text"].splitlines():
        line = line.strip()
        m = re.match(r"^Q[:\.]\s*(.+)", line, re.IGNORECASE)
        if m:
            q = m.group(1).strip()
            if len(q) > 20:  # filter too-short noise
                queries.append(q)
    return queries[:n]


def call_teacher(query: str, template: str, timeout: int = 180) -> dict:
    """Call hammerstein CLI with the framework. Returns response + meta."""
    cmd = [HAMMERSTEIN_BIN, "--template", template, query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if r.returncode != 0:
        return {"error": r.stderr.strip(), "rc": r.returncode}
    cost_m = re.search(r"cost_usd=\$(\d+\.\d+)", r.stderr)
    latency_m = re.search(r"latency_ms=(\d+)", r.stderr)
    return {
        "response": r.stdout.strip(),
        "cost_usd": float(cost_m.group(1)) if cost_m else None,
        "latency_ms": int(latency_m.group(1)) if latency_m else None,
    }


def passes_quality_filter(response: str) -> bool:
    text = response.lower()
    hits = sum(1 for m in QUALITY_MARKERS if m in text)
    return hits >= MIN_QUALITY_MARKERS and len(response) >= MIN_RESPONSE_CHARS


def collect_expansions(seeds_dict: dict, domains: list[str], per_seed: int,
                       max_workers: int = 4) -> list[dict]:
    """Run all expansion calls concurrently. Returns list of {template, domain, query}."""
    tasks = []
    for template, seeds in seeds_dict.items():
        for seed_idx, seed in enumerate(seeds):
            for domain in domains:
                tasks.append((template, seed_idx, seed, domain))

    expansions = []
    print(f"Expanding {len(tasks)} (seed, domain) pairs into ~{len(tasks) * per_seed} queries…")
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(expand_seed, seed, template, domain, per_seed):
                   (template, seed_idx, domain) for template, seed_idx, seed, domain in tasks}
        for i, fut in enumerate(as_completed(futures), 1):
            template, seed_idx, domain = futures[fut]
            try:
                qs = fut.result()
                for q in qs:
                    expansions.append({"template": template, "domain": domain,
                                       "seed_idx": seed_idx, "query": q})
            except Exception as e:
                print(f"  expansion failed ({template}, seed={seed_idx}, {domain}): {e}",
                      file=sys.stderr)
            if i % 20 == 0:
                print(f"  expansion progress: {i}/{len(tasks)} pairs, "
                      f"{len(expansions)} queries collected")
    print(f"Total expansions: {len(expansions)}")
    return expansions


def collect_teacher_outputs(queries: list[dict], out_path: Path,
                            max_workers: int = DEFAULT_WORKERS) -> tuple[int, int, float]:
    """Run teacher on each query concurrently, write JSONL incrementally.
    Returns (written, skipped, total_cost)."""
    written = skipped = 0
    total_cost = 0.0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f, ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(call_teacher, q["query"], q["template"]): q for q in queries}
        for i, fut in enumerate(as_completed(futures), 1):
            q = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                skipped += 1
                continue
            if "error" in result:
                skipped += 1
                continue
            if not passes_quality_filter(result.get("response", "")):
                skipped += 1
                continue
            record = {
                "template": q["template"],
                "domain": q["domain"],
                "seed_idx": q["seed_idx"],
                "query": q["query"],
                "response": result["response"],
                "cost_usd": result.get("cost_usd"),
                "latency_ms": result.get("latency_ms"),
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            written += 1
            total_cost += result.get("cost_usd") or 0
            if i % 25 == 0:
                print(f"  teacher progress: {i}/{len(queries)}, "
                      f"{written} written, {skipped} skipped, ${total_cost:.2f} spent",
                      flush=True)
    return written, skipped, total_cost


def main() -> int:
    p = argparse.ArgumentParser(description="Generate synthetic distillation data")
    p.add_argument("--out", default=None)
    p.add_argument("--per-seed", type=int, default=DEFAULT_EXPANSIONS)
    p.add_argument("--domains", type=int, default=DEFAULT_DOMAINS,
                   help=f"How many domains from seeds.DOMAINS (max {len(DOMAINS)})")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    p.add_argument("--test", action="store_true",
                   help="Run a 5-pair test instead of full pipeline (~$0.10)")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--execute", dest="dry_run", action="store_false",
                   help="ACTUALLY make API calls. Default: dry-run.")
    args = p.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else DATA_DIR / f"synthetic-{dt.date.today()}.jsonl"

    domains_used = DOMAINS[:args.domains]
    total_seeds = sum(len(v) for v in ALL_SEEDS.values())
    total_expansion_calls = total_seeds * len(domains_used)
    total_queries = total_expansion_calls * args.per_seed
    expansion_cost = total_expansion_calls * 0.002  # qwen3-coder-flash, small response
    teacher_cost = total_queries * 0.01
    total_cost = expansion_cost + teacher_cost
    est_minutes = (total_queries * 75) / 60 / args.workers

    print("Plan:")
    print(f"  Seeds: {total_seeds} across {len(ALL_SEEDS)} templates")
    print(f"  Domains: {len(domains_used)} (of {len(DOMAINS)} available)")
    print(f"  Per-seed expansions: {args.per_seed}")
    print(f"  Expansion calls: {total_expansion_calls} × ${0.002:.3f} = ${expansion_cost:.2f}")
    print(f"  Teacher calls: {total_queries} × ${0.01:.3f} = ${teacher_cost:.2f}")
    print(f"  Total cost: ~${total_cost:.2f}")
    print(f"  Concurrent workers: {args.workers}")
    print(f"  Estimated time: ~{est_minutes:.0f} min")
    print(f"  Output: {out}")

    if args.test:
        print("\n[TEST MODE] generating 5 pairs end-to-end…")
        # Pick 5 (seed, domain) combos
        test_tasks = [
            (t, 0, ALL_SEEDS[t][0], domains_used[0])
            for t in list(ALL_SEEDS.keys())[:5]
        ]
        expansions = []
        for template, seed_idx, seed, domain in test_tasks:
            try:
                qs = expand_seed(seed, template, domain, 1)
                if qs:
                    expansions.append({"template": template, "domain": domain,
                                       "seed_idx": seed_idx, "query": qs[0]})
                    print(f"  expanded: [{template}] {qs[0][:80]}…")
            except Exception as e:
                print(f"  expansion failed: {e}")
        if not expansions:
            sys.exit("No expansions succeeded; check OPENROUTER_API_KEY")
        print(f"\nRunning teacher on {len(expansions)} test queries…")
        test_out = DATA_DIR / f"test-{dt.date.today()}.jsonl"
        written, skipped, cost = collect_teacher_outputs(expansions, test_out, max_workers=3)
        print(f"\nTest complete: {written} written, {skipped} skipped, ${cost:.4f} spent")
        print(f"Output: {test_out}")
        return 0

    if args.dry_run:
        print("\n[DRY-RUN] No API calls made. Re-run with --execute to fire.")
        print("Or use --test for a 5-pair sanity check (~$0.10).")
        return 0

    # Full execution
    print(f"\n[EXECUTE] firing full pipeline…")
    t0 = time.time()
    expansions = collect_expansions(ALL_SEEDS, domains_used, args.per_seed, max_workers=4)
    if not expansions:
        sys.exit("No expansions succeeded; check OPENROUTER_API_KEY + retry")
    print(f"\nRunning teacher on {len(expansions)} queries…")
    written, skipped, cost = collect_teacher_outputs(expansions, out, max_workers=args.workers)
    elapsed = (time.time() - t0) / 60
    print(f"\nDone in {elapsed:.1f} min: {written} pairs written, {skipped} skipped, "
          f"${cost:.2f} teacher cost.")
    print(f"Output: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
