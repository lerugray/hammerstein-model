#!/usr/bin/env python3
"""rung1_chat.py - two-stage tool-loop CLI for hammerstein with Rung 1.

Two-stage architecture:

  Stage 1 (research): a tool-capable model (qwen3:8b by default) runs
  the tool loop, retrieving grounded facts from the local library /
  web. Default because hammerstein v1's LoRA weakened its tool-call
  format discipline — qwen3:8b base follows the format reliably.

  Stage 2 (voice): hammerstein-7b restyles the research output into
  its staff-officer voice. Single API call with the research answer
  as input + a restyle system prompt. Keeps the voice spec while
  giving us reliable tool use.

Pass --voice-model "" to skip stage 2 and return the research model's
raw output (useful for debugging the tool loop).

Tools available to the research model:

  - library_search(query, limit=3)
      Full-text search across Ray's local BookFinder library.
      Primary tool for any factual/historical question — preferred over
      web_search because it returns text from books Ray actually has on
      disk (Figes / Howard / Royle / Pakenham / etc).

  - library_read(book_id, max_chars=4000)
      Pull the text of a specific book the model identified via
      library_search. Use to follow up after a hit.

  - web_search(query, limit=5)
      DuckDuckGo search via ddgs. Use only when library_search misses
      (current events, code references, weather, etc).

Single-file by design. No Telegram bot integration yet — once the
two-stage flow validates, follow-up wires this into homelab/bot/server.mjs.

Usage:
  python scripts/rung1_chat.py "What did Napoleon III accomplish?"
  python scripts/rung1_chat.py --research-model qwen3:8b --voice-model hammerstein-7b "..."
  python scripts/rung1_chat.py --voice-model "" "..."     # research-only, no restyle
  python scripts/rung1_chat.py --voice-model "" --research-model hammerstein-7b-tools "..."
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path


# Allow importing bookfinder_general without it being pip-installed.
BOOKFINDER_PATH = Path("C:/Users/rweis/OneDrive/Documents/bookfinder-general")
if BOOKFINDER_PATH.exists():
    sys.path.insert(0, str(BOOKFINDER_PATH))

os.environ.setdefault("BOOKFINDER_LIBRARY", "C:/Users/rweis/Research/BookFinder")


# --------------------------------------------------------- tool definitions

# OpenAI/Qwen tool-call schema — Ollama's /api/chat accepts these directly
# and passes them through to Qwen2.5-7B-Instruct's chat template.

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "library_search",
            "description": (
                "Full-text search across Ray's local research library "
                "(books downloaded via bookfinder-general). Use this as "
                "the primary tool for any factual or historical question — "
                "the library has depth on military history (Crimean War, "
                "Franco-Prussian War, ancient warfare, etc).\n\n"
                "QUERY SHAPE: use SIMPLE keyword queries — 1-3 words from "
                "the actual book text, NOT author names mixed with topics. "
                "Good: 'Sevastopol' or 'Borodino casualties' or 'Auftragstaktik'. "
                "Bad: 'Royle Sevastopol Crimean War' (mixes author + topic + "
                "war name → conjunctive AND-match fails). "
                "If the first search misses, retry with shorter / broader "
                "terms before falling back to web_search.\n\n"
                "Returns book_id + title + author + up to 3 excerpts per hit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — keywords work well; "
                                       "phrase queries are not supported."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of snippet results "
                                       "(default 3, max 10).",
                        "default": 3
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "library_read",
            "description": (
                "Fetch the full text (up to max_chars) of a specific book "
                "from the local library, identified by the book_id returned "
                "from library_search. Use after library_search to read "
                "more context if a snippet looks promising."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "string",
                        "description": "The book_id from a library_search "
                                       "result."
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Truncate response after this many "
                                       "characters (default 4000).",
                        "default": 4000
                    }
                },
                "required": ["book_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "DuckDuckGo web search. Use ONLY when library_search misses — "
                "for current events, contemporary code references, weather, "
                "or topics outside the local book library's scope. Returns "
                "up to `limit` results with title + snippet + URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of results (default 5).",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    }
]


# --------------------------------------------------------- tool executors

def tool_library_search(query: str, limit: int = 3) -> dict:
    """Run a full-text search across Ray's local library."""
    try:
        from bookfinder_general import library
    except ImportError as e:
        return {"error": f"bookfinder_general not importable: {e}"}

    limit = max(1, min(int(limit or 3), 10))
    try:
        hits = library.search_library(query, max_results=limit)
    except Exception as e:
        return {"error": f"library.search_library failed: {e}"}

    results = []
    for h in hits:
        # SearchHit is a dict with keys: book_id, title, author, file, excerpts
        # `excerpts` is a list of snippet strings around match terms.
        if isinstance(h, dict):
            excerpts = h.get("excerpts") or []
            entry = {
                "book_id": h.get("book_id"),
                "title": h.get("title"),
                "author": h.get("author"),
                "excerpts": [e[:400] for e in excerpts[:3]],
            }
        else:
            excerpts = getattr(h, "excerpts", None) or []
            entry = {
                "book_id": getattr(h, "book_id", None),
                "title": getattr(h, "title", None),
                "author": getattr(h, "author", None),
                "excerpts": [str(e)[:400] for e in excerpts[:3]],
            }
        results.append(entry)
    return {"query": query, "results": results, "count": len(results)}


