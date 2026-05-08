#!/usr/bin/env python3
"""Generate synthetic distillation data: seed → expansion → teacher.

Pipeline:
  1. Load seeds from seeds.py
  2. For each seed, ask Qwen3.6 to produce N concrete variations across
     different domains (placeholder substitution, not just rephrasing).
  3. For each variation, run the teacher (hammerstein CLI = Qwen3.6 +
     framework + corpus retrieval) to produce a (query, response) pair.
  4. Filter for quality: structural-shape markers must be present.
  5. Write to data/synthetic-<DATE>.jsonl with full metadata.

Cost (estimate):
  - Expansion calls: 30 seeds × 1 call = 30 × $0.005 (small response) = $0.15
  - Teacher calls: ~2000 expansions × $0.01 = $20
  - Total: ~$20 per full run

This is the ONE expensive step in the pipeline. Per MODEL-EXPERIMENT.md
ship gate, requires Ray's explicit approval before running. Default
behavior is dry-run (prints plan, no API calls).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from hp_lib import HAMMERSTEIN_BIN  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seeds import ALL_SEEDS, DOMAINS  # noqa: E402

DATA_DIR = ROOT / "tools" / "distill" / "data"
EXPANSIONS_PER_SEED = 6  # 6 expansions × 12 domains × 30 seeds = ~2160 prompts
QUALITY_MARKERS = [
    "load-bearing", "structural", "counter-observation", "verification",
    "failure mode", "trade", "scope",
]
MIN_QUALITY_MARKERS = 2  # response must contain at least this many


def expand_seed(seed: str, template: str, domain: str, n: int) -> list[str]:
    """Use Qwen3.6 (via hammerstein --show-prompt is too cheap; use direct
    OpenRouter for expansion). Returns N concrete prompts."""
    # Stub: this would call OpenRouter directly with a meta-prompt asking
    # Qwen to generate N concrete variations of the seed within the domain.
    # Returning a placeholder list for the dry-run; the real implementation
    # plugs in OpenRouter.
    return [
        f"[{template} | {domain} | seed={seed[:40]}... | variant {i+1}/{n}]"
        for i in range(n)
    ]


def call_teacher(query: str, template: str, timeout: int = 120) -> dict:
    """Call hammerstein CLI to get teacher response."""
    cmd = [HAMMERSTEIN_BIN, "--template", template, query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if r.returncode != 0:
        return {"error": r.stderr.strip(), "stdout": r.stdout, "rc": r.returncode}
    # Parse cost/latency from stderr header
    cost_m = re.search(r"cost_usd=\$(\d+\.\d+)", r.stderr)
    latency_m = re.search(r"latency_ms=(\d+)", r.stderr)
    return {
        "response": r.stdout.strip(),
        "cost_usd": float(cost_m.group(1)) if cost_m else None,
        "latency_ms": int(latency_m.group(1)) if latency_m else None,
    }


def passes_quality_filter(response: str) -> bool:
    """Lightweight structural check — does the response have the framework
    markers? Per MODEL-EXPERIMENT.md eval methodology."""
    text = response.lower()
    hits = sum(1 for m in QUALITY_MARKERS if m in text)
    return hits >= MIN_QUALITY_MARKERS and len(response) >= 200


def main() -> int:
    p = argparse.ArgumentParser(description="Generate synthetic distillation data")
    p.add_argument("--out", default=None, help="Output JSONL path")
    p.add_argument("--per-seed", type=int, default=EXPANSIONS_PER_SEED)
    p.add_argument("--limit", type=int, default=None,
                   help="Cap total expansions (for cheap test runs)")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Print plan without calling APIs (default)")
    p.add_argument("--execute", dest="dry_run", action="store_false",
                   help="ACTUALLY make API calls. Default: dry-run.")
    args = p.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else DATA_DIR / f"synthetic-{dt.date.today()}.jsonl"

    total_seeds = sum(len(v) for v in ALL_SEEDS.values())
    total_expansions = total_seeds * len(DOMAINS) * args.per_seed
    if args.limit:
        total_expansions = min(total_expansions, args.limit)
    estimated_cost = total_expansions * 0.01

    print(f"Plan:")
    print(f"  Seeds: {total_seeds} across {len(ALL_SEEDS)} templates")
    print(f"  Domains: {len(DOMAINS)}")
    print(f"  Per-seed expansions: {args.per_seed}")
    print(f"  Total queries: {total_expansions}")
    print(f"  Estimated cost: ${estimated_cost:.2f}")
    print(f"  Output: {out}")

    if args.dry_run:
        print("\n[DRY-RUN] No API calls made. Re-run with --execute to fire.")
        return 0

    # Real execution — never auto-fire on import; this branch is only entered
    # when --execute is explicitly passed.
    print(f"\n[EXECUTE] generating {total_expansions} pairs to {out}…")
    written, skipped, total_cost = 0, 0, 0.0
    with out.open("w") as f:
        for template, seeds in ALL_SEEDS.items():
            for seed_idx, seed in enumerate(seeds):
                for domain in DOMAINS:
                    if args.limit and written >= args.limit:
                        break
                    expansions = expand_seed(seed, template, domain, args.per_seed)
                    for query in expansions:
                        result = call_teacher(query, template)
                        if "error" in result:
                            skipped += 1
                            continue
                        if not passes_quality_filter(result.get("response", "")):
                            skipped += 1
                            continue
                        record = {
                            "template": template,
                            "domain": domain,
                            "seed_idx": seed_idx,
                            "query": query,
                            "response": result["response"],
                            "cost_usd": result.get("cost_usd"),
                            "latency_ms": result.get("latency_ms"),
                            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                        }
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        f.flush()
                        written += 1
                        total_cost += result.get("cost_usd") or 0
                        if written % 50 == 0:
                            print(f"  {written} written, {skipped} skipped, ${total_cost:.2f} spent")

    print(f"\nDone: {written} pairs written, {skipped} skipped, ${total_cost:.2f} total cost.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
