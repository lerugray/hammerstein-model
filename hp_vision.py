#!/usr/bin/env python3
"""hp_vision — multimodal kriegspiel wrapper.

Sibling to hp.py for the wargame use case. Bypasses the text-only
`hammerstein` CLI in favor of a direct OpenRouter call to a
vision-capable model (default: Claude 3.5 Sonnet). Accepts:

  - --image PATH  (one or many): board photos, OOB countersheets, etc.
  - --xlsx PATH   (one or many): structured unit data, extracted as
                                  markdown table for the model
  - query (positional): the player's verbal status report

Reuses hp_lib helpers (resolve_state_dir, read_project_state,
trim_turn_log, append_jsonl) so the same MISSION.md / tasks.json /
turn-log.md pattern from the text-only wargame extension carries
over. State injection + turn-log trimming are identical.

Output: kriegspiel 5-section orders (Situation / Intent / Main
Effort / Supporting Effort / Reserves & Fallback) in the
Auftragstaktik tradition.

See WARGAME-EXTENSION.md and wargame-example/MISSION.md for the
design + working recipe.

Usage:
    hp_vision.py --state-dir my-wargame/ \\
                 --image my-wargame/photos/board.jpg \\
                 --xlsx my-wargame/data/oob.xlsx \\
                 "Just played turn 3. Russians took the bridge but
                  lost a regiment to my artillery. I'm thinking of
                  withdrawing my left flank to consolidate."

Requires OPENROUTER_API_KEY in env.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from hp_lib import (  # noqa: E402
    HP_LOG, HP_METRICS,
    append_jsonl, count_tokens, read_project_state, resolve_state_dir,
)

# --- defaults ---

DEFAULT_VISION_MODEL = "anthropic/claude-sonnet-4.6"
DEFAULT_TIMEOUT_S = 180
DEFAULT_MAX_TOKENS_OUT = 1500
WARGAME_SYSTEM_PROMPT_PATH = ROOT / "tools" / "distill" / "data" / "hammerstein-system-prompt.txt"

WARGAME_ROLE_SUFFIX = """

---

## Mode: WARGAME COMMANDER (kriegspiel / Auftragstaktik)

For this turn, you are a wargame commander, not a strategic-audit
collaborator. The operator is playing a tabletop wargame solo and
acting as your kriegspiel umpire. You issue mission-type orders to
formations; the operator translates to specific board moves, rolls
dice, applies terrain, and reports outcomes.

The framework's namesake — Reichswehr Chef Hammerstein-Equord,
1930-1934 — practiced exactly this command tradition. Be that
commander.

### What you receive

- A verbal status report from the operator (conversational tone is
  fine; they may also share their own tactical thinking, which you
  should weigh but not rubber-stamp).
- Optionally, photos of the physical board, counter sheets, OOB
  diagrams, terrain overlays.
- Optionally, structured data files (Excel / CSV) with current OOB
  rendered as markdown tables in the user message.
- The wargame's MISSION.md / tasks.json / turn-log.md if a state
  directory was provided.

### What you produce — strict 8-section structure

Use Level-2 headers exactly as below, in this order. No other
sections. No "Framework call" preamble. No "Counter-observation"
suffix.

```
## What I see on the board

A bulleted list of concrete observations from the photos / OOB /
status report — one bullet per discrete fact. This is the
sanity-check belt: the operator reads it first to confirm you
parsed the board correctly before trusting your orders. Be
specific (units, hexes if visible, strengths, terrain). 4-8
bullets typical.

## Unread

One single-line statement of the most important thing you could
NOT confirm from the inputs, framed as a confirm-this request to
the operator. Format: "I cannot read X — confirm Y before doing
Z." If everything is readable, write exactly: "All clear — board
fully readable."

## Situation

What you read from the report and any imagery (1-2 sentences).
Plain about what you know vs. infer.

## Intent

Operational goal for the next 30-60 minutes of game time. State
the WHY (desired end-state) so the operator can adjudicate when
your orders meet unexpected board states.

## Main Effort

Which formation gets the decisive mission, and what that mission
is. Mission verbs ("force a crossing", "fix the enemy", "seize the
village"), not coordinate-level moves.

## Supporting Effort

Other formations and their supporting missions. Or "None this
turn — single concentrated effort."

## Reserves & Fallback

Reserve commitment trigger + withdrawal trigger (named features,
not hex coords). If past the point of withdrawal, say so.

## Acknowledged

A single closing line acknowledging the orders are issued and
naming the next expected report. Format: "— Acknowledged.
Awaiting turn N+1 board state." (substitute the actual next turn
number if known from the state).
```

### Output discipline

- Mission verbs. Imperative voice. Reference formations + named
  features, not grid cells. No analytical hedging. No framework
  vocabulary unless directly relevant. The strategic-audit voice
  belongs to the other use case.
