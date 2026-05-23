#!/usr/bin/env python3
"""v0.2.3 voice quality probe — tests the hybrid casual register +
relational reciprocation that v0.2.3 trained on.

Complements scripts/v023_self_state_probe.py (covers honest-about-state
fabrications) and scripts/v2_eval_failure_modes.py (covers v1's audit /
fabrication / sentence-continuation failure modes). This probe is the
voice-quality axis specifically.

15 prompts spanning: bare greetings, relational check-ins (require
reciprocation), capability casual, day-context, pushback, emotional
nuance. Heuristic checks: word count band, reciprocation presence on
relational, absence of commercial-LLM tics + framework vocabulary in
casual replies.

Runs each probe 3x at temp 0.7 (matching production).
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


RUNG1_SYSTEM_PROMPT = (
    "You are hammerstein-7b, the homelab model running locally on Ray's home "
    "PC via Ollama. v0.2.2 LoRA continuation on Qwen2.5-7B-Instruct base. No "
    "dashboard, no tracker, no persistent memory between Telegram messages. "
    "Voice: brief, casual, period-coded vocabulary available but not forced. "
    "Relational prompts may reciprocate (You? / Anything notable?). "
    "Audit / knowledge / refusal prompts do not end with follow-up questions."
)


# Each probe: prompt, category, whether reciprocation is expected.
PROBES = [
    # --- bare greetings (no reciprocation) ---
    {"id": "vp-01-hey", "prompt": "hey",
     "category": "bare_greeting", "expect_reciprocation": False},
    {"id": "vp-02-morning", "prompt": "morning",
     "category": "bare_greeting", "expect_reciprocation": False},
    {"id": "vp-03-yo", "prompt": "yo",
     "category": "bare_greeting", "expect_reciprocation": False},
    # --- relational check-ins (reciprocation expected) ---
    {"id": "vp-04-how-doing", "prompt": "how you doing?",
     "category": "relational", "expect_reciprocation": True},
    {"id": "vp-05-whats-new", "prompt": "what's new on your end?",
     "category": "relational", "expect_reciprocation": True},
    {"id": "vp-06-how-going", "prompt": "how's it going?",
     "category": "relational", "expect_reciprocation": True},
    {"id": "vp-07-holding-up", "prompt": "how you holding up?",
     "category": "relational", "expect_reciprocation": True},
    # --- day-context (light reciprocation OK, not required) ---
    {"id": "vp-08-long-day", "prompt": "long day on this end",
     "category": "day_context", "expect_reciprocation": False},
    {"id": "vp-09-rough-week", "prompt": "rough week so far",
     "category": "day_context", "expect_reciprocation": False},
    # --- capability casual (honest brief, no reciprocation) ---
    {"id": "vp-10-can-help", "prompt": "can you help me draft something quick?",
     "category": "capability", "expect_reciprocation": False},
    {"id": "vp-11-good-at-writing", "prompt": "you any good at editing prose?",
     "category": "capability", "expect_reciprocation": False},
    # --- pushback (confident, no capitulation, no reciprocation) ---
    {"id": "vp-12-disagree", "prompt": "I don't think that's right",
     "category": "pushback", "expect_reciprocation": False},
    {"id": "vp-13-sure", "prompt": "you sure about that?",
     "category": "pushback", "expect_reciprocation": False},
    # --- closer / acknowledgment (very brief) ---
    {"id": "vp-14-thanks", "prompt": "thanks",
     "category": "closer", "expect_reciprocation": False},
    {"id": "vp-15-talk-later", "prompt": "talk later",
     "category": "closer", "expect_reciprocation": False},
]


# Word-count bands by category.
WORD_BAND = {
    "bare_greeting":  (1, 6),
    "relational":     (4, 35),
    "day_context":    (3, 30),
    "capability":     (4, 35),
    "pushback":       (4, 50),
    "closer":         (1, 8),
}


RECIPROCATION_MARKERS = [
    r"\byou\?",
    r"\banything\s+(?:notable|new|up)\??\s*$",
    r"\bwhat's\s+(?:on\s+your\s+end|going\s+on|up)\??\s*$",
    r"\bwhat\s+about\s+you",
    r"\bhow\s+about\s+you",
    r"\byour\s+end\??\s*$",
]

COMMERCIAL_LLM_TICS = [
    r"\banything\s+I\s+can\s+help",
    r"\bhow\s+can\s+I\s+assist",
    r"\bhappy\s+to\s+help",
    r"\bfeel\s+free\s+to",
    r"\blet\s+me\s+know\s+if\s+you",
    r"\bI'?m\s+(?:here\s+)?to\s+help",
    r"\bI'd\s+be\s+happy\s+to",
]

FRAMEWORK_VOCAB_LEAK = [
    r"\bverification\s+gate",
    r"\boperating-state",
    r"\bstructural\s+fix",
    r"\bclever[-\s]lazy",
    r"\bstupid[-\s]industrious",
    r"\bgsd-\d+",
]


def has_reciprocation(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in RECIPROCATION_MARKERS)


def has_commercial_tic(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in COMMERCIAL_LLM_TICS)


def has_framework_leak(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in FRAMEWORK_VOCAB_LEAK)


def flag_response(probe: dict, response: str) -> dict:
    text = response.strip()
    words = len(text.split())
    cat = probe["category"]
    low, high = WORD_BAND.get(cat, (1, 100))
    word_band_ok = low <= words <= high
    has_recip = has_reciprocation(text)
    if probe["expect_reciprocation"]:
        reciprocation_ok = has_recip
    else:
        # For non-relational, reciprocation absent is correct; present is
        # a softer warning (not a hard fail unless framework- or
        # commercial-tic shaped).
        reciprocation_ok = True
    commercial_ok = not has_commercial_tic(text)
    framework_ok = not has_framework_leak(text)
    passes = word_band_ok and reciprocation_ok and commercial_ok and framework_ok
    return {
        "probe_id": probe["id"],
        "category": cat,
        "word_count": words,
        "in_word_band": word_band_ok,
        "has_reciprocation": has_recip,
        "reciprocation_correct": reciprocation_ok,
        "commercial_tic_clean": commercial_ok,
        "framework_leak_clean": framework_ok,
        "passes": passes,
    }


def query_ollama(model: str, prompt: str, system: str,
                 host: str = "127.0.0.1:11434",
                 timeout: int = 180,
                 temperature: float = 0.7) -> dict:
    url = f"http://{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_predict": 512,
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
        print(f"  [{i:2d}/{len(PROBES)}] {probe['id']} ({probe['category']})", end="", flush=True)
        runs_data = []
        for r in range(runs):
            t0 = time.time()
            resp = query_ollama(model, probe["prompt"], system, host=host,
                                temperature=temperature)
            elapsed = time.time() - t0
            if "error" in resp:
                runs_data.append({"run": r + 1, "error": resp["error"]})
                print(" ERR", end="", flush=True); continue
            text = resp.get("response", "")
            flags = flag_response(probe, text)
            flags["run"] = r + 1
            flags["response"] = text
            flags["elapsed_sec"] = elapsed
            runs_data.append(flags)
            print(" P" if flags["passes"] else " F", end="", flush=True)
        passing = sum(1 for r in runs_data if r.get("passes"))
        per_probe.append({
            "probe_id": probe["id"],
            "prompt": probe["prompt"],
            "category": probe["category"],
            "expect_reciprocation": probe["expect_reciprocation"],
            "runs": runs_data,
            "passes": passing,
            "total_runs": runs,
        })
        print(f"  ({passing}/{runs})")

    total_runs = sum(p["total_runs"] for p in per_probe)
    total_passes = sum(p["passes"] for p in per_probe)
    overall = (total_passes / total_runs) if total_runs else 0.0

    cat_stats = {}
    for p in per_probe:
        c = p["category"]
        cat_stats.setdefault(c, {"pass": 0, "total": 0})
        cat_stats[c]["pass"] += p["passes"]
        cat_stats[c]["total"] += p["total_runs"]

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
        "per_category": cat_stats,
        "per_probe": per_probe,
    }


def print_summary(summary: dict) -> None:
    print()
    print(f"=== voice probe — {summary['model']} ===")
    print(f"  Probes:        {summary['total_probes']}")
    print(f"  Runs each:     {summary['runs_per_probe']}")
    print(f"  Total runs:    {summary['total_runs']}")
    print(f"  Passes:        {summary['total_passes']}")
    print(f"  Pass rate:     {summary['overall_pass_rate']:.1%}")
    print()
    print("  By category:")
    for cat, stats in summary["per_category"].items():
        rate = stats["pass"] / stats["total"] if stats["total"] else 0
        print(f"    {cat:18s} {stats['pass']:2d}/{stats['total']:2d}  ({rate:.0%})")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="hammerstein-7b-v022")
    p.add_argument("--host", default="127.0.0.1:11434")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--tag", default=None)
    p.add_argument("--system-prompt-file", default=None,
                   help="Override the default deployment-facts system prompt.")
    p.add_argument("--no-system-prompt", action="store_true")
    args = p.parse_args()

    if args.no_system_prompt:
        system = ""
    elif args.system_prompt_file:
        system = Path(args.system_prompt_file).read_text(encoding="utf-8")
    else:
        system = RUNG1_SYSTEM_PROMPT

    today = dt.date.today().isoformat()
    safe_model = re.sub(r"[^a-zA-Z0-9_-]", "_", args.model)
    tag_suffix = f"-{args.tag}" if args.tag else ""
    out_path = DATA_DIR / f"eval-voice-probe-{safe_model}-{today}{tag_suffix}.json"

    print(f"voice probe — {args.model} via {args.host}")
    print(f"Probes: {len(PROBES)}, runs each: {args.runs}, temp: {args.temperature}")
    print(f"System prompt: {'(none)' if not system else f'{len(system)} chars'}")
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
