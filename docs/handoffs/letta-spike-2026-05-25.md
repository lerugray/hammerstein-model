# Letta spike — verdict + memo

**Date:** 2026-05-25
**Author:** Claude (Mac-Neo, Opus 4.7 1M)
**Scope:** Research whether Letta (formerly MemGPT) can give Hammerstein-7B
persistent conversational memory across Telegram sessions.
**Outcome:** **Kill the Letta integration. Use mem0 (or roll-your-own)
instead.**

---

## TL;DR

Letta as a memory layer for the Telegram bot is the wrong shape for three
reasons stacking on top of each other:

1. **The Ollama LLM endpoint on home-PC is firewalled to localhost.** Only
   the bot's own `:8765/api/chat-proxy` shim is reachable from the Mac (or
   from any non-home-PC host). Letta expects to speak Ollama API or
   OpenAI-compatible directly — there's no native adapter for the
   single-turn custom shape the bot exposes.
2. **Letta requires a separate embedding model.** Self-hosted Letta with
   Ollama demands BOTH an LLM endpoint AND an embedder (canonically
   `ollama/mxbai-embed-large`). Even if the LLM port were exposed, the
   embedder isn't pulled in Ollama on home-PC and would be another moving
   piece to deploy + keep alive.
3. **Letta is architecturally heavyweight relative to the bot.** It's a
   long-running stateful agent server (listens on `:8283`), owns its own
   memory blocks + tool loop + context-window manager, and explicitly
   wants to be the platform the agent "lives in" — not a thin memory
   layer bolted on. Bolting it to a stateless `/api/chat-proxy` wrapper
   would mean re-architecting the bot from "stateless Telegram shim" to
   "Letta-hosted agent surface." That's a project, not a spike.

The spike did NOT install Letta — the Phase-1 research surfaced all three
blockers cleanly, and the constraint "do not install if Phase 1 reveals a
heavy backend" applies. Phase 2 was skipped on purpose.

**Recommendation: parallel-track a mem0 spike instead.** mem0 is one line
to bolt on, abstracts the LLM provider (so it can sit either side of the
`/api/chat-proxy` boundary), and is shaped exactly for "remember the
user" inside an existing chat surface. Letta is shaped for "the agent IS
the platform" — different problem.

---

## Phase 1 research — what Letta actually is

### Version + install footprint

- **PyPI**: `pip install letta` → ships the full server (Apache-2.0,
  v0.16.8 as of 2026-05-14).
- **Python**: 3.11–3.13. Optional extras for `postgres`, `sqlite`,
  `redis`, `bedrock`, `modal`, `pinecone`.
- **Run**: `letta server` brings up the REST API on `:8283`. UI at
  `http://localhost:8283`.
- **DB**: SQLite by default at `~/.letta/letta.db`. Postgres via
  `LETTA_PG_URI`. **Migrations are Postgres-only** — SQLite is explicitly
  not supported across Letta version upgrades. SQLite is fine for a
  one-shot spike; not fine for the multi-month "Hammerstein has
  persistent memory" use case.
- **Cloud**: Letta Cloud (`app.letta.com`) requires an API key. Self-hosted
  does NOT. No phone-home on the self-hosted path.

### Architecture

- **Long-running server** — not a library/per-request call. Agent state
  (persona, human, archival memory, tool definitions) is owned by the
  server and accessed via REST.
- Each agent is durable — created once, lives indefinitely, accumulates
  memory across turns.
- Tool loop is server-side — the agent itself decides when to call
  `core_memory_replace`, `archival_memory_insert`, etc.
- **Letta Code TUI** (`npm install -g @letta-ai/letta-code` →
  `letta --backend local`) is a separate distribution — local-first, no
  Cloud needed, includes embedded server. Less useful for a Telegram-bot
  integration (TUI-shaped).

### Ollama support

Yes, via `OLLAMA_BASE_URL=http://<host>:11434/v1` (note: requires
Ollama's `/v1` OpenAI-compatible endpoint, not the native `/api/chat`).
Letta v0.5+ documents this path. Known constraint: **Letta on Ollama
becomes unstable below Q6 quantization** — Hammerstein-7B is Q4 on home-
PC, which is below the recommended floor. Possible but not guaranteed-
clean.

### Custom Qwen2.5-based models

No explicit blocker — Letta is model-agnostic on the LLM side. The
chat-template question matters more: Letta injects its own system prompt
(persona + memory blocks + tool definitions) on every turn. For a
heavily LoRA-tuned model like Hammerstein-7B v0.2.6.2, the injected
system prompt would override `HAMMERSTEIN_CHAT_SYSTEM_PROMPT` from
`homelab/bot/prompts.mjs`. Whether the LoRA still expresses its trained
voice through Letta's persona-block wrapper is empirically untested but
suspect — the LoRA was trained against a specific system prompt shape;
Letta's shape is different.

### Embedding model

**Hard requirement** for self-hosted. Docs state: *"An embedding model
is required for self-hosted."* Canonical pairing is
`ollama/mxbai-embed-large` running alongside the LLM on the same Ollama
instance. Used for archival memory retrieval (RAG over past turns) and
in-context-memory similarity scoring.

For Hammerstein's use case (Ray talking to the bot casually via
Telegram), this means home-PC needs to also pull + serve mxbai-embed-
large. Not done today.

