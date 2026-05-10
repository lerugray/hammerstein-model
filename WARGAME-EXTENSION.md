# Wargame Solitaire Opponent — Stretch Extension

**Status:** ✅ v0 shipped 2026-05-08, with a v1 design pivot the same
day. `--state-dir` flag wired into `hp.py`; self-authored example at
[`wargame-example/`](wargame-example/) (Bridge Crossing — Steinbach).

**v1 design (Auftragstaktik / kriegspiel-style):** Per Ray's
direction 2026-05-08, the AI issues **mission-type orders** to
formations ("2nd Bn forces the bridge crossing"), not
coordinate-level moves ("2nd Bn moves D5 → D4"). This matches the
1930s German command tradition the framework's namesake actually
practiced (Reichswehr Chef Hammerstein-Equord, 1930-1934), is more
natural for the model (no hex hallucinations), and is closer to
how solo wargamers actually operate (verbal status reports +
mission orders, not structured-data state-tracking).

**v2 (multimodal, shipped 2026-05-08):** [`hp_vision.py`](hp_vision.py),
sibling to `hp.py`, takes board photos + Excel OOB sheets +
conversational status reports and produces kriegspiel orders.
Default backend: `anthropic/claude-sonnet-4.6` via OpenRouter.
Reuses the same MISSION.md / tasks.json / turn-log.md state
convention. Validated on the Bridge Crossing example 2026-05-08
(text + Excel; image wiring proven via the API schema). See
[`wargame-example/MISSION.md`](wargame-example/MISSION.md)
"Multimodal" section for the working recipe + workflow.

**v3 (web UI, shipped 2026-05-09):** [`web/frontend/src/wargame/`](web/frontend/src/wargame/)
+ [`web/backend/wargame_api.py`](web/backend/wargame_api.py).
The Wargame tab in the local dashboard at
`http://127.0.0.1:8765/?tab=wargame` (launched by `./hp_web.sh`)
wraps `hp_vision.py` end-to-end:

- Discovers campaigns from `wargame-example/` (shipped) and
  `wargames/<slug>/` (user-private, gitignored).
- "Issue orders" form takes board-photo uploads + xlsx upload +
  status report → subprocesses `hp_vision.py` with the campaign's
  state-dir → parses the 8-section markdown response into the
  `OrdersData` shape the React panel renders.
- Persists per-turn structured entries to `turn-log.json`,
  human-readable narrative to `turn-log.md`, and the most recent
  parsed orders to `orders-latest.json` (for first-load hydration).
- New campaigns are created from the UI with a name + MISSION.md
  paste; scaffolds an empty `tasks.json` + `turn-log.{md,json}` +
  `campaign.json`.
- Requires `OPENROUTER_API_KEY` in env. `hp_web.sh` sources
  `~/.hammerstein.env` and `./.env` if present.

The system prompt suffix in `hp_vision.py` was updated as part of
this ship to enforce three additional sections beyond the original
five — `## What I see on the board` (sanity-check belt), `## Unread`
(one-line "I cannot read X" gate), and `## Acknowledged` (closing
line) — so the orders panel can render Claude Design's load-bearing
"confirm-the-AI-parsed-the-board" UI element without a separate
post-processing step.

**v3.5 (Sources panel, shipped 2026-05-09):** NotebookLM-style
persistent context for rulebooks and reference imagery. The
"Sources" card on the wargame surface accepts:

