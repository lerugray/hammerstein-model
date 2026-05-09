# Wargamer-facing Web UI — design brief

A self-contained brief for designing the Phase 6.1 wargamer surface
on top of the existing FastAPI + React dashboard. Hand this to a
designer (Claude in canvas mode, a human, another tool) and they
should be able to produce mockups without needing more context.

---

## 1. Audience

**Primary user — solo wargamer at a tabletop.** Owns physical hex
maps, counters, rulebooks. Probably already plays grognard-tier
games (CSL, GMT, Compass Games, Battles). Spends their evenings
pushing cardboard around a kitchen table.

What they do NOT want:
- A new game engine (they own the rulebook + counters)
- Computer-mediated play (they want the AI as opponent / advisor,
  not as a board)
- Account creation, cloud sync, social features

What they DO want:
- Take a phone photo of the board → get back kriegspiel-style
  mission orders for the AI's side
- Turn-by-turn continuity (the AI remembers turn 1's posture by
  turn 3)
- The voice of a 1930s German general staff officer
  (Auftragstaktik), not "as an AI assistant…"

## 2. Job to be done

Replace the awkward CLI-flag invocation:

```
hp_vision.py --state-dir my-game/ \
  --image game/photos/turn3-board.jpg \
  --image game/photos/oob-detail.jpg \
  --xlsx game/data/oob.xlsx \
  "Just played turn 3. Russians took the bridge but lost a
   regiment to my artillery. I'm thinking of withdrawing my
   left flank to consolidate."
```

…with a single web page where the wargamer:

1. Picks (or creates) the campaign
2. Drags in the photos + optional spreadsheet
3. Types the verbal status report
4. Clicks "Issue orders"
5. Reads the kriegspiel orders inline + gets them appended to
   `turn-log.md` automatically

## 3. Existing substrate (don't redesign these)

The Phase 6.0 dashboard already exists at `127.0.0.1:8765`:
- FastAPI backend, React + Tailwind + shadcn-style components
- Dark/light theme toggle in header
- Verdict card + sortable calls table on the home route
- Side-drawer pattern for per-call detail
- Dense + rigorous visual style (data-dense > marketing-glossy)

The wargamer UI should feel like a sibling page in the same app,
not a separate product. Same color tokens (HSL CSS variables in
`web/frontend/src/index.css`), same typography, same component
primitives (`Card`, `Badge`, `Button`, `Switch`).

The backend already accepts multimodal inputs via `hp_vision.py`
which writes to the same `~/.hammerstein/logs/hp-calls.jsonl` the
dashboard already reads. The wargamer UI is a thin form over the
existing pipeline + a turn-log viewer.

## 4. Page layout — structural

Two-column responsive layout. On a 13" laptop:

```
┌───────────────────────────────────────────────────────────────┐
│ [hp]  Hammerstein Persistent — wargame                  ☾  ↻ │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────── Campaign picker ───────────────────────┐    │
│  │ [▼ Bridge Crossing — Steinbach (turn 3)         ]      │    │
│  │ + new campaign                                          │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌─────────── Turn input (left col) ──────────┐  ┌──────────┐ │
│  │                                              │  │ Turn-log │ │
│  │  ⬚ Drop board photos here                    │  │ history  │ │
│  │     or click to browse                       │  │          │ │
│  │  [thumb] [thumb]  + add another              │  │ ── T3 ── │ │
│  │                                              │  │ Russians │ │
│  │  ⬚ Optional: drop OOB spreadsheet            │  │ took the │ │
│  │     (.xlsx)                                  │  │ bridge…  │ │
│  │                                              │  │          │ │
│  │  ┌────────────────────────────────────────┐  │  │ ── T2 ── │ │
│  │  │ Status report (verbal):                │  │  │ Engineers│ │
│  │  │                                        │  │  │ lost on  │ │
│  │  │ Just played turn 3. Russians took the  │  │  │ bridge…  │ │
│  │  │ bridge but lost a regiment to my       │  │  │          │ │
│  │  │ artillery…                             │  │  │ ── T1 ── │ │
│  │  │                                        │  │  │  …       │ │
│  │  └────────────────────────────────────────┘  │  │          │ │
│  │                                              │  └──────────┘ │
│  │  [Issue orders] (cost preview: ~$0.03)       │               │
│  │                                              │               │
│  └──────────────────────────────────────────────┘               │
│                                                               │
│  ┌─── Latest orders (turn 3) ────────────────────────────┐    │
│  │ ## Situation                                          │    │
│  │ Both Red battalions are at strength 2, bloodied…      │    │
│  │ ## Intent                                             │    │
│  │ Break through the bridge in turn 4 …                  │    │
│  │ ## Main Effort                                        │    │
│  │ 2nd Bn. Force the bridge crossing immediately…        │    │
│  │ … etc                                                 │    │
│  │                                                       │    │
│  │ [📋 copy as markdown]   [🐦 share turn]   [💾 save]    │    │
│  └───────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────┘
```

Mobile (single column): turn input on top, turn-log collapsed
below, latest orders inline at the bottom.

## 5. Component-level details

### Campaign picker
- Dropdown over `~/.hammerstein/wargames/*/MISSION.md` directories
  (or the `--state-dir` paths the user has invoked before — pull
  from log history)
- "+ new campaign" opens a small form: name, paste-in MISSION.md
  body, optional `tasks.json` upload. Creates the directory.

### Image dropzone
- Multi-file drag-drop. Accepts `image/*`. Shows thumbnails with
  a remove (×) button.
