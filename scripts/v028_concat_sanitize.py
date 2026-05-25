#!/usr/bin/env python3
"""v0.2.8 clean-rebase additions concat + sanitize.

Per orchestrator handoff
(docs/handoffs/v0.2.8-rebase-from-privategs-orchestrator-2026-05-25.md):
single-pass training from v0.2.6.2 base with ALL accumulated v0.2.7.x
additions, with three corrections to PC's hm-013 inclusion list:

1. DROP v0.2.7.2-tool-use-judgment-xml.jsonl (empirically broken on v0.2.7.2)
   KEEP v0.2.7-tool-use-judgment.jsonl (original structured tool_calls format —
   the best-scoring tool-use we've achieved at 50% on v0.2.7)
2. Reduce []-emission oversample from 9-10x → 3x (gradient war fix)
3. Optionally add new high-signal extraction reinforcement (5-8 pairs at 5x)

Expected total: ~600 examples (vs v0.2.7.2's 933 at inflated oversample).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# (filename, oversample_factor) — orchestrator's corrected inclusion list
ADDITIONS_FILES: list[tuple[str, int]] = [
    # v0.2.7 axes
    ("v0.2.7-anti-meta-leakage-v2.jsonl",                   5),
    ("v0.2.7-register-classifier.jsonl",                    5),
    ("v0.2.6.1-extraction-low-signal-additions.jsonl",      3),  # was 9x — gradient war fix
    ("v0.2.6.2-extraction-low-signal-reinforcement.jsonl",  3),  # was 9x — gradient war fix
    ("v0.2.7-real-usage-failures.jsonl",                    5),
    ("v0.2.7-tool-routing-alignment.jsonl",                 5),
    ("v0.2.7-canonical-positives.jsonl",                    5),
    ("v0.2.7-interface-aware-close.jsonl",                  5),
    ("v0.2.7-asymmetric-engagement-fix.jsonl",              5),
    ("v0.2.7-tool-use-judgment.jsonl",                      5),  # KEEP original (NOT XML version)
    # v0.2.7.1 fix axes — dropped from 10x → 5x (anti-fab) and 3x ([]-emission)
    ("v0.2.7.1-anti-self-state-fabrication.jsonl",          5),  # was 10x
    ("v0.2.7.1-low-signal-extraction-edges.jsonl",          3),  # was 10x — gradient war fix
    ("v0.2.7.1-anti-meta-leakage-v3.jsonl",                 5),
    # v0.2.7.2 — only pure-question file kept (XML tool-use EXCLUDED)
    ("v0.2.7.2-pure-question-extraction-edges.jsonl",       3),  # was 10x — gradient war fix
    # v0.2.8 — high-signal extraction reinforcement (optional extra margin)
    ("v0.2.8-high-signal-extraction-reinforcement.jsonl",   5),
]

OUT = DATA_DIR / "ray-stack-sft-v0.2.8-additions.jsonl"

SANITIZE_REGEX = re.compile(
    r"(Jason|Ricky|Kunal|James Rodgers|Ryan Fyr|sk-[a-zA-Z0-9]{10,}|hf_[A-Za-z0-9]+)"
)

MEDICAL_BLOCKLIST = [
    "venlafaxine", "ssri", "snri", "prescription", "dosage",
    "discontinuation syndrome", "antidepressant", "anti-depressant",
]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sanitize_line(obj: dict) -> tuple[bool, str | None]:
    text = json.dumps(obj, ensure_ascii=False)
    m = SANITIZE_REGEX.search(text)
    if m:
        return False, f"regex: {m.group(0)[:40]}"
    text_lower = text.lower()
    for kw in MEDICAL_BLOCKLIST:
        if kw in text_lower:
            return False, f"medical: {kw}"
    return True, None


def main() -> int:
    counts = {
        "input_total":      0,
        "dropped_regex":    0,
        "dropped_medical":  0,
        "stripped_metadata": 0,
        "written":          0,
        "per_source":       {},
    }

    with OUT.open("w", encoding="utf-8") as fout:
        for fname, oversample in ADDITIONS_FILES:
            src = DATA_DIR / fname
            rows = load_jsonl(src)
            n_in = len(rows)

            kept: list[dict] = []
            for obj in rows:
                counts["input_total"] += 1
                keep, reason = sanitize_line(obj)
                if not keep:
                    if reason and "regex" in reason:
                        counts["dropped_regex"] += 1
                    else:
                        counts["dropped_medical"] += 1
                    continue
                if "_metadata" in obj:
                    obj.pop("_metadata", None)
                    counts["stripped_metadata"] += 1
                kept.append(obj)

            for _ in range(oversample):
                for obj in kept:
                    fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                    counts["written"] += 1

            counts["per_source"][fname] = {
                "in_raw":     n_in,
                "kept":       len(kept),
                "oversample": oversample,
                "out_total":  len(kept) * oversample,
            }

    print(f"v0.2.8 additions assembled at {OUT}")
    print(f"  Input total:                     {counts['input_total']}")
    print(f"  Dropped (regex):                 {counts['dropped_regex']}")
    print(f"  Dropped (medical blocklist):     {counts['dropped_medical']}")
    print(f"  Stripped _metadata:              {counts['stripped_metadata']}")
    print(f"  Written (with oversample):       {counts['written']}")
    print()
    print(f"  Per-source breakdown:")
    print(f"    {'file':55s} {'raw':>5s} {'kept':>5s} {'x':>3s} {'out':>6s}")
    for name, info in counts["per_source"].items():
        print(f"    {name:55s} {info['in_raw']:5d} {info['kept']:5d} {info['oversample']:3d} {info['out_total']:6d}")

    out_text = OUT.read_text(encoding="utf-8")
    m = SANITIZE_REGEX.search(out_text)
    if m:
        print(f"\nWARN: regex still matches: {m.group(0)}")
        return 1
    print("\nSanitization clean.")

    # Sanity check: count []-emission examples vs high-signal positive examples
    empty_count = 0
    nonempty_count = 0
    for line in out_text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msgs = obj.get("messages", [])
        # Look for assistant turns that are extraction outputs (JSON array)
        for m in msgs:
            if m.get("role") == "assistant":
                c = m.get("content", "").strip()
                if c == "[]":
                    empty_count += 1
                elif c.startswith("[") and c.endswith("]") and "\"type\"" in c:
                    nonempty_count += 1
    print(f"\n  Extraction ratio check:")
    print(f"    []-emission examples:    {empty_count}")
    print(f"    Non-empty JSON examples: {nonempty_count}")
    if empty_count > 0 and nonempty_count > 0:
        print(f"    Ratio []:non-empty:      {empty_count/nonempty_count:.1f}:1")
        print(f"    (v0.2.7.2 was ~11:1 which caused gradient war — target <5:1)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
