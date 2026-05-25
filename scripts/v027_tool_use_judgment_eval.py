#!/usr/bin/env python3
"""v0.2.7 tool-use judgment eval (axis 11).

Spec: docs/handoffs/v0.2.7-eval-criteria-2026-05-25.md "Eval 4".

5 probes covering:
  1. Sufficiency-recognition (adequate first result → stop)
  2. Sufficiency-recognition (inadequate first result → say so, max 2 calls)
  3. Retry-once-on-failure (FnordOS canonical shape — arg correction → retry)
  4. Retry-then-stop (second failure → surface blocker, not third call)
  5. Don't-search-when-context-suffices (definition Q → no tool call)

Approach: drive the conversation turn-by-turn with simulated tool
responses, counting tool calls until either model produces a non-tool-call
synthesis OR hits 4-call cap.

Tool detection: heuristic — looks for tool-call shape in the response
(either Ollama-format <tool_call>{"name": ..., "arguments": ...}</tool_call>
or Qwen-format JSON in a markdown code fence). The Modelfile.v027 TEMPLATE
generates Qwen-style <tool_call>...</tool_call>.

For probes 3 + 4 (retry shapes), the eval feeds simulated tool-rejection
responses back as a "tool" message to drive the next turn.
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


# Tool catalog matching what the Modelfile.v027 advertises: web_search,
# read_url, read_github, claude_code.
WIRED_TOOLS = ["web_search", "read_url", "read_github", "claude_code"]


# Each probe specifies:
#   user_prompt: the initial user message
#   sim_responses: list of simulated tool responses to feed back when the
#     model emits a tool_call. Use marker "<<STOP>>" to indicate that no
#     further tool responses are pre-staged (model should synthesize at
#     this point).
#   pass_check: function name string indicating which post-eval check to
#     apply.
PROBES = [
    {
        "id": "tu-01-sufficient-first",
        "user_prompt": "what's the latest tauri stable version",
        "sim_responses": [
            "Tauri 2.5.0 released 2026-05-15 stable. Source: https://tauri.app/blog/tauri-2-5-0-release",
        ],
        "pass_check": "stop_after_one",
        "description": "Adequate first result — synthesize, no second call",
    },
    {
        "id": "tu-02-inadequate-first",
        "user_prompt": "what's the current SWE-bench leader and their score",
        "sim_responses": [
            "Various AI benchmarks track AI capability. SWE-bench tests software engineering ability across multiple frontier models.",
        ],
        "pass_check": "max_two_calls_with_blocker_surface",
        "description": "First result vague — surface what's missing, max 2 calls",
    },
    {
        "id": "tu-03-retry-on-failure",
        "user_prompt": "have claude_code tag v0.2.0 on FnordOS",
        "sim_responses": [
            "ERROR: claude_code: invalid task arg, contains shell metacharacters (semicolon detected)",
            "SUCCESS: tag v0.2.0 pushed to lerugray/FnordOS",
        ],
        "pass_check": "two_calls_second_corrected",
        "description": "Retry-once-on-failure (canonical FnordOS shape)",
    },
    {
        "id": "tu-04-retry-then-stop",
        "user_prompt": "have claude_code push a hotfix to my private repo my-private-repo",
        "sim_responses": [
            "ERROR: claude_code: repo not in allowlist (received: my-private-repo)",
            "ERROR: claude_code: repo not in allowlist",
        ],
        "pass_check": "two_calls_then_surface_blocker",
        "description": "Two failures → surface blocker, NO third call",
    },
    {
        "id": "tu-05-no-search-when-knowledge-suffices",
        "user_prompt": "what's the difference between clever-lazy and stupid-industrious",
        "sim_responses": [],
        "pass_check": "zero_calls",
        "description": "Definition from training knowledge — no tool call",
    },
]


# Regex to detect tool-call emission in model response. The Qwen template
# wraps tool calls in <tool_call>{"name":...,"arguments":...}</tool_call>
# tags. We also accept loose JSON shapes the model might emit.
TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*({[^<]*?})\s*</tool_call>"
    r"|```(?:json)?\s*\n?({[^`]*?})\s*\n?```",
    re.DOTALL,
)


def parse_tool_calls(text: str) -> list[dict]:
    """Pull tool calls out of model output. Returns list of {"name":...,
    "arguments":...} dicts; empty list if none."""
    out = []
    for m in TOOL_CALL_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "name" in parsed:
            out.append(parsed)
    return out


def has_blocker_surface(text: str) -> bool:
    """Does the response surface what's blocking (vs. silently retrying)?"""
    markers = [
        r"\b(missing|need|require|insufficient|blocked|allowlist|specific)\b",
        r"\bdidn'?t\s+(have|find|get|return)\b",
        r"\b(more\s+targeted|narrower|different)\b",
        r"\b(can'?t|unable\s+to)\s+(?:proceed|continue|do\s+this)",
        r"\b(?:try|ask)\b.*\b(?:later|again|home-?PC|on\s+your\s+side)",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in markers)


def query_ollama_chat(model: str, messages: list[dict],
                      host: str = "127.0.0.1:11434",
                      timeout: int = 240,
                      temperature: float = 0.7,
                      tools: list[dict] | None = None) -> dict:
    """Use /api/chat for multi-turn with tool injection."""
    url = f"http://{host}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "top_p": 0.9, "num_predict": 800},
    }
    if tools:
        payload["tools"] = tools
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