- Phone-friendly: tapping the dropzone on mobile opens the camera
  directly (HTML `<input accept="image/*" capture>`).
- Visual cue if image is large enough to need server-side
  downscale (>2 MB).

### Spreadsheet dropzone
- Smaller, secondary. Single `.xlsx` file. Optional.
- Shows the sheet name + first 5 row headers as confirmation it
  parsed.

### Status report textarea
- Auto-grows. Placeholder text shows the kriegspiel-style "I'm
  thinking…" voice the user should write in.
- Word counter (soft target: 50–300 words).

### Issue Orders button
- Disabled until at least one of {photo, spreadsheet, status text}
  is provided.
- Shows live cost preview: counts tokens in the assembled prompt
  + uses the per-1k-token rate of the chosen model.
- Loading state with a streaming token counter (Sonnet 4.6 takes
  ~10–15 s for a typical kriegspiel response).

### Turn-log sidebar
- Newest-on-top, collapsible cards per turn.
- Each card shows: turn number, timestamp, the operator's status
  report (excerpt), the AI's "Intent" line (excerpt), expand button.
- Expanding shows the full 5-section kriegspiel response inline.

### Latest orders panel
- Renders the kriegspiel-formatted markdown (Situation / Intent
  / Main Effort / Supporting Effort / Reserves & Fallback) as
  styled sections with section headers.
- Three actions: copy-as-markdown to clipboard; "share turn" opens
  a modal with a pre-formatted, image-card-shaped social post; save
  permanently appends to `turn-log.md`.

## 6. Visual identity

Reuse the existing HSL token system. Specifically:

- **Palette:** same navy / cream / rust / gold the project banner
  uses (see `docs/images/banner.png`). The kriegspiel wargame
  surface skews more "general staff war room" than "data
  dashboard," so the Phase 6.0 verdict card's clean blue is not
  the right anchor here. Lean into the rust + gold accents from
  the banner.
- **Typography:** body in the same `ui-sans-serif` stack as the
  rest of the app. The kriegspiel orders panel itself can use a
  slightly more serif-flavored stack (Hoefler Text or Iowan Old
  Style fallback chain) to evoke the period feel. No italic
  decorative type; this is operational, not romantic.
- **Density:** match the existing dashboard's density. No marketing
  whitespace. A wargamer looking at this for the 50th turn wants
  fast scanning, not breathing room.
- **Iconography:** lucide icons (the dashboard already uses them).
  Image / Sheet / Swords are already imported.

## 7. Interactions to avoid

- **No animations on page load.** Bare dashboard. Wargamers will
  hate fade-ins after 3 turns.
- **No "thinking…" friendly mascots.** The model is a general
  staff officer, not a chatbot.
- **No suggested follow-up prompts.** The operator drives.
- **No "share to X" preview without a 'just copy' fallback.**
  Some wargamers will tweet their best turns; many won't, and
  forcing them through a preview wastes a click.

## 8. Risks the design should make visible

- **Cost runaway.** Each turn costs ~$0.03 with Sonnet 4.6
  multimodal. A 30-turn campaign is ~$1. Show running total per
  campaign in the header.
- **Image quality.** A grainy phone photo of a hex map can
  produce hallucinated unit positions. The orders panel should
  always include a "what I see on the board" line that the
  operator can sanity-check before acting on the orders. If the
  AI's read of the board is wrong, the orders are noise.
- **Model drift.** OpenRouter model IDs change. Show the model
  string used for each turn in the turn-log card.

## 9. Out of scope for this brief

- A board-renderer that draws hexes on a canvas (the user owns
  the physical board)
- Rules-engine validation ("can a battalion move 3 hexes through
  forest?" — the user owns the rulebook)
- Multi-player / asynchronous campaigns
- Mobile-native app (the responsive web page is enough)
- VASSAL plugin integration (see `VASSAL-EXTENSION.md`; design
  doc only, deferred until empirical validation)
- Authentication, cloud sync, hosted multi-tenant

## 10. The deliverable

**Two screens.** That's all. A designer hands back:
1. The main wargame page at `1280×900` showing the layout above
   with realistic placeholder content (a real Bridge Crossing
   turn from the existing `wargame-example/turn-log.md`)
2. The mobile breakpoint (`414×900`) showing how the columns
   stack

Bonus if there's headroom:
3. The "share turn" social-card modal
4. The new-campaign form

If a designer can't ship the two screens in one session, the brief
is too ambitious. Cut 8 (Risks) and 5 (Component-level details)
first; keep 4 (Page layout) and 6 (Visual identity).

---

## Source state for the designer

- Existing app source: [`web/`](../web/) — React + TypeScript +
  Tailwind, shadcn-style components in `src/components/ui/`
- Current dashboard route layout: [`src/App.tsx`](../web/frontend/src/App.tsx)
- Color tokens: [`src/index.css`](../web/frontend/src/index.css)
- Banner for visual identity: [`docs/images/banner.png`](images/banner.png)
- Realistic content for placeholders: [`wargame-example/turn-log.md`](../wargame-example/turn-log.md)
  and [`wargame-example/MISSION.md`](../wargame-example/MISSION.md)
- The kriegspiel response structure the panel renders:
  [`tools/distill/data/hammerstein-system-prompt.txt`](../tools/distill/data/hammerstein-system-prompt.txt)
  (Auftragstaktik 5-section format: Situation / Intent / Main
  Effort / Supporting Effort / Reserves & Fallback)
