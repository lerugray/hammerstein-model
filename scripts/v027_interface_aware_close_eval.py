#!/usr/bin/env python3
"""v0.2.7 interface-aware close-language eval.

Spec: docs/handoffs/v0.2.7-eval-criteria-2026-05-25.md "Eval 2".

Tests axis 9: model adapts close-language to the conversational surface
(chat / CLI / voice / API) AND to the contextual signal (sleep vs.
midday vs. activity). The specific real-usage failure mode this catches:
v0.2.6.2 emitted "Sleep well." at 2:22 PM in response to a generic close
— generalization from the empathy-refusal training where "Sleep well."
was contextually correct (5 AM, sleep-mentioned).

12 probes, each annotated with expected close shape. PASS per probe
based on the annotated criterion.
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


# Sleep-language markers. Includes terse closes like "Night." / "Goodnight."
# that are sleep-aware without using the full "Sleep well." phrase. Initial
# regex missed these because they're shorter.
SLEEP_LANG = [r"sleep\s+well", r"good\s*night", r"sweet\s+dreams", r"sleep\s+tight",
              r"rest\s+up", r"goodnight", r"\bnight\.?\s*$", r"\bnight\b",
              r"sleep\s+(?:tight|good)"]
SHELL_LANG = [r"close\s+the\s+shell", r"exit\s+the\s+shell", r"close\s+the\s+session",
              r"end\s+the\s+session", r"close\s+the\s+terminal"]
API_LANG = [r"end\s+of\s+response", r"acknowledged", r"response\s+complete"]


PROBES = [
    # id, prompt, surface, time/context, expected_shape, banned (regex list), required (regex list — at-least-one)
    {"id": "ic-01-chat-midday-lunch", "prompt": "ok hammerstein got it, going to grab lunch",
     "surface": "chat", "context": "midday-activity",
     "banned": SLEEP_LANG, "required": []},
    {"id": "ic-02-chat-evening-no-sleep", "prompt": "alright that's the audit, going to step away",
     "surface": "chat", "context": "evening-no-sleep-cue",
     "banned": SLEEP_LANG, "required": []},
    {"id": "ic-03-chat-night-sleep-cue", "prompt": "thanks, going to head to bed",
     "surface": "chat", "context": "night-sleep-cue",
     "banned": [], "required": SLEEP_LANG},
    {"id": "ic-04-chat-generic", "prompt": "ok thanks",
     "surface": "chat", "context": "generic",
     "banned": SLEEP_LANG + SHELL_LANG, "required": []},
    {"id": "ic-05-cli-done-verdict", "prompt": "$ done reading the verdict, exiting",
     "surface": "cli", "context": "shell-exit",
     "banned": SLEEP_LANG, "required": []},
    {"id": "ic-06-cli-exit-hpweb", "prompt": "thanks, exiting hp_web.sh",
     "surface": "cli", "context": "shell-exit",
     "banned": SLEEP_LANG, "required": []},
    {"id": "ic-07-voice-bye", "prompt": "[voice-input transcript] alright thanks hammerstein",
     "surface": "voice", "context": "voice-close",
     "banned": SLEEP_LANG + SHELL_LANG + API_LANG, "required": []},
    {"id": "ic-08-voice-step-away", "prompt": "[voice] going to step away for a bit",
     "surface": "voice", "context": "voice-activity",
     "banned": SHELL_LANG + API_LANG, "required": []},
    {"id": "ic-09-api-complete", "prompt": '{"action": "complete"}',
     "surface": "api", "context": "api-done",
     "banned": SLEEP_LANG, "required": []},
    {"id": "ic-10-chat-work", "prompt": "appreciate the read, heading back to work",
     "surface": "chat", "context": "work-context",
     "banned": SLEEP_LANG, "required": []},
    {"id": "ic-11-chat-walk", "prompt": "going for a walk",
     "surface": "chat", "context": "activity",
     "banned": SLEEP_LANG + SHELL_LANG, "required": []},
    {"id": "ic-12-chat-tomorrow", "prompt": "checking back tomorrow",
     "surface": "chat", "context": "near-tomorrow",
     "banned": SLEEP_LANG, "required": []},
]


def matches_any(patterns: list[str], text: str) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.IGNORECASE)]


def grade_response(probe: dict, response: str) -> dict:
    text = response.strip()
    banned_hits = matches_any(probe["banned"], text)
    required_hits = matches_any(probe["required"], text) if probe["required"] else []
    required_ok = (not probe["required"]) or bool(required_hits)
    banned_ok = not banned_hits
    return {
        "probe_id": probe["id"],
        "surface": probe["surface"],
        "context": probe["context"],
        "banned_hits": banned_hits,
        "required_hits": required_hits,
        "required_ok": required_ok,
        "banned_ok": banned_ok,
        "passes": banned_ok and required_ok,
    }


def query_ollama(model: str, prompt: str,
                 host: str = "127.0.0.1:11434",
                 timeout: int = 180,
                 temperature: float = 0.7) -> dict:
    url = f"http://{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "top_p": 0.9, "num_predict": 256},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"error": f"connection: {e}"}
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": f"json: {e}"}


def run_probe(model: str, host: str, runs: int, temperature: float) -> dict:
    start_ts = dt.datetime.now(dt.timezone.utc).isoformat()
    per_probe = []
    for i, probe in enumerate(PROBES, 1):
        print(f"  [{i:2d}/{len(PROBES)}] {probe['id']} [{probe['surface']}/{probe['context']}]", end="", flush=True)
        runs_data = []
        for r in range(runs):
            t0 = time.time()
            resp = query_ollama(model, probe["prompt"], host=host, temperature=temperature)
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
            "surface": probe["surface"],
            "context": probe["context"],
            "runs": runs_data,
            "passes": passing,
            "total_runs": runs,
        })
        print(f"  ({passing}/{runs})")

    total_runs = sum(p["total_runs"] for p in per_probe)
    total_passes = sum(p["passes"] for p in per_probe)
    overall = (total_passes / total_runs) if total_runs else 0.0

    by_surface = {}
    for p in per_probe:
        s = p["surface"]
        by_surface.setdefault(s, {"pass": 0, "total": 0})
        by_surface[s]["pass"] += p["passes"]
        by_surface[s]["total"] += p["total_runs"]

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
        "by_surface": by_surface,
        "per_probe": per_probe,
        "ACCEPTANCE_REMINDER": (
            "12/12 pass = full PASS. 10-11/12 = MARGINAL (ship-allowed). <10/12 = FAIL. "
            "Critical: ANY 'Sleep well' on probes ic-01, ic-02, ic-04, ic-10, ic-11 is a hard fail."
        ),
    }


def print_summary(summary: dict) -> None:
    print()
    print(f"=== interface-aware close — {summary['model']} ===")
    print(f"  Probes:     {summary['total_probes']}")
    print(f"  Total runs: {summary['total_runs']}")
    print(f"  Passes:     {summary['total_passes']}  ({summary['overall_pass_rate']:.0%})")
    print()
    print("  By surface:")
    for s, stats in summary["by_surface"].items():
        rate = stats["pass"] / stats["total"] if stats["total"] else 0
        print(f"    {s:8s} {stats['pass']:2d}/{stats['total']:2d}  ({rate:.0%})")
    print(f"\n  GATE: {summary['ACCEPTANCE_REMINDER']}")


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
    out_path = DATA_DIR / f"eval-interface-aware-close-{safe_model}-{today}{tag_suffix}.json"

    print(f"interface-aware close eval — {args.model} via {args.host}")
    print(f"Probes: {len(PROBES)}, runs each: {args.runs}, temp: {args.temperature}")
    print(f"Output: {out_path}\n")

    summary = run_probe(args.model, args.host, args.runs, args.temperature)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print_summary(summary)
    print(f"\nFull results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
