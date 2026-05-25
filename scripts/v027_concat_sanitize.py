#!/usr/bin/env python3
"""v0.2.7 additions concat + sanitize.

Architecture shift from v0.2.6.x: per-file oversample lives in this
concat-sanitize step (not in the train script). This gives the data
designer (Mac orchestrator) direct control over the 11-axis mix
without round-tripping through the train script.

11 axes (per v0.2.7-scope-and-data-design-2026-05-25.md):
  1.  meta-leakage anti-pairs           (anti-meta-leakage-v2.jsonl)
  2.  register classifier               (register-classifier.jsonl)
  3.  extraction low-signal carryover   (v0.2.6.1 + v0.2.6.2 extraction files, 9x)
  4.  real-usage failures               (real-usage-failures.jsonl)
  5.  tool-routing alignment            (tool-routing-alignment.jsonl)
  6/7/8. canonical preservation         (canonical-positives.jsonl, multi-turn)
  9.  interface-aware close             (interface-aware-close.jsonl)
  10. asymmetric engagement fix         (asymmetric-engagement-fix.jsonl)
  11. tool-use judgment                 (tool-use-judgment.jsonl)

DO NOT include: v0.2.7-canonical-negatives-reference-only.jsonl
                v0.2.7-canonical-preservation-examples.jsonl

The negatives file holds v0.2.6.2 failure-shape responses (reference
only). The preservation-examples file is Mac-side reference material;
its positive equivalents are in canonical-positives.jsonl.

Strips _metadata key (Mac orchestrator writes metadata for human
review; the trainer wants plain {"messages": [...]}).

Expected output: ~608 lines in data/ray-stack-sft-v0.2.7-additions.jsonl
(handoff brief target: ~600-800).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# (filename, oversample_factor) — handoff brief v0.2.7-pc-fire-brief-2026-05-25.md
ADDITIONS_FILES: list[tuple[str, int]] = [
    ("v0.2.7-anti-meta-leakage-v2.jsonl",                 5),
    ("v0.2.7-register-classifier.jsonl",                   5),
    ("v0.2.6.1-extraction-low-signal-additions.jsonl",     9),   # BUMPED from v026.2's 5x
    ("v0.2.6.2-extraction-low-signal-reinforcement.jsonl", 9),   # BUMPED from v026.2's 5x
    ("v0.2.7-real-usage-failures.jsonl",                   5),
    ("v0.2.7-tool-routing-alignment.jsonl",                5),
    ("v0.2.7-canonical-positives.jsonl",                   5),
    ("v0.2.7-interface-aware-close.jsonl",                 5),
    ("v0.2.7-asymmetric-engagement-fix.jsonl",             5),
    ("v0.2.7-tool-use-judgment.jsonl",                     5),
]

OUT = DATA_DIR / "ray-stack-sft-v0.2.7-additions.jsonl"

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
        "input_total":   0,
        "dropped_regex": 0,
        "dropped_medical": 0,
        "stripped_metadata": 0,
        "written":       0,
        "per_source":    {},
    }

    with OUT.open("w", encoding="utf-8") as fout:
        for fname, oversample in ADDITIONS_FILES:
            src = DATA_DIR / fname
            rows = load_jsonl(src)
            n_in = len(rows)
            n_out_per_pass = 0

            # Sanitize once per record; oversample by emitting N copies.
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
                # Strip _metadata before training — Mac orchestrator writes it
                # for human review; trainer wants plain {"messages": [...]}.
                if "_metadata" in obj:
                    obj.pop("_metadata", None)
                    counts["stripped_metadata"] += 1
                kept.append(obj)

            for _ in range(oversample):
                for obj in kept:
                    fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                    counts["written"] += 1
                    n_out_per_pass += 1

            n_out_per_pass = len(kept) * oversample  # canonical
            counts["per_source"][fname] = {
                "in_raw":     n_in,
                "kept":       len(kept),
                "oversample": oversample,
                "out_total":  len(kept) * oversample,
            }

    print(f"v0.2.7 additions assembled at {OUT}")
    print(f"  Input total (across all files):  {counts['input_total']}")
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
        print(f"\nWARN: regex still matches in output: {m.group(0)}")
        return 1
    print("\nSanitization clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
