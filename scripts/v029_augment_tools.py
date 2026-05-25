#!/usr/bin/env python3
"""v0.2.9 tool-use augmenter.

Reads the v0.2.7-tool-use-judgment.jsonl and v0.2.7-tool-routing-alignment.jsonl
pairs (original structured tool_calls format) and emits augmented copies
with a `tools` field per row containing the 4 wired Hammerstein tool
schemas (extracted from homelab/bot/tools.mjs TOOL_REGISTRY 2026-05-25).

Per docs/handoffs/v0.2.9-from-privategs-orchestrator-2026-05-25.md:
"Same 4-tool schema list on every tool-using row (matches what Ollama
renders at inference per the Modelfile template)."
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


# Mirror of homelab/bot/tools.mjs TOOL_REGISTRY (2026-05-25). Ground-truth
# source: the bot's TOOL_REGISTRY export at homelab/bot/tools.mjs:250-318.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the public web and return the top results with "
                "title, URL, and a short excerpt. Use when the user asks "
                "a question whose answer is not in your training (recent "
                "events, specific facts, current prices) or when you need "
                "to find a URL to read in detail."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",
                              "description": "The search query — write it as you would in Google."},
                    "k": {"type": "integer",
                          "description": "Number of results to return (1-10).",
                          "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": (
                "Fetch a single URL and return the page text "
                "(Readability-extracted for articles, raw for plain text/JSON). "
                "Use after web_search to read a specific result in full, "
                "or when the user shares a URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full http(s) URL to fetch."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_github",
            "description": (
                "Fetch GitHub repo content: with just owner+repo returns "
                "README + entry-point source files (smart picking). With "
                "path returns that single file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "GitHub username or org."},
                    "repo":  {"type": "string", "description": "GitHub repo name."},
                    "ref":   {"type": "string", "description": "Branch or tag (default: main)."},
                    "path":  {"type": "string", "description": "Optional path within the repo to fetch a single file."},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "claude_code",
            "description": (
                "Dispatch a Claude Code CLI session against a local repo "
                "on home-PC to perform a coding task. Use this when you "
                "need to actually MODIFY code, run builds, execute scripts, "
                "or do anything that requires filesystem write access — "
                "your other tools are read-only. Claude Code is a full "
                "coding agent; it will plan, edit files, run commands, "
                "and report what it did. The task must be a SINGLE narrow "
                "deliverable (under 500 chars) — scope down before calling. "
                "The bot enforces a repo allowlist; only repos in "
                "CLAUDE_AGENT_ALLOWED_REPOS env var (defaults to "
                "[\"homelab\"]) are reachable. Returns a short summary of "
                "what Claude did + exit code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": (
                            "Repo slug (directory name under the project root). "
                            "Must be in the allowlist. Default allowlist: "
                            "[\"homelab\"]. Operator may have expanded via "
                            "CLAUDE_AGENT_ALLOWED_REPOS env."
                        ),
                    },
                    "task": {
                        "type": "string",
                        "description": (
                            "Plain-English task description for Claude. "
                            "Single narrow deliverable. No shell commands "
                            "or shell metacharacters; Claude will run "
                            "tools itself. Under 500 chars."
                        ),
                    },
                },
                "required": ["repo", "task"],
            },
        },
    },
]


SOURCES = [
    ("v0.2.7-tool-use-judgment.jsonl",       "v0.2.9-tool-use-judgment-augmented.jsonl"),
    ("v0.2.7-tool-routing-alignment.jsonl",  "v0.2.9-tool-routing-alignment-augmented.jsonl"),
]


def main() -> int:
    for src_name, out_name in SOURCES:
        src = DATA_DIR / src_name
        out = DATA_DIR / out_name
        if not src.exists():
            print(f"  ERROR: source not found: {src}")
            continue
        n = 0
        with src.open("r", encoding="utf-8") as fin, out.open("w", encoding="utf-8") as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                obj["tools"] = TOOL_SCHEMAS
                fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                n += 1
        print(f"  {src_name:50s} -> {out_name:50s} ({n} pairs augmented)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
