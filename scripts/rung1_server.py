#!/usr/bin/env python3
"""rung1_server.py — HTTP sidecar that wraps the Rung 1 tool loop.

Drop-in replacement for Ollama's /api/chat from the bot's perspective:
- Accepts POST /api/chat with the standard Ollama chat-completion body
- Internally calls Ollama with the tools schema
- If the model emits tool_calls, dispatches to library_search / library_read /
  web_search, feeds results back, iterates
- Returns a final Ollama-shaped response with the grounded reply

The homelab Telegram bot points at this sidecar instead of Ollama directly
(via its OLLAMA env var or constant). Bot code stays unchanged otherwise.

Usage:
  python scripts/rung1_server.py --port 8766
  python scripts/rung1_server.py --port 8766 --model hammerstein-7b-v022 --max-rounds 3

The bot's homelab/.env should be updated to:
  OLLAMA_URL=http://127.0.0.1:8766/api/chat
  MODEL=hammerstein-7b-v022
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Make bookfinder_general + ddgs importable.
BOOKFINDER_PATH = Path("C:/Users/rweis/OneDrive/Documents/bookfinder-general")
if BOOKFINDER_PATH.exists():
    sys.path.insert(0, str(BOOKFINDER_PATH))

os.environ.setdefault("BOOKFINDER_LIBRARY", "C:/Users/rweis/Research/BookFinder")

LOG = logging.getLogger("rung1_server")


# --------------------------------------------------------- tool schema

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "library_search",
            "description": (
                "Full-text search across Ray's local book library (Crimean / "
                "Franco-Prussian / ancient Greek / military history depth). "
                "Use this FIRST for any factual or historical question. "
                "Simple 1-3 keyword queries from actual book text. "
                "Returns book_id + title + author + up to 3 excerpts per hit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "limit": {"type": "integer", "description": "Max hits (default 3, max 10).", "default": 3},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "library_read",
            "description": (
                "Fetch full text (up to max_chars) of a specific book by "
                "book_id from a library_search result. Use after a search "
                "hit looks promising."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 4000},
                },
                "required": ["book_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "DuckDuckGo web search. Use ONLY when library_search returns "
                "nothing useful (current events, code references, weather, "
                "topics outside the local book library)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
]


# --------------------------------------------------------- tools

def tool_library_search(query: str, limit: int = 3) -> dict:
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
        if isinstance(h, dict):
            excerpts = h.get("excerpts") or []
            results.append({
                "book_id": h.get("book_id"),
                "title": h.get("title"),
                "author": h.get("author"),
                "excerpts": [str(e)[:400] for e in excerpts[:3]],
            })
    return {"query": query, "results": results, "count": len(results)}


def tool_library_read(book_id: str, max_chars: int = 4000) -> dict:
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
    return {"book_id": book_id, "char_count": len(text), "text": text,
            "truncated": len(text) >= max_chars}


def tool_web_search(query: str, limit: int = 5) -> dict:
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
    results = [
        {"title": r.get("title", ""), "url": r.get("href", ""),
         "snippet": (r.get("body", "") or "")[:400]}
        for r in raw
    ]
    return {"query": query, "results": results, "count": len(results)}


TOOL_DISPATCH = {
    "library_search": tool_library_search,
    "library_read": tool_library_read,
    "web_search": tool_web_search,
}


# --------------------------------------------------------- ollama call

def ollama_chat(model: str, messages: list, tools: list | None,
                ollama_url: str, timeout: int = 180) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.7, "top_p": 0.9, "num_predict": 512},
    }
    if tools:
        payload["tools"] = tools
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ollama_url, data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------- the loop

def run_tool_loop(model: str, messages: list, ollama_url: str,
                  max_rounds: int, system_prompt_addon: str | None) -> dict:
    """Run the chat through the tool loop. Returns an Ollama-shaped response."""
    # Inject Rung 1 system prompt if no system message present
    has_system = any(m.get("role") == "system" for m in messages)
    if not has_system and system_prompt_addon:
        messages = [{"role": "system", "content": system_prompt_addon}] + messages

    rounds = 0
    last_resp = None
    while rounds < max_rounds:
        try:
            resp = ollama_chat(model, messages, TOOLS_SCHEMA, ollama_url)
        except Exception as e:
            return {"error": f"ollama call failed: {e}"}

        last_resp = resp
        msg = resp.get("message", {}) or {}
        tool_calls = msg.get("tool_calls", []) or []
        content = msg.get("content", "") or ""

        if not tool_calls:
            # Final answer
            return resp

        LOG.info("round %d: %d tool_call(s)", rounds, len(tool_calls))
        # Append assistant message + tool results
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = tc.get("function", {}) or {}
            name = fn.get("name")
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try: args = json.loads(args)
                except Exception: args = {}
            dispatch = TOOL_DISPATCH.get(name)
            if dispatch is None:
                result = {"error": f"unknown tool: {name}"}
            else:
                try:
                    result = dispatch(**args)
                except TypeError as e:
                    result = {"error": f"bad args for {name}: {e}"}
            LOG.info("  -> %s(%s) = %s", name, json.dumps(args)[:80],
                     json.dumps(result)[:120])
            messages.append({"role": "tool",
                             "content": json.dumps(result, ensure_ascii=False)})
        rounds += 1

    # Hit max_rounds — force a final no-tools call
    messages.append({"role": "user", "content":
                     "Tool budget used. Produce the final grounded answer "
                     "from what the tools returned, or refuse honestly if "
                     "they came up empty. Brief. Cite sources from results."})
    try:
        final = ollama_chat(model, messages, None, ollama_url)
    except Exception as e:
        return {"error": f"final ollama call failed: {e}",
                "last_resp": last_resp}
    return final


# --------------------------------------------------------- HTTP server

class Rung1Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Route through our logger instead of stderr.
        LOG.info("%s - - %s", self.address_string(), fmt % args)

    def _send_json(self, status: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"ok": True, "tools": list(TOOL_DISPATCH.keys())})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        # Only handle /api/chat — bot is using the Ollama interface
        if self.path != "/api/chat":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            req = json.loads(body)
        except Exception as e:
            self._send_json(400, {"error": f"bad request: {e}"})
            return

        model = req.get("model", self.server.default_model)
        messages = req.get("messages", []) or []
        if not messages:
            self._send_json(400, {"error": "no messages provided"})
            return

        LOG.info("incoming chat: model=%s msgs=%d last_user=%r",
                 model, len(messages),
                 (messages[-1].get("content", "") if messages else "")[:80])

        try:
            resp = run_tool_loop(
                model, list(messages),
                self.server.ollama_url,
                self.server.max_rounds,
                self.server.system_prompt_addon,
            )
        except Exception as e:
            LOG.exception("tool loop crashed")
            self._send_json(500, {"error": f"tool loop crashed: {e}"})
            return

        if "error" in resp:
            self._send_json(502, resp)
            return
        self._send_json(200, resp)


RUNG1_SYSTEM_PROMPT = """You are hammerstein-7b, the homelab model. You \
have access to three tools (described in the tools schema): library_search \
(local book library — Crimean / Franco-Prussian / ancient Greek / military \
history), library_read (specific book by book_id), web_search (DuckDuckGo, \
fallback only). For any factual or historical question, call library_search \
FIRST with simple 1-3 keyword queries. If the library has nothing useful, \
fall back to web_search. Cite the book + author for library hits. Never \
fabricate dates, figures, names, or citations — if tools come up empty, \
say so honestly. Voice: brief, period-coded, no closing follow-up questions \
unless genuinely needed."""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--model", default="hammerstein-7b-v022",
                   help="Default Ollama model (overridable per-request).")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434/api/chat")
    p.add_argument("--max-rounds", type=int, default=3)
    p.add_argument("--no-system-prompt-injection", action="store_true",
                   help="Don't inject the Rung 1 system prompt when one isn't present.")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    server = ThreadingHTTPServer((args.host, args.port), Rung1Handler)
    server.default_model = args.model
    server.ollama_url = args.ollama_url
    server.max_rounds = args.max_rounds
    server.system_prompt_addon = None if args.no_system_prompt_injection else RUNG1_SYSTEM_PROMPT

    LOG.info("rung1 server listening on http://%s:%d", args.host, args.port)
    LOG.info("default model: %s | ollama: %s | max rounds: %d",
             args.model, args.ollama_url, args.max_rounds)
    LOG.info("system prompt injection: %s", "off" if args.no_system_prompt_injection else "on")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
