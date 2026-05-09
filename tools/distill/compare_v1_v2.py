#!/usr/bin/env python3
"""3-way comparison: v1 (re-eval, same env) vs v2a (data scaling) vs v2b (teacher swap).

Run after the pod produces:
  - tools/distill/data/eval-v1-rerun-<DATE>.jsonl
  - tools/distill/data/eval-v2a-<DATE>.jsonl
  - tools/distill/data/eval-v2b-<DATE>.jsonl  (optional)

Outputs a markdown summary comparing raw marker counts (uncapped) since
v1's structural_score saturated at 1.0 on the capped metric.

Decision gates (per-variant, taking max of v2a or v2b deltas):
  - Launch swap (Δ student ≥ +0.5 markers vs v1):
    push winner to HF + GGUF + model card by Sunday evening
  - Post-launch follow-up (Δ ∈ (+0.1, +0.5)): v1 launches Tue, v2 next week
  - No-go (|Δ| ≤ 0.1): launch v1 only
  - Revert (Δ < -0.1): investigate
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "tools" / "distill" / "data"

QM = [
    "load-bearing", "structural", "counter-observation", "verification",
    "failure mode", "trade", "scope", "stupid-industrious", "clever-lazy",
    "clever-industrious", "stupid-lazy",
]


def hits(text: str) -> int:
    t = text.lower()
    return sum(1 for m in QM if m in t)


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def split_by_kind(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    strategic, forgetting = [], []
    for r in rows:
        if r.get("_forgetting_check"):
            forgetting.append(r)
        else:
            strategic.append(r)
    return strategic, forgetting


def per_condition_hits(rows: list[dict]) -> dict[str, list[int]]:
    out = {"gold": [], "student": [], "ablation": [], "vanilla": []}
    for r in rows:
        for c in out:
            x = r.get(c, {})
            if "response" in x:
                out[c].append(hits(x["response"]))
    return out


def avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def fmt_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    lines = []
    for i, row in enumerate(rows):
        lines.append("| " + " | ".join(str(c).ljust(widths[j]) for j, c in enumerate(row)) + " |")
        if i == 0:
            lines.append("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--v1", default=str(DATA_DIR / "eval-v1-rerun-2026-05-09.jsonl"))
    p.add_argument("--v2a", default=str(DATA_DIR / "eval-v2a-2026-05-09.jsonl"))
    p.add_argument("--v2b", default=str(DATA_DIR / "eval-v2b-2026-05-09.jsonl"),
                   help="Optional; pass --no-v2b to compare v1 vs v2a only")
    p.add_argument("--no-v2b", action="store_true",
                   help="Skip v2b column (when only v2a was trained)")
    p.add_argument("--out", default=str(DATA_DIR / "compare-v1-v2-2026-05-09.md"))
    args = p.parse_args()

    v1_rows = load(Path(args.v1))
    v2a_rows = load(Path(args.v2a))
    v2b_rows = [] if args.no_v2b else load(Path(args.v2b))
    if not v1_rows:
        sys.exit(f"missing: {args.v1}")
    if not v2a_rows:
        sys.exit(f"missing: {args.v2a}")
    has_v2b = bool(v2b_rows)

    v1_strat, v1_forget = split_by_kind(v1_rows)
    v2a_strat, v2a_forget = split_by_kind(v2a_rows)
    v2b_strat, v2b_forget = split_by_kind(v2b_rows) if has_v2b else ([], [])

    v1_hits = per_condition_hits(v1_strat)
    v2a_hits = per_condition_hits(v2a_strat)
    v2b_hits = per_condition_hits(v2b_strat) if has_v2b else {}

    lines = ["# v1 vs v2a vs v2b comparison — 2026-05-09", ""]
    lines.append(f"v1 source:  `{args.v1}`")
    lines.append(f"v2a source: `{args.v2a}`  (qwen3.6-plus teacher, 1500 pairs)")
    if has_v2b:
        lines.append(f"v2b source: `{args.v2b}`  (DeepSeek v4-pro teacher, 1500 pairs)")
    lines.append("")
    lines.append("Metric: **raw framework-marker count per response** (uncapped).")
    lines.append("v1 structural_score saturated at 1.0; raw counts give the meaningful signal.")
    lines.append("")
    lines.append(f"## Strategic prompts (n={len(v1_strat)})")
    lines.append("")
    if has_v2b:
        table = [["Condition", "v1", "v2a", "v2b", "v2a-v1", "v2b-v1"]]
        for c in ["gold", "student", "ablation", "vanilla"]:
            a = avg(v1_hits[c])
            b = avg(v2a_hits[c])
            d = avg(v2b_hits[c])
            table.append([c, f"{a:.2f}", f"{b:.2f}", f"{d:.2f}",
                          f"{b-a:+.2f}", f"{d-a:+.2f}"])
    else:
        table = [["Condition", "v1", "v2a", "Δ (v2a-v1)"]]
        for c in ["gold", "student", "ablation", "vanilla"]:
            a = avg(v1_hits[c])
            b = avg(v2a_hits[c])
            table.append([c, f"{a:.2f}", f"{b:.2f}", f"{b-a:+.2f}"])
    lines.append(fmt_table(table))
    lines.append("")

    # Adapter signal (student vs ablation) per variant
    v1_sa = avg(v1_hits["student"]) - avg(v1_hits["ablation"])
    v2a_sa = avg(v2a_hits["student"]) - avg(v2a_hits["ablation"])
    v2b_sa = avg(v2b_hits["student"]) - avg(v2b_hits["ablation"]) if has_v2b else 0
    lines.append("## Adapter signal (student vs ablation)")
    lines.append("")
    lines.append(f"- v1:  Δ {v1_sa:+.2f} markers")
    lines.append(f"- v2a: Δ {v2a_sa:+.2f} markers ({v2a_sa - v1_sa:+.2f} vs v1)")
    if has_v2b:
        lines.append(f"- v2b: Δ {v2b_sa:+.2f} markers ({v2b_sa - v1_sa:+.2f} vs v1)")
    lines.append("")
    lines.append("Higher = adapter contributes more beyond what a system prompt alone provides.")
    lines.append("")

    if v1_forget and (v2a_forget or v2b_forget):
        lines.append(f"## Forgetting-check prompts (n={len(v1_forget)}) — LOWER is healthier")
        lines.append("")
        v1_fh = per_condition_hits(v1_forget)
        v2a_fh = per_condition_hits(v2a_forget)
        v2b_fh = per_condition_hits(v2b_forget) if has_v2b else {}
        if has_v2b:
            ftable = [["Condition", "v1", "v2a", "v2b"]]
            for c in ["student", "ablation", "vanilla"]:
                ftable.append([c, f"{avg(v1_fh[c]):.2f}", f"{avg(v2a_fh[c]):.2f}",
                              f"{avg(v2b_fh[c]):.2f}"])
        else:
            ftable = [["Condition", "v1", "v2a"]]
            for c in ["student", "ablation", "vanilla"]:
                ftable.append([c, f"{avg(v1_fh[c]):.2f}", f"{avg(v2a_fh[c]):.2f}"])
        lines.append(fmt_table(ftable))
        lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")
    v2a_student_delta = avg(v2a_hits["student"]) - avg(v1_hits["student"])
    v2b_student_delta = (avg(v2b_hits["student"]) - avg(v1_hits["student"])) if has_v2b else None

    deltas = [("v2a", v2a_student_delta)]
    if has_v2b:
        deltas.append(("v2b", v2b_student_delta))
    deltas.sort(key=lambda x: -x[1])
    winner_name, winner_delta = deltas[0]

    lines.append(f"Best variant: **{winner_name}** with Δ {winner_delta:+.2f} markers vs v1 student.")
    lines.append("")

    if winner_delta >= 0.5:
        lines.append(f"**LAUNCH SWAP → {winner_name}**. Materially beats v1. "
                     f"Push to HF + GGUF + update model card by Sunday evening.")
    elif winner_delta > 0.1:
        lines.append(f"**POST-LAUNCH FOLLOW-UP → {winner_name}**. Improves over v1 by "
                     f"{winner_delta:+.2f} markers, below the +0.5 launch-swap bar. "
                     "Launch v1 Tue; ship v2 next week.")
    elif abs(winner_delta) <= 0.1:
        lines.append(f"**NO-GO** — best variant ({winner_name}) within ±0.1 of v1. "
                     "Data scaling and/or teacher quality didn't move the needle on the "
                     "current eval. Launch v1; next experiment is base model bump (14B).")
    else:
        lines.append(f"**REVERT** — even best variant underperforms v1 by {winner_delta:+.2f}. "
                     "Investigate before any swap.")

    if has_v2b:
        a, b = v2a_student_delta, v2b_student_delta
        if abs(a - b) <= 0.2:
            lines.append("")
            lines.append(f"v2a ({a:+.2f}) and v2b ({b:+.2f}) within 0.2 of each other — "
                         "data scaling and teacher quality contribute roughly equally. "
                         "If launching, prefer v2a (cheaper to reproduce).")
        elif a > b:
            lines.append("")
            lines.append(f"**Data scaling > teacher swap.** v2a ({a:+.2f}) beats v2b ({b:+.2f}). "
                         "v3 should keep qwen3.6-plus, scale data further or bump base model.")
        else:
            lines.append("")
            lines.append(f"**Teacher swap > data scaling.** v2b ({b:+.2f}) beats v2a ({a:+.2f}). "
                         "v3 should use DeepSeek v4-pro teacher with larger dataset.")

    out_path = Path(args.out)
    out_path.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[wrote {out_path}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