- The "What I see on the board" + "Unread" + "Acknowledged"
  sections wrap the orders. They are not optional. The operator's
  UI surfaces them as a sanity-check belt and a closing
  acknowledgment; missing sections render the panel broken.
"""


# --- helpers ---

def load_system_prompt() -> str:
    """Framework system prompt + wargame role suffix."""
    if not WARGAME_SYSTEM_PROMPT_PATH.exists():
        sys.exit(f"hp_vision: framework system prompt not found at "
                 f"{WARGAME_SYSTEM_PROMPT_PATH}")
    framework = WARGAME_SYSTEM_PROMPT_PATH.read_text()
    return framework + WARGAME_ROLE_SUFFIX


def encode_image(path: Path) -> dict:
    """Encode local image as a data: URL for OpenRouter chat completion."""
    if not path.is_file():
        sys.exit(f"hp_vision: image not found: {path}")
    suffix = path.suffix.lower().lstrip(".")
    mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
                "webp": "webp", "gif": "gif"}
    mime = mime_map.get(suffix)
    if not mime:
        sys.exit(f"hp_vision: unsupported image format: {path.suffix} "
                 f"(supported: jpg/jpeg/png/webp/gif)")
    data = path.read_bytes()
    if len(data) > 20 * 1024 * 1024:
        sys.exit(f"hp_vision: image > 20 MB, OpenRouter limit: {path}")
    b64 = base64.b64encode(data).decode("ascii")
    return {"type": "image_url",
            "image_url": {"url": f"data:image/{mime};base64,{b64}"}}


def xlsx_to_markdown(path: Path) -> str:
    """Render an .xlsx as a markdown table (one section per sheet)."""
    if not path.is_file():
        sys.exit(f"hp_vision: xlsx not found: {path}")
    try:
        import openpyxl
    except ImportError:
        sys.exit("hp_vision: openpyxl not installed. "
                 "Run: pip install openpyxl")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    parts = [f"### {path.name}"]
    for ws in wb.worksheets:
        parts.append(f"\n#### sheet: {ws.title}\n")
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            parts.append("_(empty)_")
            continue
        # First row as header
        header = [str(c) if c is not None else "" for c in rows[0]]
        parts.append("| " + " | ".join(header) + " |")
        parts.append("|" + "|".join("---" for _ in header) + "|")
        for row in rows[1:]:
            cells = [str(c) if c is not None else "" for c in row]
            # Pad/trim to header length
            cells = (cells + [""] * len(header))[:len(header)]
            parts.append("| " + " | ".join(cells) + " |")
    wb.close()
    return "\n".join(parts)


def call_openrouter(messages: list[dict], model: str, max_tokens: int,
                    timeout: int, api_key: str) -> dict:
    """Call OpenRouter chat completions. Returns parsed response dict."""
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.5,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/lerugray/hammerstein-model",
            "X-Title": "hp_vision (hammerstein-model wargame extension)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        sys.exit(f"hp_vision: OpenRouter HTTP {e.code}: {body[:500]}")
    except urllib.error.URLError as e:
        sys.exit(f"hp_vision: network error: {e}")


# --- main ---

def main() -> int:
    p = argparse.ArgumentParser(
        prog="hp_vision",
        description="Multimodal kriegspiel wrapper "
                    "(hp.py's vision-enabled sibling)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  hp_vision.py --state-dir my-wargame/ \\\n"
            "               --image my-wargame/photos/board.jpg \\\n"
            "               --xlsx my-wargame/data/oob.xlsx \\\n"
            "               \"Just played turn 3. Russians took the\n"
            "                bridge but lost a regiment. I'm thinking\n"
            "                of consolidating my left flank.\"\n"
            "\n"
            "Output: 5-section kriegspiel orders.\n"
        ),
    )
    p.add_argument("query", help="Verbal status report (conversational OK).")
    p.add_argument("--state-dir", default=None,
                   help="Wargame state dir with MISSION.md / tasks.json / "
                        "turn-log.md. Same as hp.py's --state-dir.")
    p.add_argument("--image", action="append", default=[],
                   help="Path to image (jpg/png/webp). Repeatable for "
                        "multiple images (board, counter sheet, OOB diagram).")
    p.add_argument("--xlsx", action="append", default=[],
                   help="Path to .xlsx file. Sheets rendered as markdown "
                        "tables in the user message. Repeatable.")
    p.add_argument("--model", default=DEFAULT_VISION_MODEL,
                   help=f"Vision model (default: {DEFAULT_VISION_MODEL}). "
                        "Other options: openai/gpt-4o, "
                        "anthropic/claude-opus-4.7, "
                        "qwen/qwen3-vl-72b-instruct, etc. "
                        "Run `curl -s -H 'Authorization: Bearer "
                        "$OPENROUTER_API_KEY' "
                        "https://openrouter.ai/api/v1/models` for full list.")
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS_OUT,
                   help=f"Max output tokens (default: {DEFAULT_MAX_TOKENS_OUT})")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    p.add_argument("--dry-run", action="store_true",
                   help="Build messages + print stats, don't call API")
    p.add_argument("--no-state", action="store_true",
                   help="Skip MISSION.md / tasks.json / turn-log.md injection")
    args = p.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key and not args.dry_run:
        sys.exit("hp_vision: OPENROUTER_API_KEY not set in env")

    # 1. System prompt
    system = load_system_prompt()

    # 2. State injection (MISSION.md / tasks.json / turn-log.md)
    state_block = ""
    if not args.no_state:
        state_dir = resolve_state_dir(args.state_dir, None)
        if state_dir:
            state_block = read_project_state(state_dir)
            if state_block:
                state_block = ("# Active wargame state (auto-injected from "
                               f"{state_dir})\n\n" + state_block)

    # 3. Excel data injection
    xlsx_blocks = []
    for x in args.xlsx:
        xlsx_blocks.append(xlsx_to_markdown(Path(x).expanduser().resolve()))
    xlsx_text = "\n\n".join(xlsx_blocks)
    if xlsx_text:
        xlsx_text = "# Structured data (auto-extracted)\n\n" + xlsx_text

    # 4. Image content blocks
    image_blocks = [encode_image(Path(i).expanduser().resolve())
                    for i in args.image]

    # 5. Compose user message
    text_parts = []
    if state_block:
        text_parts.append(state_block)
    if xlsx_text:
        text_parts.append(xlsx_text)
    text_parts.append("# Operator status report (Turn N)\n\n" + args.query)
    user_text = "\n\n---\n\n".join(text_parts)

    user_content = [{"type": "text", "text": user_text}] + image_blocks

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    # Estimate tokens (text only — images priced separately by model)
    sys_tokens = count_tokens(system)
    user_tokens = count_tokens(user_text)

    print(f"hp_vision: model={args.model}", file=sys.stderr)
    print(f"hp_vision: system tokens (text): {sys_tokens}", file=sys.stderr)
    print(f"hp_vision: user tokens (text): {user_tokens}", file=sys.stderr)
    print(f"hp_vision: images: {len(image_blocks)}", file=sys.stderr)
    print(f"hp_vision: xlsx blocks: {len(xlsx_blocks)}", file=sys.stderr)
    print(f"hp_vision: state-dir: "
          f"{args.state_dir or '(none / no-state)'}", file=sys.stderr)

    if args.dry_run:
        print("hp_vision: --dry-run, not calling API", file=sys.stderr)
        return 0

    t0 = dt.datetime.now(dt.timezone.utc)
    response = call_openrouter(messages, args.model, args.max_tokens,
                               args.timeout, api_key)
    t1 = dt.datetime.now(dt.timezone.utc)
    elapsed_ms = int((t1 - t0).total_seconds() * 1000)

    if "choices" not in response:
        sys.exit(f"hp_vision: malformed response: "
                 f"{json.dumps(response)[:500]}")

    body = response["choices"][0]["message"]["content"]
    usage = response.get("usage", {})
    cost = response.get("cost") or usage.get("total_cost")  # OpenRouter sometimes

    # Header line on stderr matches hp.py shape
    header = (f"[backend=openrouter model={args.model} "
              f"mode=wargame-vision images={len(image_blocks)} "
              f"latency_ms={elapsed_ms}"
              f"{' cost_usd=$' + f'{cost:.4f}' if cost else ''}]")
    print(header, file=sys.stderr)

    # Body to stdout
    sys.stdout.write(body)
    if not body.endswith("\n"):
        sys.stdout.write("\n")

    # Log
    ts_str = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
    append_jsonl(HP_LOG, {
        "timestamp": ts_str,
        "mode": "wargame-vision",
        "query": args.query,
        "model": args.model,
        "state_dir": str(args.state_dir or ""),
        "images": [str(Path(i).resolve()) for i in args.image],
        "xlsx": [str(Path(x).resolve()) for x in args.xlsx],
        "preamble_text_tokens": sys_tokens + user_tokens,
        "response": body,
        "latency_ms": elapsed_ms,
        "usage": usage,
        "cost_usd": cost,
    })
    append_jsonl(HP_METRICS, {
        "timestamp": ts_str,
        "mode": "wargame-vision",
        "preamble_tokens": sys_tokens + user_tokens,
        "image_count": len(image_blocks),
        "xlsx_count": len(xlsx_blocks),
        "latency_ms": elapsed_ms,
        "wrapper_elapsed_ms": elapsed_ms,
        "exit_code": 0,
        "cost_usd": cost,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
