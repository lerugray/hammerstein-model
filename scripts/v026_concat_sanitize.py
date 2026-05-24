#!/usr/bin/env python3
"""v0.2.6 additions concat + sanitize.

Builds data/ray-stack-sft-v0.2.6-additions.jsonl by concatenating:
- data/ray-stack-sft-v0.2.5-additions.jsonl  (645 pairs — full v0.2.5 carryover)
- data/v0.2.6-empathy-additions.jsonl        (20 new empathy + moral-weight pairs)
- data/v0.2.6-extraction-reliability-additions.jsonl  (8 new extraction pairs)

Total expected: 673 pairs.

Two new axes (per docs/handoffs/v0.2.6-retrain-2026-05-24.md):
  1. Empathy + moral-weight 8th pillar — hold weight without pulling on it,
     no generic-empathy fillers, no excavation prompts, route grief into
     adjacent-care. 20 pairs reviewed + approved by Ray on the Mac
     orchestrator side.
  2. Extraction schema stability + density floor — kill [AI]-hallucinated
     types, emit [] for low-signal chunks instead of meta-comment entries.
     8 pairs Sonnet-drafted, JSONL clean.

Sanitization is the standard v0.1+ block regex + medical block list —
the new pairs were drafted with this in mind and should pass clean.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

SOURCES = [
    DATA_DIR / "ray-stack-sft-v0.2.5-additions.jsonl",
    DATA_DIR / "v0.2.6-empathy-additions.jsonl",
    DATA_DIR / "v0.2.6-extraction-reliability-additions.jsonl",
]
OUT = DATA_DIR / "ray-stack-sft-v0.2.6-additions.jsonl"

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
    counts = {"input_total": 0, "dropped_regex": 0, "dropped_medical": 0, "written": 0,
              "per_source": {}}

    with OUT.open("w", encoding="utf-8") as fout:
        for src in SOURCES:
            n_in = 0
            n_out = 0
            for obj in load_jsonl(src):
                n_in += 1
                counts["input_total"] += 1
                keep, reason = sanitize_line(obj)
                if not keep:
                    if reason and "regex" in reason:
                        counts["dropped_regex"] += 1
                    else:
                        counts["dropped_medical"] += 1
                    continue
                fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                n_out += 1
                counts["written"] += 1
            counts["per_source"][src.name] = {"in": n_in, "out": n_out}

    print(f"v0.2.6 additions assembled at {OUT}")
    print(f"  Input total:     {counts['input_total']}")
    print(f"  Dropped (regex): {counts['dropped_regex']}")
    print(f"  Dropped (med):   {counts['dropped_medical']}")
    print(f"  Written:         {counts['written']}")
    print(f"  Per-source:")
    for name, info in counts["per_source"].items():
        print(f"    {name:55s} in={info['in']:4d} out={info['out']:4d}")

    out_text = OUT.read_text(encoding="utf-8")
    m = SANITIZE_REGEX.search(out_text)
    if m:
        print(f"\nWARN: regex still matches: {m.group(0)}")
        return 1
    print("\nSanitization clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
