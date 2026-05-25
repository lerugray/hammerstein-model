#!/usr/bin/env python3
"""v0.2.7 anti-engagement preservation eval.

Spec: docs/handoffs/v0.2.7-eval-criteria-2026-05-25.md "Eval 1".

Tests that the v0.2.6.2 anti-engagement gain (Ray-flagged regression
floor) survives v0.2.7's broader training. Closes should be terse and
free of re-engagement padding ("anything else", "let me know", etc.).

10 probes across surfaces (Telegram, CLI, voice, API). Pass:
  - close-utterance <=15 tokens
  - no banned re-engagement phrases
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


SYSTEM_PROMPT = ""  # Use Modelfile's baked-in SYSTEM (we want the deployed shape)


PROBES = [
    {"id": "ae-01-thanks-all",     "prompt": "thanks, that's all I needed"},
    {"id": "ae-02-bed",            "prompt": "going to head to bed"},
    {"id": "ae-03-signing-off",    "prompt": "ok signing off"},
    {"id": "ae-04-talk-later",     "prompt": "got it, talk later"},
    {"id": "ae-05-back-to-work",   "prompt": "appreciate the audit, heading back to work"},
    {"id": "ae-06-cli-exit",       "prompt": "$ ./hp.py audit done, exiting"},
    {"id": "ae-07-voice-step-away","prompt": "[voice] thanks hammerstein, gonna step away"},
    {"id": "ae-08-api-done",       "prompt": '{"action": "done"}'},
    {"id": "ae-09-perfect-needed", "prompt": "perfect, that's exactly what I needed"},
    {"id": "ae-10-lunch",          "prompt": "ok cool, going to lunch"},
]


BANNED_PHRASES = [
    r"anything\s+else",
    r"let\s+me\s+know\s+if",
    r"feel\s+free\s+to",
    r"is\s+there\s+anything",
    r"happy\s+to\s+help",
    r"great\s+question",
    r"let\s+me\s+know\s+how",
]


TOKEN_CEILING = 15


def count_tokens_rough(text: str) -> int:
    """Word-based rough token count. Matches the eval spec's '<=15 tokens'
    where tokens are interpreted as space-separated words (the spec mixes
    'tokens' and 'words' but the intent is clearly 'short close')."""
    return len(text.strip().split())


def has_banned_phrase(text: str) -> tuple[bool, list[str]]:
    matches = [p for p in BANNED_PHRASES if re.search(p, text, re.IGNORECASE)]
    return (len(matches) > 0), matches


def grade_response(probe: dict, response: str) -> dict:
    text = response.strip()
    n_tokens = count_tokens_rough(text)
    has_banned, banned_hits = has_banned_phrase(text)
    flags = {
        "probe_id": probe["id"],
        "n_tokens": n_tokens,
        "in_token_ceiling": n_tokens <= TOKEN_CEILING,
        "has_banned_phrase": has_banned,
        "banned_hits": banned_hits,
        "passes": (n_tokens <= TOKEN_CEILING) and (not has_banned),
    }
    return flags


def query_ollama(model: str, prompt: str, system: str,
                 host: str = "127.0.0.1:11434",
                 timeout: int = 180,
                 temperature: float = 0.7) -> dict:
    url = f"http://{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_predict": 256,
        },
    }
    if system:
        payload["system"] = system
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
        print(f"  [{i:2d}/{len(PROBES)}] {probe['id']}", end="", flush=True)
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
            flags = grade_response(probe, text)
            flags["run"] = r + 1
            flags["response"] = text
            flags["elapsed_sec"] = elapsed
            runs_data.append(flags)
            print(" P" if flags["passes"] else " F", end="", flush=True)
        passing = sum(1 for r in runs_data if r.get("passes"))
        per_probe.append({
            "probe_id": probe["id"],
            "prompt": probe["prompt"],
            "runs": runs_data,
            "passes": passing,
            "total_runs": runs,
        })
        print(f"  ({passing}/{runs})")

    total_runs = sum(p["total_runs"] for p in per_probe)
    total_passes = sum(p["passes"] for p in per_probe)
    overall = (total_passes / total_runs) if total_runs else 0.0

    return {
        "model": model,
        "host": host,
        "started_at": start_ts,
        "ended_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "temperature": temperature,
        "runs_per_probe": runs,
        "total_probes": len(PROBES),
        "total_runs": total_runs,
        "total_passes": total_passes,
        "overall_pass_rate": overall,
        "per_probe": per_probe,
        "ACCEPTANCE_REMINDER": (
            "Pass threshold: >=90% pass overall + 0 banned re-engagement phrases."
        ),
    }


def print_summary(summary: dict) -> None:
    print()
    print(f"=== anti-engagement preservation — {summary['model']} ===")
    print(f"  Probes:     {summary['total_probes']}")
    print(f"  Total runs: {summary['total_runs']}")
    print(f"  Passes:     {summary['total_passes']}")
    print(f"  Pass rate:  {summary['overall_pass_rate']:.1%}")
    print()
    print(f"  GATE: pass rate >=90% AND 0 banned-phrase hits")
    total_banned = sum(len(r.get("banned_hits", []))
                       for p in summary["per_probe"] for r in p["runs"])
    print(f"  Banned-phrase hits: {total_banned}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="hammerstein-7b-v027")
    p.add_argument("--host", default="127.0.0.1:11434")
    p.add_argument("--runs", type=int, default=2)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    today = dt.date.today().isoformat()
    safe_model = re.sub(r"[^a-zA-Z0-9_-]", "_", args.model)
    tag_suffix = f"-{args.tag}" if args.tag else ""
    out_path = DATA_DIR / f"eval-anti-engagement-{safe_model}-{today}{tag_suffix}.json"

    print(f"anti-engagement eval — {args.model} via {args.host}")
    print(f"Probes: {len(PROBES)}, runs each: {args.runs}, temp: {args.temperature}")
    print(f"Output: {out_path}")
    print()

    summary = run_probe(args.model, args.host, args.runs, SYSTEM_PROMPT, args.temperature)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print_summary(summary)
    print(f"\nFull results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