- `.pdf` rulebooks → auto-converted to markdown via
  [`pymupdf4llm`](https://github.com/pymupdf/RAG) with the cleanup
  pipeline ported from
  [`conflict-simulations/manuals/build-docx.py`](https://github.com/lerugray/conflict-simulations/blob/main/manuals/build-docx.py)
  (strips pandoc image-placeholder noise, promotes
  picture-text-wrapped section titles to proper H2/H3/H4
  headings). Stored as `<state-dir>/rules/<book>.md`.
- `.md` / `.markdown` / `.txt` rulebooks → saved as-is to
  `<state-dir>/rules/`.
- `.jpg` / `.png` / `.webp` / `.gif` reference images
  (strategic map, counter sheet, terrain effects chart, random
  event table) → stored at `<state-dir>/reference/` and
  attached to every `hp_vision.py` issue as additional image
  blocks, **prepended** before the per-turn board photo with a
  status-text hint distinguishing them from the live board state.

Per-source kind tag (`rules` / `ref image`) and delete affordance.
Total token cost surfaced inline.

**v3.6 (digest layer, shipped 2026-05-09):** Karpathy
three-layer LLM-Wiki pattern, mini-mini version
(see [`raybrain`](https://github.com/lerugray/raybrain) for the
full-RAG cousin). At PDF/MD upload time, after the standard
conversion + cleanup pipeline, an additional one-shot OpenRouter
call ([`web/backend/wargame_digest.py`](web/backend/wargame_digest.py))
generates an "AI Commander Reference" digest:

- Structured by operational concerns (game shape, sequence of
  play, forces, combat resolution, movement & terrain, air
  missions, naval, logistics, special rules, victory).
- Cross-references back to source rulebook section IDs
  (`[see §X.Y]`) so the model's orders can cite specifically.
- Skips design notes, dedications, ethics statements, copyright
  metadata, glossary entries that aren't load-bearing for orders.
- Stored as `<state-dir>/rules/<book>.digest.md` alongside the raw
  conversion. Both files coexist; raw is the citation source.

Preamble injection
([`hp_lib.py:read_project_state`](hp_lib.py)) prefers the digest
when present:

| Layer | Tokens (Ukraine 1.12 example) | Goes into preamble |
|---|---:|---|
| raw `<book>.pdf` | n/a | no — kept on disk for citation |
| `<book>.md` (auto-converted) | ~16,000 | only if no digest |
| `<book>.digest.md` (LLM-curated) | ~3,100 | yes — preferred when present |

Empirical result on a Turn 2 reissue against the same Bridge
Crossing photo: 5x reduction in preamble tokens, comparable or
better order quality (the model used MORE specific section
references with the digest because the digest's structure makes
them more salient than they were buried in the full rulebook),
roughly the same end-to-end latency (image processing dominates).

Digest generation is non-fatal: if the OpenRouter call fails, the
upload still succeeds and the full rulebook stays in preamble
until the next attempt. UI surfaces a `digest` badge on rule
sources that have one.

**Output structure** (kriegspiel-shaped):

- `## Situation` — what the commander reads from the report
- `## Intent` — operational goal (the WHY, for adjudication
  flexibility)
- `## Main Effort` — formation + mission verb
- `## Supporting Effort` — other formations + secondary missions
- `## Reserves & Fallback` — commitment trigger + withdrawal
  trigger

The working query recipe + future multimodal direction (photo
input from the physical board, OOB from countersheets) are
documented in
[`wargame-example/MISSION.md`](wargame-example/MISSION.md).

The original spec (below) is preserved as design context. The v1
shape is closer in spirit to the spec's intent than my v0 unit-
level draft was.

**Audience:** Wargamers playing solitaire. Ray's domain; portfolio-
relevant; possibly distributable / monetizable.

## What it does

The player runs a wargame solo. They reference local files:
`rules.md`, `map` (tactical or strategic), `units` / order of battle,
and a per-turn snapshot of the current state. Hammerstein reads them
and acts as the opponent (one side or both): generates orders at the
appropriate command echelon — general intent + concrete unit-level
orders — and adapts each turn to the situation as the player
reports it.

The player remains the adjudicator (dice, fog filtering, terrain
resolution, rules edge-cases). The AI provides command intent and
unit assignments.

## Hammerstein scoping verdict (2026-05-08)

Walked the proposal through `hp.py --template scope-this-idea`
against the post-Phase-1 substrate. The verdict:

> "Don't build a new wargame engine or modify the CLI. Treat the game
> as just another project folder that your existing wrapper already
> knows how to read."

Key cuts:

- **Don't add a CLI template.** The existing `scope-this-idea` /
  `audit-this-plan` / etc. handle the reasoning shape; the role
  ("you are the opposing commander") shapes via the injected
  preamble.
- **Don't invent a state schema.** Reuse `MISSION.md` (campaign
  rules / ROE) and `tasks.json` (OOB / current orders). Add one new
  file: `turn-log.md` (append-only per-turn snapshots).
- **Player-managed fog of war.** AI receives exactly what the player
  reports. AI assumes perfect intel within that snapshot. Player
  filters what's actually visible on the board.
- **Bypass corpus-id intersection for turn continuity.** Recency
  beats structural similarity here. The injected `turn-log.md`
  carries forward; the wrapper's audit-similarity retrieval is a
  no-op for wargame play.
- **Output shape via preamble, not new pipeline.** Enforce a strict
  markdown structure (`## Intent → ## Axis → ## Unit Assignments →
  ## Reserves → ## Fallback`) by stating the contract in
  `wargame-context.md`.

**Tradeoff named:** fidelity vs. friction. If orders are too abstract,
the player spends more time translating them than thinking own moves.
If too concrete, the AI hallucinates constraints it can't see.

**Kill signal:** *"I'm spending more time cleaning up the AI's orders
than I would have spent planning my own."* If this appears, the right
move isn't a better prompt — it's dropping the feature.

## Minimum viable shape

### Required `hp.py` changes (~10-20 LOC)

1. **Extend `read_project_state` to include `turn-log.md`** when
   present. Append after the `tasks.json` block. Recency-ordered
   (newest turn at the top) so the most recent snapshot dominates
   the context window.
2. **Optional `--state-dir <path>` flag** for explicit state-dir
   override. v1 auto-detects `generalstaff-private/state/<cwd-name>`,
   which only works inside Ray's GS layout. The wargame use case
   wants a `wargame/` dir that ships alongside the rules. Either:
   (a) host wargames under GS state, (b) add the override flag.

That's it. The intersection retrieval, token budget, schema
validation, and quarantine all carry over unchanged.

### Example dir structure

```
my-wargame/
├── rules.md           # → MISSION.md role (rules/ROE/scenario brief)
├── units.json         # → tasks.json role (OOB + current orders)
├── turn-log.md        # append-only per-turn snapshots (NEW)
├── wargame-context.md # role instructions + output-shape contract
└── maps/              # referenced in rules; AI doesn't render
```

`wargame-context.md` is the shape contract the player writes once
per scenario:

```markdown
## Role
You are the commander of <SIDE>. Your task is to issue orders to
your forces given the current snapshot. The player adjudicates
all dice, fog, terrain, and rules edge-cases.

## Output structure
- ## Intent (1-2 sentences)
- ## Axis (primary effort + secondary if any)
- ## Unit Assignments (each unit → mission verb + objective)
- ## Reserves (held forces + commitment trigger)
- ## Fallback (withdrawal trigger + rally point)
```

### Per-turn workflow

```
$ cd my-wargame/
$ hp.py --template scope-this-idea \
        "Turn 14. Status: <player-reported snapshot>. Issue orders for Red."
```

The wrapper:
1. Pulls `rules.md`, `units.json`, `turn-log.md`, `wargame-context.md`
   into the preamble.
2. Subprocesses `hammerstein` with the snapshot as the query.
3. Outputs orders in the structure the context contract specified.
4. Player appends the orders + outcome to `turn-log.md` after
   adjudication.

## Open architectural questions

1. **State portability beyond Ray's GS.** Current auto-detection is
   hardcoded to `generalstaff-private/state/`. For a wargame to ship
   to other users, `hp.py` needs a `--state-dir <path>` flag or a
   `.hp-config` discovery convention. Defer until Phase 5 actually
   begins.

2. **Multi-side play.** AI plays one side; player plays the other.
   Or: AI plays both, player adjudicates and reports. v1 is "AI
   plays one side, player runs the table." Two-sided AI is a
   separate variation — needs to keep two `turn-log.md` files (one
   per side) or split state.

3. **Long-running campaign memory.** Current corpus-id retrieval is
   a no-op for turn-by-turn play (recency wins). But across
   campaigns / scenarios, the audit log MIGHT surface useful
   patterns ("last campaign Red kept losing the river crossing —
   plan around it"). Defer; observe the dogfood pattern first.

4. **Ruleset copyright.** Distributable wargame examples must be
   self-authored or public-domain. The `my-wargame/` example dir
   shipped with hp.py should use a tiny self-authored scenario
   (e.g., abstract two-division engagement) — not a commercial
   ruleset.

5. **Output discipline drift.** Hammerstein's training is on
   strategic-reasoning prose. Wargame orders need imperative voice.
   Watch for the model lapsing into analytical framing ("the
   commander would consider...") instead of orders ("II Corps
   attacks east"). The fix is in `wargame-context.md`'s shape
   contract; track if it holds across 5+ turns.

## Ship gate

Phase 5 ships when ALL hold:

- Phase 3 dogfood loop returned CONTINUE from `hp_status.py`
- Phase 4 (failure-pattern preflight) shipped or explicitly deferred
  with rationale
- A self-authored example wargame is built and runs cleanly for 3
  consecutive turns without manual prompt tweaking
- `--state-dir` override flag is in (the GS-hardcoded auto-detect
  is fine for Ray's dogfood but blocks distribution)

The 20-LOC `turn-log.md` change to `read_project_state` is trivial
and could land as a no-op enhancement before Phase 5 begins (it
costs nothing if no `turn-log.md` exists). But the shape decisions
above need Phase 3's lessons before committing.

## Why this is interesting beyond Ray's dogfood

The audit-with-deeper-recall use case is solo and personal. The
wargame opponent is the first plausible **shareable** use case:
wargamers are a specific community Ray has access to, with a
concrete pain point (no one to play against), and the deliverable
(a directory with rules + a state file + the wrapper) is small
enough to distribute as a tarball or a git repo.

If Phase 5 ships and 3-5 wargamers use it on real games, that's the
external-validation evidence the dedicated dogfood deployment was
supposed to generate. The framework gets a use case beyond Ray.