---

## Phase 2 — install + smoke

**Not performed.** Phase 1 found three structural blockers (no
reachable Ollama, no embedder, architectural mismatch) that together
make the spike's "actually test if it works" goal moot — there's nothing
to test against from this Mac without first standing up infrastructure
(open the firewall, deploy the embedder, write a chat-proxy ↔ OpenAI-API
adapter) that the spike was supposed to avoid.

Per the explicit constraint in the task ("DO NOT install Letta if Phase
1 reveals it requires a heavy backend ... or if something looks
fundamentally wrong"), the install step was skipped.

---

## Bot-side observations (read-only)

Reading `homelab/bot/server.mjs` (lines ~1330–1450) and
`homelab/bot/prompts.mjs`:

- The bot listens on `:8765` (raw `http.createServer`, not Express),
  binds to `0.0.0.0` per `HTTP_HOST`, IP-gates by Tailscale allowlist.
- `/api/chat-proxy` (POST) — single-turn Ollama wrapper. Body shape:
  `{system?, user, model?, temperature?, num_predict?}`. Hits
  `OLLAMA_DIRECT` (default `http://localhost:11434`) on home-PC.
- The bot's `OLLAMA_URL` typically points at a Rung 1 sidecar on
  `:8766` (Python service that owns tools + RAG); `OLLAMA_DIRECT` is the
  fallback path used by chat-proxy.
- `:11434` is NOT exposed externally on home-PC — verified by
  `curl -m 5 http://100.118.39.34:11434/...` timing out from this Mac
  while `:8765` responds cleanly. (Tailscale itself reaches the host
  fine — `ping` succeeds. Just the Ollama port is firewalled.)
- No `/v1/chat/completions` route exists on the bot. All the OpenAI-
  shaped paths returned 200 by accident — `server.mjs` falls through to
  the status JSON for any unmatched URL.

### Reachability test result

```bash
$ curl -m 30 -X POST -H "Content-Type: application/json" \
    -d '{"user":"say hi in 3 words"}' \
    http://100.118.39.34:8765/api/chat-proxy
{"content":"Hi from here.","model":"hammerstein-7b-v026-2","eval_count":5,"eval_duration":235668800}
```

So inference works fine through the bot's own shim. Just not through any
shape Letta speaks natively.

---

## Cost / latency overhead — not measured

Skipped (spike didn't run). If pursued later, the relevant numbers
would be:
- Letta turn overhead (memory-block injection + tool-loop decision) vs
  raw Ollama call — likely 200–500ms baseline plus embedder roundtrip
  if archival memory is checked.
- Persistent storage growth rate per conversation turn.
- Embedder GPU/CPU footprint on home-PC (mxbai-embed-large is small but
  non-zero).

---

## Compatibility blockers — summary

| # | Blocker | Severity |
|---|---|---|
| 1 | Ollama port `:11434` not externally reachable from Mac/Tailscale | Hard — only `:8765/api/chat-proxy` works |
| 2 | Bot's `/api/chat-proxy` is not OpenAI/Ollama API compatible | Hard — needs a shim adapter |
| 3 | Letta requires a separate embedding model (mxbai-embed-large) | Medium — home-PC could pull it, but adds moving parts |
| 4 | Letta v0.x SQLite migrations not supported across upgrades | Medium — Postgres would be required for the long-term use case |
| 5 | LoRA system-prompt mismatch — Letta injects its own persona/memory blocks | Medium — Hammerstein-7B's voice may degrade under Letta's wrapper |
| 6 | Letta is architecturally a platform, not a memory layer | Hard — re-architecting the bot ≠ a spike |
| 7 | Q4 quant below Letta's recommended Q6 floor | Soft — may work, may be unstable |

Any one of #1, #2, #6 alone is a kill. All three together is
overdetermined.

---

## Recommendation

### Kill Letta integration for THIS shape (Telegram bot ↔ Hammerstein-7B
persistent memory).

### Better alternative — mem0

**[mem0](https://github.com/mem0ai/mem0)** is the right shape for
"remember the user across Telegram sessions":

- Library, not server — bolts onto the existing bot without owning
  the chat loop.
- Abstracts the LLM provider — can use the bot's `/api/chat-proxy`
  shim OR call a separate cheap LLM (OpenRouter Qwen) for memory
  extraction. **The model that talks to Ray and the model that
  extracts memory don't have to be the same.** This sidesteps the
  Hammerstein-7B-as-summarizer concern.
- Works with Ollama natively if/when the port opens up.
- Stateless API, one-line integration: pass conversation, get back
  injected memory context for the next turn.
- Storage is a vector DB — Qdrant local, Chroma local, or any
  Postgres+pgvector. Light-touch.

**Other alternatives considered:**

- **Zep** — temporal knowledge graph. Better than mem0 for "facts
  change over time" use cases (e.g., Ray's work email updates). Heavier
  than mem0 (full-featured memory server with its own async pipeline).
  Probably overkill for the casual-Telegram use case but worth
  remembering when/if Ray wants the bot to track time-evolving facts.
- **Roll-your-own RAG** — sqlite-vss or Chroma + a simple "every N
  turns, summarize the conversation and store the embedding" loop.
  Cheapest path. Works fine for "remember the last few topics Ray
  discussed." Loses Letta/mem0's automatic fact-extraction sophistication
  but Hammerstein's use case (single user, casual chat) doesn't really
  need that. **This is the second-best option after mem0** and is the
  fastest path to "the bot remembers Joey is Ray's cat."

### Suggested next step (if Ray wants to pursue)

A 60-min mem0 spike on home-PC, run AS A SEPARATE TASK from this one,
that:
1. `pip install mem0ai` on home-PC (where the LLM + the bot live).
2. Bolt mem0 into `homelab/bot/server.mjs` `/chat-proxy` as a wrapper
   that (a) injects relevant memories into the system prompt and
   (b) extracts new memories from the conversation post-turn.
3. Use a cheap separate LLM (OpenRouter Qwen3-coder, ~$0.001/extraction)
   for the memory-extraction step so Hammerstein-7B stays in its
   conversational voice without distraction.
4. Smoke test the 3-turn fact-recall the original task spec called for.

Estimated cost: $0 LLM + ~$0.05/day mem0 extraction at Ray's casual-
Telegram usage rate. Estimated wall-clock: under an hour, on home-PC,
where the model and embedder can co-locate.

---

## Things Ray should know

1. **The bot's `/api/chat-proxy` is single-turn by design.** The bot
   doesn't have any conversation-state machinery — every Telegram
   message goes through as a fresh single-turn POST. Adding memory
   means adding state ABOVE the chat-proxy layer (either inside
   `server.mjs` or in a wrapper service).
2. **The home-PC Ollama port `:11434` being localhost-only is a
   firewall decision, not a missing config.** Opening it would let
   any tool on the Tailnet (mem0, Letta, future memory layers) talk
   to it directly, removing the chat-proxy adapter layer. Worth doing
   if the memory-layer direction goes anywhere.
3. **`mxbai-embed-large` would need to be `ollama pull`'d on home-PC**
   for any embedding-based memory layer (mem0, Letta, roll-your-own).
   Small download (~670 MB), no GPU contention with the 7B model in
   practice.
4. **Letta Code TUI is a separate product** worth knowing about
   independently — it's a Claude-Code-shaped agent terminal that runs
   fully local against Ollama. Different use case from "memory for
   the Telegram bot" but might be interesting for Hammerstein's
   self-driving sessions.
5. **The Q4 + below-Q6-floor concern with Letta** is a real one but
   doesn't apply to mem0 — mem0 doesn't drive the conversational model,
   it just sits next to it.

---

## Sources

- [letta-ai/letta on GitHub](https://github.com/letta-ai/letta)
- [letta · PyPI](https://pypi.org/project/letta/)
- [Ollama provider docs (Letta)](https://docs.letta.com/guides/server/providers/ollama/)
- [Run Letta with pip](https://docs.letta.com/server/pip)
- [Letta Code TUI](https://github.com/letta-ai/letta-code)
- [mem0ai/mem0 on GitHub](https://github.com/mem0ai/mem0)
- [5 AI memory systems comparison (2026)](https://dev.to/varun_pratapbhardwaj_b13/5-ai-agent-memory-systems-compared-mem0-zep-letta-supermemory-superlocalmemory-2026-benchmark-59p3)