def tool_library_read(book_id: str, max_chars: int = 4000) -> dict:
    """Fetch the text of a specific book."""
    try:
        from bookfinder_general import library
    except ImportError as e:
        return {"error": f"bookfinder_general not importable: {e}"}

    max_chars = max(500, min(int(max_chars or 4000), 20000))
    try:
        text = library.get_book_content(book_id, max_chars=max_chars)
    except Exception as e:
        return {"error": f"library.get_book_content failed: {e}"}

    if text is None:
        return {"error": f"book_id not found: {book_id}"}

    return {
        "book_id": book_id,
        "char_count": len(text),
        "text": text,
        "truncated": len(text) >= max_chars,
    }


def tool_web_search(query: str, limit: int = 5) -> dict:
    """DuckDuckGo search via ddgs."""
    try:
        from ddgs import DDGS
    except ImportError as e:
        return {"error": f"ddgs not installed: {e}"}

    limit = max(1, min(int(limit or 5), 10))
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=limit))
    except Exception as e:
        return {"error": f"ddgs failed: {e}"}

    results = []
    for r in raw:
        results.append({
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": (r.get("body", "") or "")[:400],
        })
    return {"query": query, "results": results, "count": len(results)}


TOOL_DISPATCH = {
    "library_search": tool_library_search,
    "library_read": tool_library_read,
    "web_search": tool_web_search,
}


# --------------------------------------------------------- ollama client

def ollama_chat(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    host: str = "127.0.0.1:11434",
    timeout: int = 180,
) -> dict:
    """POST to Ollama's /api/chat. Returns the parsed JSON response."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7, "top_p": 0.9, "num_predict": 512},
    }
    if tools:
        payload["tools"] = tools

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"error": f"ollama URL error: {e}"}
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": f"ollama JSON decode error: {e}"}


# --------------------------------------------------------- system prompt

RESEARCH_SYSTEM_PROMPT = """You are the research stage of a two-stage \
chat pipeline. Your job is to retrieve grounded facts via tools and \
produce a factually correct answer. A separate voice-styling stage will \
restyle your output later — don't worry about voice; focus on accuracy \
and sourcing.

You have three tools available:

  - library_search: full-text search of Ray's local book library.
  - library_read: pull a specific book's text after a library_search hit.
  - web_search: DuckDuckGo, for topics outside the local library.

MANDATORY TOOL USE — your prior training contains fabricated facts. \
Before you produce ANY of the following, you MUST call a tool and \
ground your response in the result:

  - Specific dates, years, casualty figures, troop counts
  - Quotes from named people or books
  - Citations of specific papers, podcasts, or sources
  - Claims about WHO did WHAT WHEN in history
  - Population numbers, GDP figures, statistics
  - Any factual claim where being wrong would mislead Ray

