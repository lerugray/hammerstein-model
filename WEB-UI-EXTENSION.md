# Web/UI Extension — Stretch Design

**Status:** Phase 6 stretch. Gated on Phase 3 dogfood passing. The
CLI is the source of truth; the UI is a convenience layer on top.

**Audience for this doc:** Ray. You flagged UI/UX as the area where
your input matters most, so this is options-oriented — pick a
direction and the implementation follows.

## Why this matters now

Phase 1 shipped a CLI that works. Phase 1.5 found the relevance
filter is at 53% precision (close to the 60% gate; not categorical).
Phase 3 dogfood will measure whether memory injection is earning its
weight in real use. **None of that requires a UI** — `hp.py` is a
drop-in replacement for `hammerstein`, and the metrics already track
on disk.

A UI matters if the daily-use friction is *visual scanning + marking
conclusion_changed*, not *querying*. Hammerstein's scoping audit
named the kill signal: if you build a UI but find yourself wishing
for regex filters, cost aggregation, or cross-project correlation,
the right move was a CLI query upgrade, not a UI.

## Hammerstein's scoping verdict (2026-05-08)

> "Build a single-file local web server that reads your existing log
> files and displays a clean table of recent calls, their gate
> verdicts, and a one-click toggle to mark conclusions as changed.
> Skip packaging, authentication, hosting, and wargame features. If
> it takes more than a weekend to ship, you've already overbuilt it."

Specifically refused: packaging (Electron/Tauri), auth, multi-tenant,
hosted infra, wargame play surface, external-operator onboarding.

Specifically absorbed: JSONL parsing, sortable table render,
gate-status polling, local HTTP serving on `127.0.0.1`, one write
action (the conclusion_changed toggle).

## Minimum viable shape

```
hammerstein-model/
├── hp_web.py        # FastAPI or Flask server, ~150 LOC
└── static/
    └── index.html   # one page, vanilla JS or htmx, ~100 LOC
```

What it does:
1. Binds to `127.0.0.1:8765` (or whatever).
2. On page load, reads `~/.hammerstein/logs/hp-calls.jsonl` +
   `hp-metrics.jsonl`.
3. Renders a table: timestamp, project (auto-detected from cwd at
   call time), template, query excerpt, response excerpt, latency,
   cost, conclusion_changed (toggle), preamble token count.
4. One button per row: "this changed my conclusion." Flips
   `conclusion_changed` in `hp-metrics.jsonl` (atomic rewrite — read,
   modify, write).
5. Top of page: current `hp_status.py` verdict (CONTINUE / EXTEND /
   ABORT) with the failing gate cited if any.
6. No write actions beyond the toggle. No query submission. The CLI
   stays the input surface.

What it doesn't do:
- Submit new queries (use `hp.py` from the terminal).
- Edit responses.
- Cross-project aggregation.
- Search beyond a simple text-filter input.
- Multi-user / auth.
- Anything that requires a database.

## Surface options (your decision)

These are real tradeoffs, not all equivalent.

### Option 1: Local web app (Flask / FastAPI on `127.0.0.1`)

Ships as one Python file + one HTML file. Browser is the UI. No auth
needed because it binds to localhost only.

**Pros:** Ships in a weekend. Browser handles tabular data well.
Vanilla JS or htmx keeps it simple. Familiar tech.
**Cons:** Browser context-switch from terminal. Not portable to
other operators without setup steps.

### Option 2: TUI (Textual or Rich-based terminal app)

Lives next to your existing `hsh` shell. Keyboard-driven. No
browser.

**Pros:** Stays in the terminal where `hp.py` and `hsh` already
live. Single-process daemon already runs in your dev workflow.
**Cons:** Terminal rendering limits dense tabular data. Sorting +
filtering a 200-row log is awkward in TUI. Marking conclusion_changed
across many rows is keyboard-heavy.

### Option 3: VS Code / Cursor extension

Embeds the panel in your IDE. Lives where you're already working.

**Pros:** Zero context-switch when you're coding.
**Cons:** Significant scope (VSIX packaging, extension manifest,
JSON-RPC). Locks in to one IDE. Doesn't help when you're in a
different project not loaded in the IDE.

### Option 4: Hosted SaaS

Skip. Hammerstein's audit explicitly refused this for v1, and the
privacy boundary (your GS state references private project work) is
a real concern.

### Option 5: Electron / Tauri desktop app

Skip. Same as Option 1 but with packaging overhead. The packaging
is the cost; the value is identical.

### My pick (you can override)

**Option 1** — local Flask/FastAPI on 127.0.0.1, one file, ships in
a weekend. It maps directly to hammerstein's scoping verdict and
matches the "if it takes more than a weekend you've overbuilt"
framing.

If you say "I'll never open a browser when I'm working in the
terminal," then Option 2 (TUI) is the right pivot.

## Open questions for you

These need your input before I'd build anything:

1. **Single-user or eventual multi-tenant?** If you ever want to
   sell/give this to wargamers (Phase 5) or external operators, the
   UI shape changes a lot. v1 should be single-user. Confirm?

2. **Browser vs. terminal as primary surface?** Option 1 vs. Option
   2. What's your gut? Do you bounce between Cursor and a browser
   regularly, or do you live mostly in the terminal?

3. **What's the load-bearing UI capability that the CLI can't do
   today?** Hammerstein guessed: marking conclusion_changed
   efficiently + at-a-glance audit history. If your real bottleneck
   is something else (e.g., "I want to search the log by project
   name across the last month"), the right cut is a CLI query
   upgrade first, not a UI. Be honest about your daily friction.

4. **Color / theme / visual polish bar?** Plain HTML table with no
   styling vs. a designed UI. The first is hours; the second is days
   or weeks. For dogfood-only, plain HTML is enough — the question
   is whether you'd lose interest if it looks cheap.

5. **Mobile?** If you'd want to glance at hp-status from your phone,
   the local-only surface doesn't reach you. Could add a tunnel
   (ngrok, cloudflared) but that breaks the privacy boundary. If
   mobile matters, it's a separate decision.

## Phase 5 (wargame) interaction

If Phase 5 ships first, the wargame play surface is its own UI shape
(turn input + structured orders output). The dogfood UI from Phase 6
doesn't naturally cover that. Two options when both are in scope:

- Build them as separate pages in the same FastAPI app
- Build the wargame UI as a separate tool that just reuses
  `hp_filter.py` + `hp_lib.py`

Defer this decision until Phase 5 actually starts.

## Tech stack options (if Option 1 is chosen)

- **FastAPI + vanilla JS**: my default. FastAPI is dead-simple for
  read-only JSON endpoints; vanilla JS handles a sortable table
  fine. ~150 LOC.
- **Flask + htmx**: htmx removes most JS. Tables become
  server-rendered HTML fragments. Simpler if you dislike JS;
  slightly more dependencies.
- **Streamlit**: prototyped in 50 LOC but the styling is opinionated
  and looks like every other Streamlit app. Fine for a 1-day MVP;
  not great as a long-term surface.
- **NiceGUI / Reflex / similar**: heavier; defer.

If you don't have a strong preference, I'd go FastAPI + vanilla JS.

## Ship gate (for Phase 6)

This ships when:
- Phase 3 returned CONTINUE from `hp_status.py` (the wrapper itself
  earned its weight)
- You answered the open questions above
- A weekend's work passes daily-use validation: you actually open it
  daily and use it for `conclusion_changed` toggling at minimum

Kill signal (per hammerstein): if you don't open it daily within the
first 14 days, drop the UI and upgrade the CLI's filter/search
instead. The UI is a convenience, not the architecture.
