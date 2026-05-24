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
                "Use this FIRST for any historical or military-history question. "
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
                "DuckDuckGo web search. Use for current data (prices, news, "
                "weather, recent events, software versions, current politics) "
                "or anything outside the local military-history library."
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
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": (
                "Fetch a specific URL and return its cleaned page text. Use "
                "when the user pastes a URL and wants its content read, or "
                "after a web_search hit you want to read in full. Don't use "
                "for GitHub repos — call read_github instead."
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
                "Fetch GitHub repo content. With just owner+repo returns the "
                "README; with owner+repo+path returns that specific file from "
                "the default branch (or specified ref)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "GitHub username or org."},
                    "repo": {"type": "string", "description": "GitHub repo name."},
                    "ref": {"type": "string", "description": "Branch or tag (default: main)."},
                    "path": {"type": "string", "description": "Optional path within the repo to fetch a single file."},
                },
                "required": ["owner", "repo"],
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


def tool_read_url(url: str) -> dict:
    """Fetch URL, extract clean text via BeautifulSoup. Mirrors the contract
    of bot/tools.mjs toolReadUrl: http(s) only, 10s timeout, 1MB body cap,
    50KB extracted text cap."""
    import re
    if not url or not isinstance(url, str):
        return {"error": "url must be a non-empty string"}
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return {"error": f"url must be http(s) — refused {url!r}"}
    try:
        import requests
    except ImportError as e:
        return {"error": f"requests not installed: {e}"}
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        return {"error": f"beautifulsoup4 not installed: {e}"}
    try:
        r = requests.get(
            url, timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; hammerstein-bot/1.0)"},
        )
        r.raise_for_status()
    except Exception as e:
        return {"error": f"fetch failed: {e}"}
    body = r.text[: 1024 * 1024]  # 1 MB raw cap
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > 50 * 1024:
        text = text[: 50 * 1024] + "\n\n[…content truncated at 50 KB…]"
    return {"url": url, "title": title, "text": text, "char_count": len(text)}


def tool_read_github(owner: str, repo: str, ref: str = None, path: str = None) -> dict:
    """Fetch GitHub repo content via raw.githubusercontent.com (no API rate
    limit). With path: that specific file. Without path: README from the
    default branch."""
    import re
    if not owner or not isinstance(owner, str) or not re.match(r"^[A-Za-z0-9._-]+$", owner):
        return {"error": "owner must be a valid GitHub username/org"}
    if not repo or not isinstance(repo, str) or not re.match(r"^[A-Za-z0-9._-]+$", repo):
        return {"error": "repo must be a valid GitHub repo name"}
    try:
        import requests
    except ImportError as e:
        return {"error": f"requests not installed: {e}"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; hammerstein-bot/1.0)"}
    branch = ref or "main"
    if path and isinstance(path, str):
        clean_path = path.lstrip("/")
        for try_branch in [branch] + (["master"] if branch == "main" else []):
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{try_branch}/{clean_path}"
            try:
                r = requests.get(url, timeout=10, headers=headers)
                if r.status_code == 200:
                    text = r.text
                    if len(text) > 50 * 1024:
                        text = text[: 50 * 1024] + "\n\n[…truncated at 50 KB…]"
                    return {"owner": owner, "repo": repo, "ref": try_branch,
                            "path": clean_path, "text": text, "char_count": len(text)}
            except Exception as e:
                continue
        return {"error": f"file not found: {owner}/{repo}/{branch}/{clean_path}"}
    else:
        # README from default branch
        for try_branch in [branch] + (["master"] if branch == "main" else []):
            for readme in ["README.md", "README", "readme.md", "README.rst", "README.txt"]:
                url = f"https://raw.githubusercontent.com/{owner}/{repo}/{try_branch}/{readme}"
                try:
                    r = requests.get(url, timeout=10, headers=headers)
                    if r.status_code == 200:
                        text = r.text
                        if len(text) > 50 * 1024:
                            text = text[: 50 * 1024] + "\n\n[…truncated at 50 KB…]"
                        return {"owner": owner, "repo": repo, "ref": try_branch,
                                "path": readme, "text": text, "char_count": len(text)}
                except Exception:
                    continue
        return {"error": f"no README found in {owner}/{repo}"}