The order: library_search FIRST (your library has depth on Crimean, \
Franco-Prussian, Austro-Prussian, ancient Greek / Hellenistic, broader \
military history). If library_search returns nothing useful after 2 \
keyword retries, fall back to web_search. Cite the source in your \
response — title + author for library, URL for web.

If both tools come up empty, refuse honestly: "I can't verify this \
without a source I trust." Do NOT fabricate.

Output style:
- Factual, grounded, with inline citation (book title + author for \
library hits, URL for web). The voice stage will polish — don't over-style.
- Brief but complete. Include the specific facts (dates, names, places, \
figures) that the user's question is asking for.
- If tools come up empty, say so honestly. Do NOT fabricate to fill \
the gap.

QUERY SHAPE FOR library_search: simple 1-3 keyword queries from actual \
book text. Bad: "Royle Sevastopol Crimean War" (AND-match fails). Good: \
"Sevastopol" then narrow with "Sevastopol casualties".
"""


VOICE_SYSTEM_PROMPT = """You are hammerstein-7b, running locally on \
Ray's home PC. You hold the Hammerstein framework's structural-fix / \
clever-lazy / stupid-industrious discipline as your operating disposition.

You're the voice-styling stage of a two-stage pipeline. The previous \
stage has already done the research and produced a factually grounded \
answer with source citations. Your job is to restyle that answer in \
your staff-officer voice WITHOUT changing the facts or dropping the \
citations.

