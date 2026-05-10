"""LLM-curated digest layer for uploaded wargame rulebooks.

Karpathy three-layer pattern, mini version:
  raw    — `<state-dir>/rules/<book>.pdf` + `<book>.md` (auto-converted)
  wiki   — `<state-dir>/rules/<book>.digest.md` (this module's output)
  schema — preamble injection prefers the digest by default; full
           rulebook stays on disk for citation lookups

The digest is a focused "AI Commander Reference" — what the AI
commander actually consults turn-to-turn. Skips design notes,
dedications, narrative passages, and narrative voice. Cross-references
back to the source rulebook section IDs so the model's orders can
cite specifically.

Generated once at upload time via a single OpenRouter call (~$0.05).
Re-runnable on demand (e.g. after a model upgrade or a prompt tweak).
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path

DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
DEFAULT_MAX_TOKENS = 4000
DEFAULT_TIMEOUT_S = 180

DIGEST_SYSTEM_PROMPT = """You are condensing a tabletop wargame rulebook
into a focused AI Commander Reference. The reader is an LLM acting as
the kriegspiel commander for one side; it issues mission-type orders
to formations every turn and consults this reference for the specific
rule mechanics that affect those orders.

## Your output contract

Strict markdown. Target 2000-3500 words. Structure:

```
# AI Commander Reference — <Game Title>

## Game shape
- one-line: scale, map type, turns, sides
- victory-condition summary

## Sequence of play
- numbered phases as they actually run

## Forces
- per-side: unit types, key special units, what the special units do

## Combat resolution
- the formula (CS + adjustments → result)
- modifier list (terrain, flanking, support, air, etc) — short bullets, name + DRM/CSA + section
- casualty / loss math
- retreat / advance after combat rules

## Movement & terrain
- MP costs, ZOC effects, stacking limits
- terrain effects (highlight: rivers, forest, urban, fortified — anything that changes combat)

## Air missions  (omit if game has no air)
- mission types + when each fires
- air-to-air, SAM, suppression, ground support

## Naval / specialized assets  (omit if not present)

## Logistics & supply
- LOC rules, supply effects, partisan / interdiction mechanics

## Special rules  (anything turn-by-turn relevant that didn't fit above)

## Victory & VP
- VP track, key VP triggers, end-of-game scoring

## Quick decision matrix
- 5-10 bullets: "If <situation>, the relevant rule is <§>." Maximum signal.
```

## Discipline

- Every rule mechanic gets a `[see §X.Y]` reference back to the source
  rulebook so the commander's orders can cite precisely.
- Skip: design notes, dedications, ethics statements, copyright,
  publisher info, table of contents, glossary entries that aren't
  load-bearing for combat / movement / orders.
- Keep: numeric values (DRMs, CSAs, MA costs, dice probabilities,
  VP values), trigger conditions, modifier lists, special-rule names.
- If the source has tables (CRT, TEC, Air missions), prefer a tight
  bulleted summary of the table's load-bearing rows rather than
  reproducing the table verbatim.
- Imperative shape — write for an operator, not a publisher: "Naval
  units stack freely; after each use, roll 1d8: 6+ eliminates [see §3.1.2]"
  not "There are interesting interactions with naval units."
- Bias toward what affects mission-level orders (formation activations,
  axis priorities, when to commit air, whether to engage). De-emphasize
  fiddly bookkeeping (counter art, setup ID matching) unless it changes
  what a commander would order.

Output the markdown only. No preamble, no commentary, no explanation
of what you did. The first line of your output is the H1 title.
"""


def _call_openrouter(messages: list[dict], model: str, max_tokens: int,
                     timeout: int, api_key: str) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
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
            "X-Title": "wargame_digest (hammerstein-model wargame extension)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def generate_digest(
    full_rules_md: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = DEFAULT_TIMEOUT_S,
    api_key: str | None = None,
) -> tuple[str, dict]:
    """Generate the AI Commander Reference digest from a full rulebook.

    Returns (digest_markdown, meta) where meta contains model usage
    (prompt_tokens / completion_tokens / cost if reported).
    """
    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in env")

    messages = [
        {"role": "system", "content": DIGEST_SYSTEM_PROMPT},
        {"role": "user", "content": (
            "# Source rulebook\n\n"
            "Generate the AI Commander Reference for the following "
            "rulebook. Follow the output contract strictly.\n\n"
            "---\n\n"
            + full_rules_md
        )},
    ]
    response = _call_openrouter(messages, model, max_tokens, timeout, api_key)
    if "choices" not in response:
        raise RuntimeError(
            f"digest call returned malformed response: "
            f"{json.dumps(response)[:300]}"
        )
    body = response["choices"][0]["message"]["content"]
    usage = response.get("usage", {}) or {}
    cost = response.get("cost") or usage.get("total_cost")
    meta = {
        "model": model,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cost_usd": cost,
    }
    return body.strip() + "\n", meta


def write_digest(rules_md_path: Path, digest_md: str) -> Path:
    """Write the digest next to its source. `<book>.md` → `<book>.digest.md`."""
    out = rules_md_path.with_suffix("")
    out = out.with_name(out.name + ".digest.md")
    out.write_text(digest_md)
    return out
