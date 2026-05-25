#!/usr/bin/env python3
"""v0.2.6.1 additions concat + sanitize.

Iteration on v0.2.6 after the post-train eval flagged five hard failure
modes (see commit 4d7f051 + docs/handoffs/v0.2.6-retrain-2026-05-24.md
+ data/eval-*-v026-* artifacts):

  1. Fake tool-call syntax leaking into conversational prose
  2. Empathy-refusal deflection ("Not my lane / I don't have the
     emotional range") — opposite of what v0.2.6 was supposed to train
  3. Joey=dog anchor drift (model called him a cat in one run)
  4. Low-signal extraction chunks still emitting decision/preference
     items instead of []
  5. Audit-register drift on casual knowledge-query prompts

Builds data/ray-stack-sft-v0.2.6.1-additions.jsonl by concatenating:
- data/ray-stack-sft-v0.2.6-additions.jsonl                (670 pairs)
- data/v0.2.6.1-anti-tool-leakage-additions.jsonl          (15 pairs)
- data/v0.2.6.1-anti-refusal-empathy-additions.jsonl       (8 pairs)
- data/v0.2.6.1-joey-anchor-additions.jsonl                (4 pairs)
- data/v0.2.6.1-extraction-low-signal-additions.jsonl      (10 pairs)

Total expected: ~707 pairs (670 + 37 iteration). The 37 new pairs will
get the same 3x extra oversample treatment as the v0.2.6 new pairs did,
to give them proportional loss influence.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

SOURCES = [
    DATA_DIR / "ray-stack-sft-v0.2.6-additions.jsonl",
    DATA_DIR / "v0.2.6.1-anti-tool-leakage-additions.jsonl",
    DATA_DIR / "v0.2.6.1-anti-refusal-empathy-additions.jsonl",
    DATA_DIR / "v0.2.6.1-joey-anchor-additions.jsonl",
    DATA_DIR / "v0.2.6.1-extraction-low-signal-additions.jsonl",
]
OUT = DATA_DIR / "ray-stack-sft-v0.2.6.1-additions.jsonl"

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

    print(f"v0.2.6.1 additions assembled at {OUT}")
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
