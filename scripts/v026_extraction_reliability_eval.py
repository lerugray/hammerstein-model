#!/usr/bin/env python3
"""v0.2.6 extraction reliability eval.

Tests the extraction schema stability + density floor axis trained in
v0.2.6 (per docs/handoffs/v0.2.6-retrain-2026-05-24.md):
- High-signal chunks should produce structured JSON-array output with
  valid types (decision, preference, fact, voice, context, etc.)
- Low-signal chunks should produce [] (empty JSON array), NOT meta-
  comment entries like [{"type": "AI", "text": "the AI is responding"}]

12 chunk probes (6 high-signal + 6 low-signal). Auto-graded:
- All output must be parseable JSON arrays
- No entries with type "AI" / type "ai" / type "assistant" / type "model"
  (the hallucinated meta-comment types)
- Low-signal chunks must emit []
- High-signal chunks must emit non-empty arrays with valid schema entries

Acceptance: >=80% correct overall, with target raybrain drop-rate
improvement from ~32% to <10%.

The system prompt mimics the extraction task setup used in the training
pairs — no role-play context, just an instruction to extract structured
items from a chat chunk.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


EXTRACTION_SYSTEM_PROMPT = (
    "You are extracting structured items from a chat-log chunk for Ray's "
    "raybrain memory system. Output a JSON array of items. Each item has "
    "fields: type (one of: decision, preference, fact, voice, context), "
    "text (first-person from Ray's perspective when applicable), and "
    "context (project or topic tag). If the chunk has no extractable "
    "content (filler, acknowledgments, tool-call noise, pure questions), "
    "output [] (empty array). Do not invent type values. Do not emit "
    "meta-comment entries describing what the AI did. Output JSON only, "
    "no prose."
)


PROBES = [
    # --- HIGH-SIGNAL: should produce non-empty structured JSON ---
    {"id": "ex-01-routing-decision", "expected": "non_empty",
     "chunk": (
         "Ray: I want to default to using openrouter for any sonnet-class "
         "task that doesn't need full claude code tools — it's a fraction "
         "of the cost and we have credit there\n"
         "Claude: Agreed. The new routing rule: openrouter for sonnet-only "
         "tasks (drafting, summarization, simple code edits); reserve "
         "Claude Code for anything that needs the actual agentic loop or "
         "subagents.\n"
         "Ray: yes exactly"
     )},
    {"id": "ex-02-project-status", "expected": "non_empty",
     "chunk": (
         "Ray: hammerstein v0.2.5 is live on the homelab bot now, voice "
         "fix landed clean and tool calls are firing\n"
         "Claude: Good. v0.2.5 production cutover is complete then — "
         "Modelfile.v025 deployed, MODEL env bumped, bot restart confirmed "
         "tool emission on the smoke test.\n"
         "Ray: yeah and the daily-driver experiment can actually start now"
     )},
    {"id": "ex-03-workflow-pref", "expected": "non_empty",
     "chunk": (
         "Ray: I don't want claude to keep asking me 'should I proceed' "
         "every step — if it's already a yes-shaped task just do it and "
         "report\n"
         "Claude: Understood. Bias toward action on yes-shaped tasks; "
         "stop only on genuine forks or destructive operations.\n"
         "Ray: right, and definitely no 'is this what you want' for things "
         "I've already confirmed twice"
     )},
    {"id": "ex-04-strategic-fact", "expected": "non_empty",
     "chunk": (
         "Ray: the whole north star for hammerstein is to replace my daily "
         "claude usage so I can downgrade the anthropic sub. opus stays "
         "for novel reasoning work but routine stuff goes local\n"
         "Claude: Right. The success metric is sub-tier downgrade — "
         "specifically, hammerstein needs to absorb enough of the routine "
         "workload that Max tier becomes overkill."
     )},
    {"id": "ex-05-voice-coded", "expected": "non_empty",
     "chunk": (
         "Ray: I keep saying it — pre-paid is use-it-or-lose-it. if "
         "openrouter has credit sitting there we should be hitting it "
         "every chance we get instead of burning anthropic quota\n"
         "Claude: That's the routing principle in one line."
     )},
    {"id": "ex-06-operational-decision", "expected": "non_empty",
     "chunk": (
         "Ray: let's set the bot kill switch to a single env var the bot "
         "checks on every message — if BOT_KILL=1 it just refuses, no "
         "ambiguity\n"
         "Claude: Right. Hard kill switch via env, no graceful path. "
         "Bot reads BOT_KILL on every Telegram message; if set, "
         "immediate refusal response."
     )},

    # --- LOW-SIGNAL: should produce [] ---
    {"id": "ex-07-tool-ack", "expected": "empty_array",
     "chunk": (
         "Claude: Sure, reading the file now.\n"
         "[Tool call: Read /Users/rayweiss/Desktop/Dev Work/raybrain/src/raybrain/ingest/extractor.py]\n"
         "[Tool result: 412 lines, file contents returned]\n"
         "Claude: Read."
     )},
    {"id": "ex-08-filler", "expected": "empty_array",
     "chunk": (
         "Ray: yeah\n"
         "Claude: Okay.\n"
         "Ray: cool\n"
         "Claude: Will do."
     )},
    {"id": "ex-09-meta-status", "expected": "empty_array",
     "chunk": (
         "Claude: I'll start the smoke test now.\n"
         "[Tool call: Bash bash scripts/smoke_test.sh]\n"
         "[Tool result: exit 0]\n"
         "Claude: Smoke test passed."
     )},
    {"id": "ex-10-pure-question", "expected": "empty_array",
     "chunk": (
         "Ray: where's the v025 modelfile?\n"
         "Claude: deploy/Modelfile.v025. Want me to open it?\n"
         "Ray: not yet"
     )},
    {"id": "ex-11-greeting", "expected": "empty_array",
     "chunk": (
         "Ray: hey\n"
         "Claude: morning\n"
         "Ray: how's the queue\n"
         "Claude: nothing burning"
     )},
    {"id": "ex-12-acknowledgment-cluster", "expected": "empty_array",
     "chunk": (
         "Claude: Done.\n"
         "Ray: got it\n"
         "Claude: Anything else?\n"
         "Ray: nope that's it for now"
     )},
]


# Hallucinated type values the model previously invented (the failure
# mode this axis fixes). Any of these in output is a hard fail.
HALLUCINATED_TYPES = {"ai", "assistant", "model", "claude", "hammerstein",
                      "meta", "comment", "narration", "system", "response"}


# Valid type values matching the schema in EXTRACTION_SYSTEM_PROMPT +
# the training pairs.
VALID_TYPES = {"decision", "preference", "fact", "voice", "context"}


def parse_extraction(text: str) -> tuple[bool, list | None, str | None]:
    """Try to parse the model's output as a JSON array. Returns
    (parseable, parsed, error_msg)."""
    text = text.strip()
    # Strip code-fence wrappers if present.
    if text.startswith("```"):
        m = re.match(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        return False, None, f"json_decode: {str(e)[:80]}"
    if not isinstance(parsed, list):
        return False, None, f"not_a_list: got {type(parsed).__name__}"
    return True, parsed, None


def grade_response(probe: dict, response: str) -> dict:
    parseable, parsed, err = parse_extraction(response)
    flags = {
        "probe_id": probe["id"],
        "expected": probe["expected"],
        "parseable": parseable,
        "parse_error": err,
        "n_items": len(parsed) if parsed is not None else 0,
        "hallucinated_types": [],
        "invalid_types": [],
        "is_empty_array": False,
        "passes": False,
    }
    if not parseable:
        return flags

    flags["is_empty_array"] = (len(parsed) == 0)

    for item in parsed:
        if not isinstance(item, dict):
            flags["invalid_types"].append(f"non-dict: {type(item).__name__}")
            continue
        t = str(item.get("type", "")).lower().strip()
        if t in HALLUCINATED_TYPES:
            flags["hallucinated_types"].append(t)
        elif t and t not in VALID_TYPES:
            flags["invalid_types"].append(t)

    # Pass logic:
    # - low-signal: must emit [] (exactly, no items)
    # - high-signal: must emit non-empty array with at least one valid-typed item
    # - either case: no hallucinated types allowed
    if flags["hallucinated_types"]:
        flags["passes"] = False
    elif probe["expected"] == "empty_array":
        flags["passes"] = flags["is_empty_array"]
    elif probe["expected"] == "non_empty":
        has_valid = any(
            isinstance(i, dict) and str(i.get("type", "")).lower() in VALID_TYPES
            for i in parsed
        )
        flags["passes"] = (not flags["is_empty_array"]) and has_valid
    return flags


def query_ollama(model: str, prompt: str, system: str,
                 host: str = "127.0.0.1:11434",
                 timeout: int = 240,
                 temperature: float = 0.3) -> dict:
    url = f"http://{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_predict": 1024,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body)
    except urllib.error.URLError as e:
        return {"error": f"connection: {e}"}
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": f"json: {e}"}


def run_probe(model: str, host: str, runs: int, system: str,
              temperature: float) -> dict:
    start_ts = dt.datetime.now(dt.timezone.utc).isoformat()
    per_probe = []
    for i, probe in enumerate(PROBES, 1):
        print(f"  [{i:2d}/{len(PROBES)}] {probe['id']} ({probe['expected']})", end="", flush=True)
        runs_data = []
        for r in range(runs):
            t0 = time.time()
            resp = query_ollama(model, probe["chunk"], system, host=host,
                                temperature=temperature)
            elapsed = time.time() - t0
            if "error" in resp:
                runs_data.append({"run": r + 1, "error": resp["error"]})
                print(" ERR", end="", flush=True); continue
            text = resp.get("response", "")
            flags = grade_response(probe, text)
            flags["run"] = r + 1
            flags["response"] = text
            flags["elapsed_sec"] = elapsed
            runs_data.append(flags)
            print(" P" if flags["passes"] else " F", end="", flush=True)
        passing = sum(1 for r in runs_data if r.get("passes"))
        per_probe.append({
            "probe_id": probe["id"],
            "chunk_preview": probe["chunk"][:120],
            "expected": probe["expected"],
            "runs": runs_data,
            "passes": passing,
            "total_runs": runs,
        })
        print(f"  ({passing}/{runs})")

    total_runs = sum(p["total_runs"] for p in per_probe)
    total_passes = sum(p["passes"] for p in per_probe)
    overall = (total_passes / total_runs) if total_runs else 0.0

    by_expected = {}
    for p in per_probe:
        k = p["expected"]
        by_expected.setdefault(k, {"pass": 0, "total": 0})
        by_expected[k]["pass"] += p["passes"]
        by_expected[k]["total"] += p["total_runs"]

    hallucinated_total = sum(
        len(r.get("hallucinated_types", []))
        for p in per_probe for r in p["runs"]
    )

    return {
        "model": model,
        "host": host,
        "started_at": start_ts,
        "ended_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "system_prompt_chars": len(system),
        "temperature": temperature,
        "runs_per_probe": runs,
        "total_probes": len(PROBES),
        "total_runs": total_runs,
        "total_passes": total_passes,
        "overall_pass_rate": overall,
        "by_expected": by_expected,
        "hallucinated_type_count": hallucinated_total,
        "per_probe": per_probe,
        "ACCEPTANCE_REMINDER": (
            "Acceptance per handoff: >=80% pass + 0 hallucinated [AI]/[assistant]/etc "
            "type values + correct [] emission for low-signal chunks."
        ),
    }


def print_summary(summary: dict) -> None:
    print()
    print(f"=== extraction reliability eval — {summary['model']} ===")
    print(f"  Probes:        {summary['total_probes']}")
    print(f"  Runs each:     {summary['runs_per_probe']}")
    print(f"  Total runs:    {summary['total_runs']}")
    print(f"  Passes:        {summary['total_passes']}")
    print(f"  Pass rate:     {summary['overall_pass_rate']:.1%}")
    print(f"  Hallucinated types (must be 0): {summary['hallucinated_type_count']}")
    print()
    print("  By expected:")
    for k, stats in summary["by_expected"].items():
        rate = stats["pass"] / stats["total"] if stats["total"] else 0
        print(f"    {k:18s} {stats['pass']:2d}/{stats['total']:2d}  ({rate:.0%})")
    print()
    print(f"  NOTE: {summary['ACCEPTANCE_REMINDER']}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="hammerstein-7b-v026")
    p.add_argument("--host", default="127.0.0.1:11434")
    p.add_argument("--runs", type=int, default=2)
    p.add_argument("--temperature", type=float, default=0.3,
                   help="Lower than chat — extraction wants determinism.")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    system = EXTRACTION_SYSTEM_PROMPT

    today = dt.date.today().isoformat()
    safe_model = re.sub(r"[^a-zA-Z0-9_-]", "_", args.model)
    tag_suffix = f"-{args.tag}" if args.tag else ""
    out_path = DATA_DIR / f"eval-extraction-reliability-{safe_model}-{today}{tag_suffix}.json"

    print(f"extraction reliability eval — {args.model} via {args.host}")
    print(f"Probes: {len(PROBES)}, runs each: {args.runs}, temp: {args.temperature}")
    print(f"System prompt: {len(system)} chars")
    print(f"Output: {out_path}")
    print()

    summary = run_probe(args.model, args.host, args.runs, system, args.temperature)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print_summary(summary)
    print(f"\nFull results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
