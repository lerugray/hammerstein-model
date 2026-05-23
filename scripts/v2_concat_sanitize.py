#!/usr/bin/env python3
"""v0.2 additions concat + sanitize.

Three jobs:

  1. Parse Seeds 01-30 from data/v2-casual-seeds-scratchpad.md and write
     them out as data/v2-casual-seeds-2026-05-23.jsonl (OpenAI chat-message
     format, matching v0.1).
  2. Concatenate v0.2 sources into data/ray-stack-sft-v0.2-additions.jsonl:
       - v2-casual-seeds-2026-05-23.jsonl (30 seeds)
       - v2-audit-discrimination-2026-05-23.jsonl (~58 pairs)
       - v2-casual-restyled-2026-05-23.jsonl (~170 OpenRouter-restyled)
  3. Sanitize the combined file against the v0.1 block regex:
       (Jason|Ricky|Kunal|James Rodgers|Ryan Fyr|sk-[a-zA-Z0-9]{10,}|hf_[A-Za-z0-9]+)
     plus a small medical-content block list. Drop matching lines, log
     counts.

Also writes the v0.1 combined file (ray-stack-sft-v0.1-combined.jsonl)
if not already present — needed by the v0.2 training script's mix.

Idempotent. Re-run safely.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

SCRATCHPAD = DATA_DIR / "v2-casual-seeds-scratchpad.md"
SEEDS_OUT = DATA_DIR / "v2-casual-seeds-2026-05-23.jsonl"
DISCRIMINATION = DATA_DIR / "v2-audit-discrimination-2026-05-23.jsonl"
RESTYLED = DATA_DIR / "v2-casual-restyled-2026-05-23.jsonl"
V02_OUT = DATA_DIR / "ray-stack-sft-v0.2-additions.jsonl"
V01_COMBINED_OUT = DATA_DIR / "ray-stack-sft-v0.1-combined.jsonl"
V01_BASE = DATA_DIR / "ray-stack-sft-2026-05-21.jsonl"
V01_EXPANSION = DATA_DIR / "ray-stack-sft-2026-05-22-expansion.jsonl"

# v0.1 sanitization regex — block list
SANITIZE_REGEX = re.compile(
    r"(Jason|Ricky|Kunal|James Rodgers|Ryan Fyr|sk-[a-zA-Z0-9]{10,}|hf_[A-Za-z0-9]+)"
)

# Medical/personal content block list (case-insensitive). Conservative.
MEDICAL_BLOCKLIST = [
    "venlafaxine", "ssri", "snri", "prescription", "dosage",
    "discontinuation syndrome", "antidepressant", "anti-depressant",
]


# --- Seed parsing ----------------------------------------------------------

# Each seed block in the scratchpad has the shape:
#
# ### Seed NN - <description>
#
# **Prompt:**
#
# > <prompt text, possibly multi-line with leading "> ">
#
# [optional v1 actual block]
#
# **Ideal (DRAFT, awaiting Ray review):**
#
# > <ideal text, possibly multi-line with leading "> ">
#
# Target shape: ...
#
# ---

SEED_HEADER = re.compile(r"^### Seed (\d{2}) - (.+)$", re.MULTILINE)
PROMPT_HEADER = re.compile(r"^\*\*Prompt:\*\*\s*$", re.MULTILINE)
IDEAL_HEADER = re.compile(
    r"^\*\*Ideal \(DRAFT, awaiting Ray review\):\*\*\s*$", re.MULTILINE
)


def _extract_blockquote(text: str, start: int) -> tuple[str, int]:
    """Starting at `start`, find the next blockquote (lines starting with >).
    Returns (text_without_quote_marker, end_index_in_text)."""
    lines = text[start:].splitlines(keepends=True)
    quote_lines: list[str] = []
    end_offset = 0
    in_quote = False
    consumed_chars = 0

    for line in lines:
        consumed_chars += len(line)
        stripped = line.rstrip("\n").rstrip()
        if not in_quote:
            if stripped.startswith(">"):
                # Enter the block
                content = stripped[1:].lstrip()
                quote_lines.append(content)
                in_quote = True
            elif stripped == "":
                continue
            else:
                # Hit a non-blank non-quote line before the quote — skip
                continue
        else:
            if stripped.startswith(">"):
                content = stripped[1:].lstrip()
                quote_lines.append(content)
            elif stripped == "":
                quote_lines.append("")
                continue
            else:
                # Quote ended
                consumed_chars -= len(line)
                break
    while quote_lines and quote_lines[-1] == "":
        quote_lines.pop()
    return ("\n".join(quote_lines).strip(), start + consumed_chars)


def parse_seeds(scratchpad_text: str) -> list[dict]:
    """Walk the scratchpad and return a list of {prompt, response} dicts
    for each Seed block that has both a Prompt and an Ideal section."""
    seeds: list[dict] = []
    for header_match in SEED_HEADER.finditer(scratchpad_text):
        seed_n = int(header_match.group(1))
        desc = header_match.group(2).strip()
        block_start = header_match.end()
        # Find the next Seed header (or end of text) to bound this seed
        next_header = SEED_HEADER.search(scratchpad_text, block_start)
        block_end = next_header.start() if next_header else len(scratchpad_text)
        block = scratchpad_text[block_start:block_end]

        # Prompt section
        prompt_m = PROMPT_HEADER.search(block)
        if not prompt_m:
            continue
        prompt_text, _ = _extract_blockquote(block, prompt_m.end())

        # Ideal section
        ideal_m = IDEAL_HEADER.search(block)
        if not ideal_m:
            continue
        ideal_text, _ = _extract_blockquote(block, ideal_m.end())

        if not prompt_text or not ideal_text:
            continue

        seeds.append({
            "seed_n": seed_n,
            "desc": desc,
            "messages": [
                {"role": "user", "content": prompt_text},
                {"role": "assistant", "content": ideal_text},
            ],
        })
    return seeds


def write_seeds_jsonl(seeds: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for s in seeds:
            obj = {"messages": s["messages"]}
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# --- Concat + sanitize ----------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sanitize_line(obj: dict) -> tuple[bool, str | None]:
    """Return (keep, reason_if_dropped). Drops on block-list match."""
    text = json.dumps(obj, ensure_ascii=False)
    m = SANITIZE_REGEX.search(text)
    if m:
        return False, f"block-regex-match: {m.group(0)[:40]}"
    text_lower = text.lower()
    for kw in MEDICAL_BLOCKLIST:
        if kw in text_lower:
            return False, f"medical-blocklist: {kw}"
    return True, None


def concat_and_sanitize(sources: list[Path], out_path: Path) -> dict:
    """Read sources, sanitize each line, write the kept lines to out_path.
    Returns counts dict."""
    counts = {"input_total": 0, "dropped_regex": 0, "dropped_medical": 0,
              "written": 0, "per_source": {}}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fout:
        for src in sources:
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
    return counts


# --- Main ----------------------------------------------------------------

def main() -> int:
    if not SCRATCHPAD.exists():
        print(f"ERROR: scratchpad not found at {SCRATCHPAD}")
        return 1

    # Step 1: parse seeds → write seeds JSONL
    print(f"[1/3] Parsing seeds from {SCRATCHPAD.name}...")
    text = SCRATCHPAD.read_text(encoding="utf-8")
    seeds = parse_seeds(text)
    print(f"  Found {len(seeds)} seed entries")
    if len(seeds) == 0:
        print("ERROR: no seeds parsed. Check scratchpad format.")
        return 1
    write_seeds_jsonl(seeds, SEEDS_OUT)
    print(f"  Wrote {SEEDS_OUT}")
    for s in seeds:
        u_preview = s["messages"][0]["content"][:60].replace("\n", " ")
        print(f"    Seed {s['seed_n']:02d}: {u_preview}")

    # Step 2: assemble v0.1 combined if missing
    if not V01_COMBINED_OUT.exists():
        print(f"\n[2/3] Assembling v0.1 combined ({V01_BASE.name} + {V01_EXPANSION.name})...")
        if not V01_BASE.exists() or not V01_EXPANSION.exists():
            print(f"  WARN: v0.1 source files missing — skipping combined assembly")
        else:
            combined = load_jsonl(V01_BASE) + load_jsonl(V01_EXPANSION)
            with V01_COMBINED_OUT.open("w", encoding="utf-8") as f:
                for obj in combined:
                    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            print(f"  Wrote {V01_COMBINED_OUT} ({len(combined)} pairs)")
    else:
        print(f"\n[2/3] v0.1 combined already exists at {V01_COMBINED_OUT.name} — skipping")

    # Step 3: concat v0.2 sources with sanitization
    print(f"\n[3/3] Concat + sanitize v0.2 sources → {V02_OUT.name}")
    sources = [SEEDS_OUT, DISCRIMINATION, RESTYLED]
    for s in sources:
        if not s.exists():
            print(f"  WARN: {s.name} missing — will skip")
    counts = concat_and_sanitize([s for s in sources if s.exists()], V02_OUT)
    print(f"  Input total:     {counts['input_total']}")
    print(f"  Dropped (regex): {counts['dropped_regex']}")
    print(f"  Dropped (med):   {counts['dropped_medical']}")
    print(f"  Written:         {counts['written']}")
    print(f"  Per-source:")
    for name, info in counts["per_source"].items():
        print(f"    {name:50s}  in={info['in']:4d}  out={info['out']:4d}")
    print(f"\n  Output: {V02_OUT}")

    # Sanity grep after write
    out_text = V02_OUT.read_text(encoding="utf-8")
    m = SANITIZE_REGEX.search(out_text)
    if m:
        print(f"\nWARN: sanitization regex still matches output! ({m.group(0)})")
        return 1
    print(f"\nSanitization check: 0 matches against block regex. Clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
