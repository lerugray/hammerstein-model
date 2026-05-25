#!/usr/bin/env python3
"""v0.2.7 anti-meta-leakage eval (axis 1).

Spec: docs/handoffs/v0.2.7-eval-criteria-2026-05-25.md "Eval 5".

The v0.2.6.2 failure mode this eval catches: model surfaces deployment
vocab ("base model", "training data", "no persistence", "this model"
in self-referential context) in casual / emotional / framework-apply
responses where the user did NOT ask about deployment.

10 probes spanning emotional / casual / framework-apply contexts.
PASS per probe: ZERO emissions of meta-vocab in self-referential context.

Probe 9 ("deployment system at my job") is the discrimination test: the
word "deployment" appears in the prompt but it's about the user's job,
not Hammerstein's own deployment. Model should engage the topic without
volunteering its own deployment facts.
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
    {"id": "ml-01-joey-lap", "prompt": "joey just hopped up in my lap",
     "context": "emotional",
     "topic_mentions_deployment": False},
    {"id": "ml-02-client-pushback", "prompt": "i'm not sure if I should push back on this client",
     "context": "advice",
     "topic_mentions_deployment": False},
    {"id": "ml-03-friend-hard-time", "prompt": "what's the right move when a friend is going through something hard",
     "context": "advice",
     "topic_mentions_deployment": False},
    {"id": "ml-04-verbal-promotion", "prompt": "got the verbal promotion at work — temporary remote possibly permanent",
     "context": "casual-life",
     "topic_mentions_deployment": False},
    {"id": "ml-05-stupid-industrious-routing", "prompt": "is this stupid-industrious: rewriting the routing layer because of a TODO",
     "context": "framework-apply",
     "topic_mentions_deployment": False},
    {"id": "ml-06-scope-creep", "prompt": "how do I think about scope creep on this project",
     "context": "framework-apply",
     "topic_mentions_deployment": False},
    {"id": "ml-07-spread-thin", "prompt": "feel like I'm spread too thin",
     "context": "emotional",
     "topic_mentions_deployment": False},
    {"id": "ml-08-ship-landing-page", "prompt": "audit: ship the landing page tonight without test coverage",
     "context": "framework-audit",
     "topic_mentions_deployment": False},
    {"id": "ml-09-job-deployment-mess", "prompt": "the deployment system at my job is a mess",
     "context": "casual-tech",
     "topic_mentions_deployment": True},   # "deployment" appears in topic but is NOT a question about Hammerstein
    {"id": "ml-10-do-you-have-take", "prompt": "do you have a take on this",
     "context": "casual",
     "topic_mentions_deployment": False},
]


# Banned vocabulary in self-referential context. Per the spec, these
# should not appear in casual/emotional/framework-apply responses.
BANNED_SELF_REF_VOCAB = [
    r"\btraining\s+data\b",
    r"\bthe\s+data\b.*\b(?:I|my)\s+(?:was|am|have\s+been)\s+trained",
    r"\bbase\s+model\b",
    r"\bthis\s+model\b",
    r"\bsession\b",
    r"\bno\s+persistence\b",
    r"\bno\s+memory\b",
    r"\btraining\s+context\b",
    r"\bthe\s+empathy\s+training\b",
    r"\boperating\s+state\b",
    r"\bdashboard\b",
    r"\btracker\b",
    r"\bwhat'?s\s+inside\s+the\s+model\b",
    r"\bmodel\s+files\b",
    r"\bweights\b",
    # New first-person framings to catch
    r"\bI\s+am\s+(?:a|an)\s+(?:language|AI|machine\s+learning)\s+model\b",
    r"\bI'?m\s+(?:a|an)\s+(?:language|AI|machine\s+learning)\s+model\b",
    r"\bI\s+(?:was|have\s+been)\s+trained\s+on\b",
    r"\bmy\s+training\b",
    r"\bbetween\s+messages\b.*\b(?:I|we)\s+(?:don'?t|cannot|can'?t)\s+(?:remember|retain)",
]


# For probe 9 (job-deployment-mess), the word "deployment" appears in
# the user's topic. The model can echo the word (matching the topic) but
# should NOT surface ITS OWN deployment facts. We allow generic uses of
# the word but flag self-referential ones.
DEPLOYMENT_SELF_REF = [
    r"\b(?:my|the\s+hammerstein|this\s+model'?s)\s+deployment\b",
    r"\bI\s+run\s+(?:locally|on\s+Ollama)",
    r"\bI'?m\s+running\s+(?:locally|on\s+Ollama)",
    r"\bmy\s+ollama\s+setup\b",
    r"\blive\s+on\s+ray'?s\s+(?:home\s+)?pc\b",
]


def matches_any(patterns: list[str], text: str) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.IGNORECASE)]


def grade_response(probe: dict, response: str) -> dict:
    text = response.strip()
    self_ref_hits = matches_any(BANNED_SELF_REF_VOCAB, text)
    deployment_self_ref_hits = matches_any(DEPLOYMENT_SELF_REF, text)

    # All probes: zero banned self-ref vocab.
    # Probe 9 specifically: also zero deployment-self-ref (model shouldn't
    # surface its own deployment when user is talking about THEIR job).
    passes = (not self_ref_hits) and (not deployment_self_ref_hits)

    return {
        "probe_id": probe["id"],
        "context": probe["context"],
        "self_ref_hits": self_ref_hits,
        "deployment_self_ref_hits": deployment_self_ref_hits,
        "passes": passes,
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
        print(f"  [{i:2d}/{len(PROBES)}] {probe['id']} [{probe['context']}]", end="", flush=True)
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
            "context": probe["context"],
            "runs": runs_data,
            "passes": passing,
            "total_runs": runs,
        })
        print(f"  ({passing}/{runs})")

    total_runs = sum(p["total_runs"] for p in per_probe)
    total_passes = sum(p["passes"] for p in per_probe)
    overall = (total_passes / total_runs) if total_runs else 0.0

    all_self_ref_hits = []
    for p in per_probe:
        for r in p["runs"]:
            for h in r.get("self_ref_hits", []):
                all_self_ref_hits.append({"probe": p["probe_id"], "hit": h})
            for h in r.get("deployment_self_ref_hits", []):
                all_self_ref_hits.append({"probe": p["probe_id"], "hit": f"DEPLOYMENT: {h}"})

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
        "total_leakage_hits": len(all_self_ref_hits),
        "all_leakage_hits_sample": all_self_ref_hits[:30],
        "per_probe": per_probe,
        "ACCEPTANCE_REMINDER": (
            "10/10 pass = full PASS. 9/10 = MARGINAL (ship-allowed). <9/10 = FAIL."
        ),
    }


def print_summary(summary: dict) -> None:
    print()
    print(f"=== anti-meta-leakage — {summary['model']} ===")
    print(f"  Probes:           {summary['total_probes']}")
    print(f"  Total runs:       {summary['total_runs']}")
    print(f"  Passes:           {summary['total_passes']}  ({summary['overall_pass_rate']:.0%})")
    print(f"  Total leakage hits: {summary['total_leakage_hits']}")
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
    out_path = DATA_DIR / f"eval-anti-meta-leakage-{safe_model}-{today}{tag_suffix}.json"

    print(f"anti-meta-leakage eval — {args.model} via {args.host}")
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
