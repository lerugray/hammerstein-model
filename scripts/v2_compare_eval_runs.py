#!/usr/bin/env python3
"""Compare two eval-results JSONs side by side. Designed for v1 baseline
vs v0.2 post-train comparison; works for any pair output by
v2_eval_failure_modes.py.

Usage:
  python scripts/v2_compare_eval_runs.py \
      data/eval-hammerstein-7b-2026-05-22-v1-baseline.json \
      data/eval-hammerstein-7b-v02-<DATE>-v02-post-train.json

Output: side-by-side per-prompt summary, aggregated failure-mode deltas,
register-mismatch deltas, and clean-pass deltas. Plus a full markdown
report to stdout suitable for piping into the session note or a PR
description.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_pair(a: dict, b: dict, name_a: str, name_b: str) -> str:
    out: list[str] = []
    out.append(f"# Eval comparison — {name_a} vs {name_b}\n")
    out.append(f"- **{name_a}** model: `{a.get('model')}` tag: `{a.get('tag') or '-'}`")
    out.append(f"- **{name_b}** model: `{b.get('model')}` tag: `{b.get('tag') or '-'}`")
    out.append("")

    # Aggregate counts
    totals_a = a.get("total_prompts", 0)
    totals_b = b.get("total_prompts", 0)
    clean_a = a.get("clean_passes", 0)
    clean_b = b.get("clean_passes", 0)
    mismatch_a = a.get("register_mismatches", 0)
    mismatch_b = b.get("register_mismatches", 0)

    out.append("## Aggregate")
    out.append("")
    out.append(f"|  | {name_a} | {name_b} | Δ |")
    out.append("|---|---:|---:|---:|")
    out.append(f"| Total prompts | {totals_a} | {totals_b} | {totals_b - totals_a:+d} |")
    out.append(f"| Clean passes | {clean_a} | {clean_b} | {clean_b - clean_a:+d} |")
    out.append(f"| Register mismatches | {mismatch_a} | {mismatch_b} | {mismatch_b - mismatch_a:+d} |")
    out.append("")

    # Failure-mode counts
    fmc_a = a.get("failure_mode_counts", {}) or {}
    fmc_b = b.get("failure_mode_counts", {}) or {}
    all_modes = sorted(set(fmc_a) | set(fmc_b))
    out.append("## Failure-mode counts")
    out.append("")
    out.append(f"| Mode | {name_a} | {name_b} | Δ |")
    out.append("|---|---:|---:|---:|")
    for m in all_modes:
        va, vb = fmc_a.get(m, 0), fmc_b.get(m, 0)
        out.append(f"| `{m}` | {va} | {vb} | {vb - va:+d} |")
    if not all_modes:
        out.append("| (no failure modes flagged in either run) | — | — | — |")
    out.append("")

    # Per-prompt
    out.append("## Per-prompt")
    out.append("")
    out.append(f"| Prompt ID | {name_a} flags | {name_b} flags | {name_a} reg | {name_b} reg |")
    out.append("|---|---|---|---|---|")
    a_by_id = {r.get("prompt_id"): r for r in a.get("results", []) if "prompt_id" in r}
    b_by_id = {r.get("prompt_id"): r for r in b.get("results", []) if "prompt_id" in r}
    all_ids = sorted(set(a_by_id) | set(b_by_id))
    for pid in all_ids:
        ra = a_by_id.get(pid)
        rb = b_by_id.get(pid)
        flags_a = "+".join(ra.get("flags", []) or ["clean"]) if ra else "-"
        flags_b = "+".join(rb.get("flags", []) or ["clean"]) if rb else "-"
        reg_a = f"{ra.get('detected_register')}/{ra.get('expected_register')}" if ra else "-"
        reg_b = f"{rb.get('detected_register')}/{rb.get('expected_register')}" if rb else "-"
        if ra and ra.get("register_mismatch"):
            reg_a += " ⚠"
        if rb and rb.get("register_mismatch"):
            reg_b += " ⚠"
        out.append(f"| `{pid}` | {flags_a} | {flags_b} | {reg_a} | {reg_b} |")
    out.append("")

    # Verdict heuristic
    clean_delta = clean_b - clean_a
    mismatch_delta = mismatch_b - mismatch_a
    total_flags_a = sum(fmc_a.values())
    total_flags_b = sum(fmc_b.values())
    flag_delta = total_flags_b - total_flags_a

    out.append("## Verdict heuristic")
    out.append("")
    out.append(f"- Clean-pass delta: {clean_delta:+d}")
    out.append(f"- Register-mismatch delta: {mismatch_delta:+d}")
    out.append(f"- Total flag count delta: {flag_delta:+d}")
    out.append("")
    if clean_delta > 0 and flag_delta < 0 and mismatch_delta <= 0:
        out.append("**Direction: better.** Ship-candidate worth a closer manual read.")
    elif clean_delta < 0 or flag_delta > 0 or mismatch_delta > 0:
        out.append("**Direction: worse.** Iterate before shipping; check the diff per-prompt.")
    else:
        out.append("**Direction: mixed or neutral.** Manual read on the raw responses.")
    out.append("")
    out.append("Heuristics are coarse; the raw responses in the JSONs are the truth.")

    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("baseline", help="Path to baseline eval JSON (v1)")
    p.add_argument("candidate", help="Path to candidate eval JSON (v0.2)")
    p.add_argument("--name-a", default="baseline", help="Label for the baseline column")
    p.add_argument("--name-b", default="candidate", help="Label for the candidate column")
    p.add_argument("--out", default=None,
                   help="Optional markdown output path; if absent, writes to stdout")
    args = p.parse_args()

    a = load(Path(args.baseline))
    b = load(Path(args.candidate))
    md = summarize_pair(a, b, args.name_a, args.name_b)

    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