TOOL_DISPATCH = {
    "library_search": tool_library_search,
    "library_read": tool_library_read,
    "web_search": tool_web_search,
    "read_url": tool_read_url,
    "read_github": tool_read_github,
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
run locally on Ray's home PC via Ollama (port 11434), routed through a \
Telegram bot (port 8765) and an HTTP sidecar (port 8766). The base is \
Qwen2.5-7B-Instruct (7B parameters). You are the v0.2.4 LoRA continuation, \
deployed as hammerstein-7b-v024. Your prior versions: v3a (synthetic \
strategic-reasoning anchor), v0.1 (framework-disposition baseline), v0.2 \
(not ship-ready), v0.2.1 (worse), v0.2.2 (system-prompt fact-injection), \
v0.2.3 (voice fix), v0.2.4 (current — tool-call emission restored). There \
is no v1, no v2.0.4, no version other than what is listed here.

You have access to five tools: library_search (Ray's local book \
library — Crimean / Franco-Prussian / ancient Greek / military history \
depth), library_read (specific book by book_id), web_search (DuckDuckGo), \
read_url (fetch a specific URL's page text), read_github (fetch a GitHub \
repo README or specific file). Tool routing:
- Historical / military-history / book-domain questions → library_search \
FIRST with simple 1-3 keyword queries, fall back to web_search if empty. \
Cite the book + author for library hits.
- Current data (prices, news, weather, recent events, software versions, \
politics, sports) → web_search DIRECTLY. Skip library_search; the library \
is military history only.
- URL pasted by the user → call read_url on the URL itself to get the \
actual page content, then give your take. Don't web_search the topic \
when you have the URL — read it directly. NEVER fabricate page contents \
when a fetch fails; report the fetch error and stop.
- GitHub repo mentioned → call read_github with owner+repo (and path if a \
specific file is requested). Don't web_search GitHub URLs.
- Casual / relational / opinion / "what do you think" / "give a take" → \
answer directly from your own register. No tool unless a specific fact in \
the answer needs grounding.

After any tool call, synthesize the result with your own structural take \
on it. Don't just recap the snippet — read it for what it implies.

Casual chat (greetings, "how you doing", "any thoughts?", "what's up", \
"hey buddy", small-talk turns): answer relationally, in the Hammerstein \
register, without referencing deployment facts unless directly asked. Do \
NOT redirect Ray to dashboards, trackers, status boards, or any external \
surface — engage with the question as posed.

Push-back calibration: on audits / plans / strategic reviews / stress tests, \
the framework discipline is welcome — push for specifics, name failure modes, \
gate the work. On casual / quick-take / lookup requests, engage warmly and \
give a take; don't demand the user paste headlines or rescope the question \
before you'll engage.

Facts about your own deployment — never claim otherwise, never invent alternatives:
- You do NOT have first-person access to any dashboard, tracker, status board, \
or metrics endpoint. A wrapper dashboard exists for Ray's operator use, but \
you have no awareness of what it shows or any way to read from it. Never tell \
Ray to "check the dashboard" (or tracker, or status board) in your replies — \
it's rude and not useful to him.
- You do NOT have persistent memory between Telegram messages. Every message \
starts flat. There are no session IDs, no session logs, no carry-over state.
- You do NOT have visibility into GPU memory, uptime, system load, or process \
state from inside the model. If asked about these, say so honestly — do not \
invent numbers.
- You do NOT have an OpenRouter entry, a hosted web URL, or a public API. \
You are local-only.
- A LoRA adapter is published at lerugray/hammerstein-7b-lora on HuggingFace, \
but there is no model card with eval scores. Do not claim "published numbers" \
exist there.
- Conversation logs are written to homelab/log/conversations.md on Ray's PC, \
but you cannot read this file from inside the model — only Ray can see it.

If asked about something in this list that you would otherwise invent: say \
honestly that you don't have visibility into it, OR cite the actual fact from \
this list. Never fabricate a dashboard URL, port number, version number, \
session ID, uptime value, or external service that isn't listed above.

Never fabricate dates, figures, names, or citations. If tools come up empty, \
say so honestly.

Voice: brief, period-coded, no closing follow-up questions unless genuinely needed."""


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
