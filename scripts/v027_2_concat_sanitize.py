#!/usr/bin/env python3
"""v0.2.7.2 additions concat + sanitize.

Iteration on v0.2.7.1 per orchestrator handoff
(docs/handoffs/v0.2.7.2-from-privategs-orchestrator-2026-05-25.md).

Primary fix: tool-use XML — rewrite the 10 v0.2.7-tool-use-judgment.jsonl
pairs with <tool_call>{"name":...,"arguments":{...}}</tool_call> embedded
in assistant content (the model emits XML in text, not via the chat
template's tool_calls field).

Secondary fix: pure-question extraction — 5 anti-pairs for "named thing
in pure question + ack/defer" → [] discrimination (ex-10 shape).

CRITICAL: v0.2.7-tool-use-judgment.jsonl (the OLD format) is EXCLUDED
from the concat to avoid training on conflicting tool-call formats.
The XML version replaces it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# (filename, oversample_factor)
ADDITIONS_FILES: list[tuple[str, int]] = [
    # v0.2.7 axes (same as v027_1_concat_sanitize.py, MINUS the OLD tool-use
    # file which is replaced by the XML version below)
    ("v0.2.7-anti-meta-leakage-v2.jsonl",                  5),
    ("v0.2.7-register-classifier.jsonl",                    5),
    ("v0.2.6.1-extraction-low-signal-additions.jsonl",      9),
    ("v0.2.6.2-extraction-low-signal-reinforcement.jsonl",  9),
    ("v0.2.7-real-usage-failures.jsonl",                    5),
    ("v0.2.7-tool-routing-alignment.jsonl",                 5),
    ("v0.2.7-canonical-positives.jsonl",                    5),
    ("v0.2.7-interface-aware-close.jsonl",                  5),
    ("v0.2.7-asymmetric-engagement-fix.jsonl",              5),
    # NOTE: v0.2.7-tool-use-judgment.jsonl INTENTIONALLY EXCLUDED — replaced
    # by v0.2.7.2-tool-use-judgment-xml.jsonl below.

    # v0.2.7.1 fix axes (carryover at original oversample)
    ("v0.2.7.1-anti-self-state-fabrication.jsonl",         10),
    ("v0.2.7.1-low-signal-extraction-edges.jsonl",         10),
    ("v0.2.7.1-anti-meta-leakage-v3.jsonl",                10),

    # v0.2.7.2 fix axes — primary + secondary, both 10x
    ("v0.2.7.2-tool-use-judgment-xml.jsonl",               10),  # primary
    ("v0.2.7.2-pure-question-extraction-edges.jsonl",      10),  # secondary
]

OUT = DATA_DIR / "ray-stack-sft-v0.2.7.2-additions.jsonl"

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

    print(f"v0.2.7.2 additions assembled at {OUT}")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