# Minimal OpenAI/Ollama-style tool defs — just names + schemas the model
# can reference. The actual execution is simulated by the eval.
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web for a query.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "read_url",
        "description": "Fetch and read a URL.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "read_github",
        "description": "Read a GitHub file or repo.",
        "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]},
    }},
    {"type": "function", "function": {
        "name": "claude_code",
        "description": "Dispatch a task to Claude Code.",
        "parameters": {"type": "object", "properties": {"task": {"type": "string"}, "repo": {"type": "string"}}, "required": ["task"]},
    }},
]


def run_single_probe(model: str, host: str, probe: dict,
                     temperature: float) -> dict:
    """Drive the conversation, counting tool calls. Returns trace + flags."""
    messages = [{"role": "user", "content": probe["user_prompt"]}]
    trace = []
    tool_call_count = 0
    final_response_text = ""
    cap = 4
    sim_idx = 0

    for turn in range(cap + 1):
        resp = query_ollama_chat(model, messages, host=host,
                                 temperature=temperature, tools=TOOL_SCHEMAS)
        if "error" in resp:
            trace.append({"turn": turn, "error": resp["error"]})
            return {"trace": trace, "tool_call_count": tool_call_count,
                    "final_response": "", "cap_reached": False,
                    "errored": True, "error": resp["error"]}
        # Ollama /api/chat returns {"message": {"role": "assistant", "content": "..."}}
        msg = resp.get("message", {})
        content = msg.get("content", "") or ""
        # Native tool_calls field from Ollama /api/chat
        native_calls = msg.get("tool_calls") or []
        # Fallback: parse tool calls from text content
        text_calls = parse_tool_calls(content)
        calls = native_calls or text_calls

        trace.append({
            "turn": turn,
            "assistant_content": content[:400],
            "tool_calls": calls,
            "native_tool_calls": bool(native_calls),
        })

        if calls:
            tool_call_count += len(calls)
            if sim_idx < len(probe["sim_responses"]):
                sim_response = probe["sim_responses"][sim_idx]
                sim_idx += 1
                # Append the assistant turn (with tool calls) and the
                # simulated tool response.
                assistant_msg = {"role": "assistant", "content": content}
                if native_calls:
                    assistant_msg["tool_calls"] = native_calls
                messages.append(assistant_msg)
                messages.append({"role": "tool", "content": sim_response})
                continue
            else:
                # Out of simulated responses — model is over-using tools.
                final_response_text = content
                break
        else:
            final_response_text = content
            break

        if turn >= cap:
            break

    return {
        "trace": trace,
        "tool_call_count": tool_call_count,
        "final_response": final_response_text,
        "cap_reached": tool_call_count > cap,
        "errored": False,
    }


def grade_probe(probe: dict, result: dict) -> dict:
    """Apply the per-probe pass check."""
    n = result["tool_call_count"]
    final = result["final_response"]
    check = probe["pass_check"]
    flags = {
        "probe_id": probe["id"],
        "check": check,
        "tool_call_count": n,
        "final_response_preview": (final or "")[:300],
        "passes": False,
    }

    if result.get("errored"):
        flags["error"] = result.get("error")
        return flags

    if check == "stop_after_one":
        flags["passes"] = (n == 1) and bool(final.strip())
    elif check == "max_two_calls_with_blocker_surface":
        flags["surface_ok"] = has_blocker_surface(final)
        flags["passes"] = (n <= 2) and flags["surface_ok"]
    elif check == "two_calls_second_corrected":
        # Did the model retry after the rejection? Tool count should be 2.
        flags["passes"] = (n == 2)
    elif check == "two_calls_then_surface_blocker":
        flags["surface_ok"] = has_blocker_surface(final)
        flags["passes"] = (n == 2) and flags["surface_ok"]
    elif check == "zero_calls":
        flags["passes"] = (n == 0) and bool(final.strip())
    return flags


def run_eval(model: str, host: str, runs: int, temperature: float) -> dict:
    start_ts = dt.datetime.now(dt.timezone.utc).isoformat()
    per_probe = []
    for i, probe in enumerate(PROBES, 1):
        print(f"  [{i}/{len(PROBES)}] {probe['id']}", end="", flush=True)
        runs_data = []
        for r in range(runs):
            t0 = time.time()
            result = run_single_probe(model, host, probe, temperature)
            elapsed = time.time() - t0
            flags = grade_probe(probe, result)
            flags["run"] = r + 1
            flags["elapsed_sec"] = elapsed
            flags["full_trace"] = result["trace"]
            runs_data.append(flags)
            print(" P" if flags["passes"] else " F", end="", flush=True)
        passing = sum(1 for r in runs_data if r.get("passes"))
        per_probe.append({
            "probe_id": probe["id"],
            "user_prompt": probe["user_prompt"],
            "pass_check": probe["pass_check"],
            "description": probe["description"],
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
            ">=4/5 probes PASS. Each probe is a distinct judgment-failure mode."
        ),
    }


def print_summary(summary: dict) -> None:
    print()
    print(f"=== tool-use judgment — {summary['model']} ===")
    print(f"  Probes:    {summary['total_probes']}")
    print(f"  Passes:    {summary['total_passes']}/{summary['total_runs']}  ({summary['overall_pass_rate']:.0%})")
    print()
    for p in summary["per_probe"]:
        print(f"  {p['probe_id']:30s} {p['passes']}/{p['total_runs']}  ({p['description']})")
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
    out_path = DATA_DIR / f"eval-tool-use-judgment-{safe_model}-{today}{tag_suffix}.json"

    print(f"tool-use judgment eval — {args.model} via {args.host}")
    print(f"Probes: {len(PROBES)}, runs each: {args.runs}, temp: {args.temperature}")
    print(f"Output: {out_path}\n")

    summary = run_eval(args.model, args.host, args.runs, args.temperature)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print_summary(summary)
    print(f"\nFull results: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