Voice rules:
- Brief by default. 1-3 sentences for casual greetings/questions; \
structured for audits.
- Period-coded, observational, clipped. No JSON, no schemas, no \
verification-gate Booleans, no "Plain English summary:" preamble.
- No closing follow-up questions unless genuinely load-bearing.
- Honest about uncertainty when the research stage flagged it.
- KEEP THE CITATIONS the research stage included. Don't drop sources \
to make the response feel cleaner.
- NEVER add new facts, dates, names, or citations the research stage \
didn't include. You're styling, not adding.
"""


# --------------------------------------------------------- the loop

def run_loop(
    model: str,
    user_prompt: str,
    host: str,
    max_rounds: int = 3,
    verbose: bool = False,
) -> dict:
    """Run the tool loop until the model returns a text-only response (no
    further tool calls), errors, or we hit max_rounds. Returns the
    accumulated transcript + final reply."""
    messages = [
        {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    tool_round = 0
    transcript = []

    while tool_round < max_rounds:
        resp = ollama_chat(model, messages, tools=TOOLS_SCHEMA, host=host)
        if "error" in resp:
            return {"error": resp["error"], "transcript": transcript}

        msg = resp.get("message", {})
        content = msg.get("content", "") or ""
        tool_calls = msg.get("tool_calls", []) or []

        transcript.append({
            "round": tool_round,
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        })

        if verbose:
            print(f"--- assistant round {tool_round} ---", file=sys.stderr)
            if content:
                print(f"[content]\n{content}", file=sys.stderr)
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    print(f"[tool_call] {fn.get('name')}({fn.get('arguments')})", file=sys.stderr)

        if not tool_calls:
            return {
                "final_content": content,
                "rounds_used": tool_round,
                "transcript": transcript,
            }

        # Append the assistant message + execute the tool calls + append results
        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        })
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments", {}) or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            dispatch = TOOL_DISPATCH.get(name)
            if dispatch is None:
                tool_result = {"error": f"unknown tool: {name}"}
            else:
                try:
                    tool_result = dispatch(**args)
                except TypeError as e:
                    tool_result = {"error": f"bad args for {name}: {e}"}

            transcript.append({
                "round": tool_round,
                "role": "tool",
                "tool_name": name,
                "tool_args": args,
                "tool_result": tool_result,
            })

            if verbose:
                print(f"[tool_result] {name} -> {json.dumps(tool_result)[:300]}",
                      file=sys.stderr)

            messages.append({
                "role": "tool",
                "content": json.dumps(tool_result, ensure_ascii=False),
            })

        tool_round += 1

    # Hit max_rounds — append a directive + final call without tools.
    messages.append({
        "role": "user",
        "content": (
            "You've used the max tool-call budget. Now produce the final "
            "answer based on what the tools returned (or, if they came "
            "up empty, refuse honestly per the system prompt). Brief "
            "and grounded; cite sources from the tool results."
        )
    })
    final = ollama_chat(model, messages, tools=None, host=host)
    if "error" in final:
        return {"error": final["error"], "transcript": transcript,
                "rounds_used": tool_round}
    final_content = (final.get("message", {}) or {}).get("content", "")
    transcript.append({"round": tool_round, "role": "assistant",
                       "content": final_content, "forced_final": True})
    return {
        "final_content": final_content,
        "rounds_used": tool_round,
        "transcript": transcript,
        "hit_max_rounds": True,
    }


# --------------------------------------------------------- entry point

def restyle_with_voice(
    voice_model: str,
    user_prompt: str,
    research_output: str,
    host: str,
    verbose: bool = False,
) -> dict:
    """Stage 2: feed the research output into hammerstein-7b and ask it
    to restyle in its voice. Single Ollama call, no tools."""
    voice_user_msg = (
        f"User asked:\n{user_prompt}\n\n"
        f"Research stage produced this factually grounded answer:\n"
        f"---\n{research_output}\n---\n\n"
        f"Restyle in your voice. Keep all the facts and citations; do "
        f"not add new ones."
    )
    messages = [
        {"role": "system", "content": VOICE_SYSTEM_PROMPT},
        {"role": "user", "content": voice_user_msg},
    ]
    resp = ollama_chat(voice_model, messages, tools=None, host=host)
    if "error" in resp:
        return {"error": resp["error"]}
    content = (resp.get("message", {}) or {}).get("content", "")
    if verbose:
        print(f"--- voice stage output ---\n{content}", file=sys.stderr)
    return {"voice_content": content, "messages": messages}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prompt", help="The user prompt to send.")
    p.add_argument("--research-model", default="qwen3:8b",
                   help="Ollama model for the tool loop (default: qwen3:8b)")
    p.add_argument("--voice-model", default="",
                   help="Ollama model for voice restyling. Default off; "
                        "pass --voice-model hammerstein-7b to enable stage 2. "
                        "v0 ships research-only because hammerstein's LoRA "
                        "fine-tuning makes it unreliable as a restyler "
                        "(adds new facts, echoes the user-instruction wrapper). "
                        "Voice restyle is a v0.1.1+ followup; the v0.2.2 "
                        "training pass should include system-prompt-following "
                        "training pairs to fix this.")
    p.add_argument("--host", default="127.0.0.1:11434",
                   help="Ollama host:port (default: 127.0.0.1:11434)")
    p.add_argument("--max-rounds", type=int, default=4,
                   help="Max tool-call rounds before forcing a final answer "
                        "(default 4)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Print each round's assistant message + tool calls.")
    p.add_argument("--transcript-out", default=None,
                   help="Optional path to write the full transcript JSON.")
    args = p.parse_args()

    if args.verbose:
        print(f"=== stage 1 (research): {args.research_model} ===", file=sys.stderr)
    research = run_loop(args.research_model, args.prompt, args.host,
                        max_rounds=args.max_rounds, verbose=args.verbose)

    if "error" in research:
        print(f"ERROR (research stage): {research['error']}", file=sys.stderr)
        return 1

    research_content = research.get("final_content", "").strip()
    final_output = research_content

    voice = None
    if args.voice_model:
        if args.verbose:
            print(f"\n=== stage 2 (voice): {args.voice_model} ===", file=sys.stderr)
        voice = restyle_with_voice(args.voice_model, args.prompt,
                                   research_content, args.host,
                                   verbose=args.verbose)
        if "error" in voice:
            print(f"WARN (voice stage failed: {voice['error']}); falling back "
                  f"to research output", file=sys.stderr)
        else:
            final_output = voice.get("voice_content", research_content).strip()

    print(final_output)

    if args.transcript_out:
        out = {
            "user_prompt": args.prompt,
            "research_model": args.research_model,
            "voice_model": args.voice_model or None,
            "research": research,
            "voice": voice,
            "final_output": final_output,
        }
        Path(args.transcript_out).write_text(
            json.dumps(out, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n[transcript saved to {args.transcript_out}]",
              file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
