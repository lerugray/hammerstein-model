#!/usr/bin/env python3
"""Phase 1.5 precision test for the corpus-id intersection heuristic.

Default: pick the N most recent audit-this-plan queries from the main log,
replay each through hp's filter (no inference), and emit a markdown
scoring sheet to scoring/precision-<DATE>.md. Operator fills in `[x]` for
each match they judge structurally relevant.

`--score <path>`: parse a filled sheet and print precision (% of injected
matches judged structurally relevant). Gate: ≥60% to commit to the
intersection heuristic; <60% triggers fallback to recency+keyword filter.

Per DESIGN.md Phase 1.5.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hp_lib import (  # noqa: E402
    DEFAULT_MAX_PREAMBLE_TOKENS, MAIN_LOG, entry_ids, fetch_corpus_ids,
    filter_similar, format_entry, read_jsonl, select_for_preamble,
)

DEFAULT_N = 10
DEFAULT_TEMPLATE = "audit-this-plan"
SCORING_DIR = Path(__file__).resolve().parent.parent / "scoring"
PRECISION_THRESHOLD = 0.60


def pick_recent_queries(entries: list[dict], n: int, template: str) -> list[dict]:
    """Most-recent n entries matching template, excluding hp's own subprocess
    calls (heuristic: skip entries whose query starts with 'contract pre-flight')."""
    audits = [e for e in entries if e.get("template") == template
              and not (e.get("query") or "").startswith("contract pre-flight")]
    audits.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return audits[:n]


def generate_sheet(n: int, template: str, max_tokens: int) -> Path:
    main_entries = read_jsonl(MAIN_LOG)
    targets = pick_recent_queries(main_entries, n, template)
    if not targets:
        sys.exit(f"precision_test: no entries found with template={template}")

    SCORING_DIR.mkdir(exist_ok=True)
    out = SCORING_DIR / f"precision-{dt.datetime.now().strftime('%Y-%m-%d')}.md"

    lines = [
        f"# hp precision test — {dt.datetime.now().strftime('%Y-%m-%d')}",
        "",
        f"Picked {len(targets)} recent {template} queries. For each, the matches",
        "the corpus-id intersection filter would inject are listed below.",
        "",
        "**Score:** for each match, change `[ ]` → `[x]` if structurally relevant",
        "(same failure pattern, not just topically similar). Leave `[ ]` if noise.",
        "",
        f"Then run: `python tools/precision_test.py --score {out.relative_to(Path.cwd())}`",
        "",
        f"Gate: ≥{int(PRECISION_THRESHOLD*100)}% to commit to the intersection heuristic.",
        "",
    ]

    for i, target in enumerate(targets, 1):
        target_query = (target.get("query") or "").strip().replace("\n", " ")
        target_query_short = target_query[:200] + ("…" if len(target_query) > 200 else "")
        try:
            new_ids = set(fetch_corpus_ids(target_query, template))
        except Exception as e:
            lines.append(f"## Query {i}: ERROR fetching corpus IDs ({e})\n")
            continue

        # Exclude the target itself from the pool
        pool = [e for e in main_entries if e.get("timestamp") != target.get("timestamp")]
        matches = filter_similar(pool, new_ids, min_match=2)
        selected = select_for_preamble(matches, new_ids, max_tokens)

        lines.append(f"## Query {i} — {target.get('timestamp', '?')}")
        lines.append("")
        lines.append(f"**Target query (excerpt):** {target_query_short}")
        lines.append("")
        lines.append(f"**Target retrieved corpus IDs:** {sorted(new_ids)}")
        lines.append(f"**Matched prior entries:** {len(selected)}")
        lines.append("")

        if not selected:
            lines.append("_(no matches at ≥2 or ≥1 fallback — nothing to score)_")
            lines.append("")
            continue

        for j, match in enumerate(selected, 1):
            shared = sorted(entry_ids(match) & new_ids)
            mq = (match.get("query") or "").strip().replace("\n", " ")
            mq_short = mq[:150] + ("…" if len(mq) > 150 else "")
            lines.append(f"- [ ] **match {i}.{j}** — {match.get('timestamp', '?')} — shared IDs: {shared}")
            lines.append(f"  - prior query: {mq_short}")
        lines.append("")

    out.write_text("\n".join(lines))
    print(f"precision_test: wrote {out}")
    return out


CHECKBOX_RE = re.compile(r"^\s*-\s*\[(x|X| )\]\s*\*\*match\s+\d+\.\d+\*\*", re.MULTILINE)


def score_sheet(path: Path) -> int:
    text = path.read_text()
    boxes = CHECKBOX_RE.findall(text)
    if not boxes:
        sys.exit(f"precision_test: no match checkboxes found in {path}")
    total = len(boxes)
    relevant = sum(1 for b in boxes if b.lower() == "x")
    precision = relevant / total
    print(f"precision_test: {relevant}/{total} matches scored relevant ({precision*100:.1f}%)")
    print(f"  threshold: {PRECISION_THRESHOLD*100:.0f}%")
    if precision >= PRECISION_THRESHOLD:
        print("  verdict: PASS — commit to intersection heuristic")
        return 0
    print("  verdict: FAIL — fall back to recency+keyword filter")
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 1.5 precision test for hp")
    p.add_argument("-n", type=int, default=DEFAULT_N, help=f"Queries to test (default {DEFAULT_N}).")
    p.add_argument("--template", default=DEFAULT_TEMPLATE)
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_PREAMBLE_TOKENS)
    p.add_argument("--score", type=Path, default=None,
                   help="Score a filled sheet instead of generating one.")
    args = p.parse_args()

    if args.score:
        return score_sheet(args.score)
    generate_sheet(args.n, args.template, args.max_tokens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
