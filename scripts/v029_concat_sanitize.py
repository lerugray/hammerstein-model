#!/usr/bin/env python3
"""v0.2.9 additions concat + sanitize.

Per docs/handoffs/v0.2.9-from-privategs-orchestrator-2026-05-25.md:
clean-rebase from v0.2.6.2 base (same as v0.2.8) plus:
  - REPLACE v0.2.7-tool-use-judgment.jsonl with augmented version that
    carries the `tools` field per row (v0.2.9-tool-use-judgment-augmented.jsonl)
  - REPLACE v0.2.7-tool-routing-alignment.jsonl with augmented version
    (v0.2.9-tool-routing-alignment-augmented.jsonl)
  - ADD v0.2.9-relational-voice-reinforcement.jsonl (5x oversample)

CRITICAL: this concat-sanitize PRESERVES the `tools` field in the output.
The train script's format_example() uses tokenizer.apply_chat_template
which reads `tools` to render the # Tools system preamble at training
time, matching what Ollama renders at inference.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# (filename, oversample_factor) — orchestrator's v0.2.9 inclusion list
ADDITIONS_FILES: list[tuple[str, int]] = [
    # v0.2.7 axes (same as v0.2.8, EXCEPT tool-use + tool-routing swapped for augmented versions)
    ("v0.2.7-anti-meta-leakage-v2.jsonl",                   5),
    ("v0.2.7-register-classifier.jsonl",                    5),
    ("v0.2.6.1-extraction-low-signal-additions.jsonl",      3),
    ("v0.2.6.2-extraction-low-signal-reinforcement.jsonl",  3),
    ("v0.2.7-real-usage-failures.jsonl",                    5),
    # AUGMENTED versions (carry `tools` field):
    ("v0.2.9-tool-routing-alignment-augmented.jsonl",       5),  # was v0.2.7-tool-routing-alignment.jsonl
    ("v0.2.9-tool-use-judgment-augmented.jsonl",            5),  # was v0.2.7-tool-use-judgment.jsonl
    # Other v0.2.7 axes:
    ("v0.2.7-canonical-positives.jsonl",                    5),
    ("v0.2.7-interface-aware-close.jsonl",                  5),
    ("v0.2.7-asymmetric-engagement-fix.jsonl",              5),
    # v0.2.7.1 fix axes
    ("v0.2.7.1-anti-self-state-fabrication.jsonl",          5),
    ("v0.2.7.1-low-signal-extraction-edges.jsonl",          3),
    ("v0.2.7.1-anti-meta-leakage-v3.jsonl",                 5),
    # v0.2.7.2 fix axis (pure-question only — XML tool-use EXCLUDED)
    ("v0.2.7.2-pure-question-extraction-edges.jsonl",       3),
    # v0.2.8 high-signal extraction reinforcement
    ("v0.2.8-high-signal-extraction-reinforcement.jsonl",   5),
    # v0.2.9 NEW relational voice reinforcement
    ("v0.2.9-relational-voice-reinforcement.jsonl",         5),
]

OUT = DATA_DIR / "ray-stack-sft-v0.2.9-additions.jsonl"

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
        "preserved_tools": 0,
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
                if "tools" in obj:
                    counts["preserved_tools"] += 1
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

    print(f"v0.2.9 additions assembled at {OUT}")
    print(f"  Input total:                     {counts['input_total']}")
    print(f"  Dropped (regex):                 {counts['dropped_regex']}")
    print(f"  Dropped (medical blocklist):     {counts['dropped_medical']}")
    print(f"  Stripped _metadata:              {counts['stripped_metadata']}")
    print(f"  Preserved `tools` field:         {counts['preserved_tools']} (before oversample)")
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

    # Sanity: count examples with the `tools` field in output
    tools_in_output = 0
    for line in out_text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "tools" in obj:
            tools_in_output += 1
    print(f"  Examples with `tools` field in output: {tools_in_output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
