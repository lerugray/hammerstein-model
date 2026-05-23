# Rung 1 v0 — notes + limits

`scripts/rung1_chat.py` is the standalone CLI that gives hammerstein
(or any Ollama-served model) access to three tools:

- **`library_search`** — full-text search of Ray's local BookFinder
  library at `C:\Users\rweis\Research\BookFinder\`. Primary tool for
  historical / factual questions.
- **`library_read`** — pull a specific book's text (up to 20000 chars)
  by `book_id`. Use after a library_search hit.
- **`web_search`** — DuckDuckGo via ddgs. Fallback for topics the
  library doesn't cover.

## What works

- Tool loop end-to-end. Model emits `<tool_call>{...}</tool_call>`,
  harness intercepts, dispatches to Python, feeds result back, loops
  until model returns a text-only response (or hits max_rounds).
- Smoke-tested with **qwen3:8b base**: clean Britannica-grounded
  answers on Napoleon III, Sevastopol, etc. Real dates, real cited
  sources, no fabrication.
- `library_search` returns `excerpts` (list of text snippets) plus
  `book_id` / `title` / `author`. Verified against the local library
  (80 books indexed, including Figes/Royle on Crimea, Howard on
  Franco-Prussian, Worthington on ancient Greek, etc).
- Per-pod SSH pattern for fresh RunPod jobs works without account
  credential changes (see `reference_runpod_per_pod_ssh.md` memory).

## What doesn't work (yet)

### hammerstein-7b-tools as the research model

The v3a LoRA fine-tuning weakened the base model's tool-call format
discipline. Symptoms on open-ended factual prompts:

- Emits `library_search {...}` as plain text instead of the
  `<tool_call>...</tool_call>` XML wrapper that Ollama intercepts.
- Ignores the MANDATORY-tool-use system prompt and defaults to
  confident answer-from-training (the v3a default disposition).
- Fabricates citations to push back ("Richard Bonney 2016",
  "Lissagaray" — both invented).

Diagnostic: v3a was trained with NO system prompt as deliberate
design. That training erodes responsiveness to ALL system prompts,
including the tool-use mandate.

### Two-stage voice restyle (qwen3:8b research → hammerstein voice)

Tried this; doesn't reliably restyle:

- hammerstein-7b adds new facts not in the research output (more
  fabrication on top of grounded source material).
- Sometimes echoes a fake user-instruction wrapper ("I will paste the
  full output below. Your job is to make this read like...") then
  responds to ITSELF rather than the actual instruction.
- Voice-restyle output is often longer than the research input, with
  the `**Plain English summary:**` preamble v0.2 was supposed to drop.

Diagnostic: same root cause as the tool-discipline issue — the LoRA
shifted the model away from following system prompts. Restyling
requires "do exactly this transformation, don't add anything" which
is precisely the kind of constrained instruction-following the v3a
training degraded.

## What ships in v0

CLI runs research-only by default:

```bash
python scripts/rung1_chat.py "What did Napoleon III actually accomplish?"
# → uses qwen3:8b + tools; returns grounded answer with citations
```

Voice restyle is opt-in:

```bash
python scripts/rung1_chat.py --voice-model hammerstein-7b "..."
# → research stage + restyle attempt; surface artifacts may leak
```

## Path forward to v0.1+

Two non-mutually-exclusive fixes:

1. **Train v0.2.2 with tool-call + system-prompt-following pairs.**
   Add ~50 explicit tool-call exemplars + ~30 system-prompt-following
   pairs to the v0.2.2 training mix. This re-installs the format
   discipline + system-prompt responsiveness that v3a's no-system-prompt
   design degraded. Aligns with Ray's "focused, tested-mid-stream"
   v0.2.2 plan.

2. **Use qwen3:8b end-to-end + accept its voice.** Ships immediately,
   loses the hammerstein voice flavor but gets grounded answers. Could
   be the production path for Rung 1 if voice isn't load-bearing for
   the use cases that need tools (mostly factual queries).

## Integration with the Telegram bot

Not done yet. The current bot at `homelab/bot/server.mjs` is direct
Ollama-chat with no tool plumbing. To wire Rung 1 in:

1. Port the tool loop logic from `rung1_chat.py` into JS, OR
2. Have the bot shell out to `python scripts/rung1_chat.py` per
   user message (simpler but ~500ms startup per call), OR
3. Run `rung1_chat.py` as a tiny HTTP server, bot fetches from it.

Option 2 is the fastest path to a working integration; option 1 or 3
is the right long-term shape. Defer until v0.2.2 ships and we know
which model the bot should route to.

## Files

- `scripts/rung1_chat.py` — the CLI + tool loop
- `D:\hammerstein-store\models\hammerstein-7b-tools.Modelfile` — the
  hammerstein-7b variant with the Qwen2.5 tool-aware chat template
  (loaded into Ollama as `hammerstein-7b-tools`)
- `data/rung1-smoke-*.json` — smoke-test transcripts for debugging
