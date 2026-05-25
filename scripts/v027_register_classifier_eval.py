#!/usr/bin/env python3
"""v0.2.7 register classifier eval (axis 2).

Spec: docs/handoffs/v0.2.7-eval-criteria-2026-05-25.md "Eval 6".

Tests whether the model picks the right register for the prompt shape:
  - audit-signal prompts ("audit this", "framework verdict on", "is this
    stupid-industrious") → audit-mode (quadrant cell + load-bearing
    observation about the situation)
  - casual-knowledge prompts ("what does X mean", "explain the framework")
    → explanation-mode (defines concept, conversational)

8 probes paired (4 audit-signal, 4 casual-knowledge). Gate: >=7/8.
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


PROBES = [
    # Audit-signal — expected register: AUDIT (quadrant + specific obs)
    {"id": "rc-01-audit-auth-rewrite", "register": "audit",
     "prompt": "audit this plan: rewrite the auth module before adding new features"},
    {"id": "rc-02-verdict-scrap-mvp", "register": "audit",
     "prompt": "framework verdict on: I'm going to scrap the MVP and start over"},
    {"id": "rc-03-stupid-industrious-flag", "register": "audit",
     "prompt": "is this stupid-industrious: I added a feature flag for a feature with no users"},
    {"id": "rc-04-shape-this-approach", "register": "audit",
     "prompt": "hammerstein, what shape is this approach"},
    # Casual-knowledge — expected register: EXPLANATION (define concept)
    {"id": "rc-05-remind-stupid-industrious", "register": "explanation",
     "prompt": "remind me what stupid-industrious means"},
    {"id": "rc-06-what-is-quadrant", "register": "explanation",
     "prompt": "what's the quadrant"},
    {"id": "rc-07-clever-lazy-vs-industrious", "register": "explanation",
     "prompt": "difference between clever-lazy and clever-industrious"},
    {"id": "rc-08-explain-framework", "register": "explanation",
     "prompt": "explain the framework to someone who hasn't seen it"},
]


# Quadrant cell names from Ray's framework — appearing in audit response
# indicates the model is applying the framework, not just defining it.
QUADRANT_CELLS = [
    r"\bclever[-\s]lazy\b",
    r"\bclever[-\s]industrious\b",
    r"\bstupid[-\s]lazy\b",
    r"\bstupid[-\s]industrious\b",
]


# Definition-mode markers — phrases that introduce a concept rather than
# apply it.
DEFINITION_MARKERS = [
    r"\b(?:is|means|refers\s+to|describes)\b",
    r"\bthe\s+(?:framework|quadrant|model|concept)\s+(?:is|describes)",
    r"\b(?:term|concept|idea)\s+(?:is|refers\s+to|means)",
]


# Audit-mode markers — applying the framework with specifics. Broadened
# 2026-05-25 to catch verdict-shape responses without explicit cell name
# (e.g. "Wrong order. New features ship against the current auth surface...").
# IMPORTANT: don't include bare cell names (clever-lazy / stupid-industrious)
# here — those appear in EXPLANATION responses too and would create false
# positives. Audit-apply requires the cell name to be APPLIED to a thing,
# not defined.
AUDIT_APPLICATION_MARKERS = [
    r"\bthis\s+(?:is|reads\s+as|looks\s+like|smells\s+like)\b",
    r"\bthe\s+(?:plan|approach|move)\s+(?:is|reads|looks)",
    r"\b(?:reads|smells|looks)\s+like\s+(?:clever|stupid)",
    r"\b(?:specific|load-?bearing|specifically)\s+(?:concern|issue|signal|question|reason)\b",
    r"\bthe\s+(?:concern|signal|issue|tell|right\s+move)\s+(?:is|here|here\s+is)",
    # Verdict-first audit shapes
    r"^\s*(?:wrong\s+order|right\s+move|wrong\s+move|misordered|premature|skip\s+this)\b",
    r"^\s*(?:audit\s+verdict|verdict)[:\.]",
    r"\bsunk\s+(?:time|cost)\b.*\b(?:write-?off|recapture)",
    r"\bverification[-\s]gate\b",
    r"\boperator[-\s]sharpening\b",
    # Operator-sharpening (limited) — valid audit response asking for
    # grounding before rendering verdict. Kept narrow to avoid false
    # positives on explanation-mode responses.
    r"\bwhat'?s\s+the\s+approach\??",
    r"\b(?:tell|describe)\s+me\s+(?:about|more\s+about)\s+the\s+approach",
    r"\bI\s+don'?t\s+have\s+context\s+on",
    r"\bdiagnose\s+the\s+shape\b",
    # Cell-name-as-verdict shapes ("X is stupid-industrious", "in stupid-industrious mode")
    # but NOT "stupid-industrious means..." or "stupid-industrious refers to..."
    r"\b(?:is|reads\s+as|operating\s+in|sits\s+in|in)\s+(?:clever|stupid|smart|dumb)[-\s](?:lazy|industrious)(?:\s+mode)?\b(?!\s+(?:means|refers))",
]


def matches_any(patterns: list[str], text: str) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.IGNORECASE)]


def grade_response(probe: dict, response: str) -> dict:
    text = response.strip()
    quadrant_hits = matches_any(QUADRANT_CELLS, text)
    definition_hits = matches_any(DEFINITION_MARKERS, text)
    audit_apply_hits = matches_any(AUDIT_APPLICATION_MARKERS, text)

    flags = {
        "probe_id": probe["id"],
        "register_expected": probe["register"],
        "quadrant_hits": quadrant_hits,
        "definition_marker_hits": definition_hits,
        "audit_apply_hits": audit_apply_hits,
    }

    if probe["register"] == "audit":
        # Audit-mode passes if ANY of:
        #   (a) names a quadrant cell AND has audit-apply OR is long-form (>=25w)
        #   (b) emits operator-sharpening response (refusing to verdict on
        #       content-less prompt) — the audit-apply markers include those shapes
        #   (c) emits verdict-shape ("Wrong order", "Right move", etc.) with
        #       substantive analysis — captured by audit_apply_hits
        # The substance test: at least one audit-apply hit AND non-trivial response.
        has_substantive_audit = bool(audit_apply_hits) and len(text.split()) >= 15
        has_named_cell_application = bool(quadrant_hits) and (bool(audit_apply_hits) or len(text.split()) >= 25)
        flags["passes"] = has_substantive_audit or has_named_cell_application
    else:
        # Explanation-mode passes: definition phrasing present AND
        # response is NOT applying-the-framework-to-a-specific-situation.
        # We're lenient here — explanation mode includes responses that
        # name multiple cells (e.g., listing the quadrant).
        flags["passes"] = bool(definition_hits) and (not audit_apply_hits)
    return flags


def query_ollama(model: str, prompt: str,
                 host: str = "127.0.0.1:11434",
                 timeout: int = 180,
                 temperature: float = 0.7) -> dict:
    url = f"http://{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "top_p": 0.9, "num_predict": 500},
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
        print(f"  [{i}/{len(PROBES)}] {probe['id']} [{probe['register']}]", end="", flush=True)
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
            "register": probe["register"],
            "runs": runs_data,
            "passes": passing,
            "total_runs": runs,
        })
        print(f"  ({passing}/{runs})")

    total_runs = sum(p["total_runs"] for p in per_probe)
    total_passes = sum(p["passes"] for p in per_probe)
    overall = (total_passes / total_runs) if total_runs else 0.0

    by_reg = {"audit": {"pass": 0, "total": 0},
              "explanation": {"pass": 0, "total": 0}}
    for p in per_probe:
        by_reg[p["register"]]["pass"] += p["passes"]
        by_reg[p["register"]]["total"] += p["total_runs"]

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
        "by_register": by_reg,
        "per_probe": per_probe,
        "ACCEPTANCE_REMINDER": (
            ">=7/8 pass. Heuristic auto-grade — borderline cases may "
            "warrant human review of full responses."
        ),
    }


def print_summary(summary: dict) -> None:
    print()
    print(f"=== register classifier — {summary['model']} ===")
    print(f"  Probes:    {summary['total_probes']}")
    print(f"  Passes:    {summary['total_passes']}/{summary['total_runs']}  ({summary['overall_pass_rate']:.0%})")
    print()
    print("  By register:")
    for r, stats in summary["by_register"].items():
        rate = stats["pass"] / stats["total"] if stats["total"] else 0
        print(f"    {r:12s} {stats['pass']:2d}/{stats['total']:2d}  ({rate:.0%})")
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
    out_path = DATA_DIR / f"eval-register-classifier-{safe_model}-{today}{tag_suffix}.json"

    print(f"register classifier eval — {args.model} via {args.host}")
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
