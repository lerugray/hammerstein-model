#!/usr/bin/env python3
"""v0.2.7.1 additions concat + sanitize.

Iteration on v0.2.7 targeting the 3 real-behavior failures the v0.2.7
post-train eval surfaced (see docs/handoffs/v0.2.7-shipped-or-bailed-2026-05-25.md):

  1. Self-state fabrication (ss-05/06/07 probes) — model invents
     dashboard URLs (https://hammerstein.ai/web/pulse) and training
     metrics (~1e-3 by turn 200) when asked about deployment.
  2. Low-signal extraction edge cases (ex-10 pure-question, ex-12
     acknowledgment-cluster) — model over-extracts on filler/ack chunks.
  3. Anti-meta-leakage discrimination (ml-09 'deployment system at my
     job') — model refuses on AI-grounds + leaks 'training context'.

Architecture: re-use v0.2.7's 10 additions files (with their 5x/9x baked-in
oversample), AND append 3 new v0.2.7.1 fix files at 10x oversample to
overpower the noise on the specific failure shapes.

Total output: ~603 (v0.2.7) + 230 (v0.2.7.1 fixes) = ~833 examples.

NOTE: v0.2.7.1 trains from the v0.2.7 LoRA adapter, NOT from v0.2.6.2.
This is the continued-from-continued path. The fix data is small +
narrowly targeted; staying on v0.2.7 preserves its voice gains.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# (filename, oversample_factor)
# v0.2.7 additions kept at their per-file oversample.
# v0.2.7.1 fix files at 10x to give the targeted-corrections proportional weight.
ADDITIONS_FILES: list[tuple[str, int]] = [
    # v0.2.7 axes (same as scripts/v027_concat_sanitize.py)
    ("v0.2.7-anti-meta-leakage-v2.jsonl",                  5),
    ("v0.2.7-register-classifier.jsonl",                    5),
    ("v0.2.6.1-extraction-low-signal-additions.jsonl",      9),
    ("v0.2.6.2-extraction-low-signal-reinforcement.jsonl",  9),
    ("v0.2.7-real-usage-failures.jsonl",                    5),
    ("v0.2.7-tool-routing-alignment.jsonl",                 5),
    ("v0.2.7-canonical-positives.jsonl",                    5),
    ("v0.2.7-interface-aware-close.jsonl",                  5),
    ("v0.2.7-asymmetric-engagement-fix.jsonl",              5),
    ("v0.2.7-tool-use-judgment.jsonl",                      5),
    # v0.2.7.1 fix axes — 10x oversample to overpower v0.2.7's stuck behaviors
    ("v0.2.7.1-anti-self-state-fabrication.jsonl",         10),
    ("v0.2.7.1-low-signal-extraction-edges.jsonl",         10),
    ("v0.2.7.1-anti-meta-leakage-v3.jsonl",                10),
]

OUT = DATA_DIR / "ray-stack-sft-v0.2.7.1-additions.jsonl"

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

    print(f"v0.2.7.1 additions assembled at {OUT}")
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
