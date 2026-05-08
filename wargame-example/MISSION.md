# Bridge Crossing — Steinbach

A self-authored micro-wargame, public domain, designed as the
example scenario for the
[hammerstein-model wargame extension](../WARGAME-EXTENSION.md).

This file does double duty in the
[`hp.py`](../hp.py) wrapper convention:

- It plays the role of `MISSION.md` (campaign rules, ROE, scenario
  brief) — so it gets injected into the AI's context preamble
  automatically when you run `hp.py --state-dir wargame-example/`.
- It also defines the **AI's role and output contract** (the
  "wargame-context" portion). One file, fewer moving parts.

The companion files are `tasks.json` (current OOB / orders),
`turn-log.md` (per-turn snapshots, append-only), and `maps/`
(referenced terrain).

---

## Scenario brief

**Date:** Mid-twentieth-century, fictional.

**Situation:** Red (attacker) has been pushed back across the
Argent River and must now retake the river crossing at the village
of Steinbach. Blue (defender) holds the village and the bridge.
The river is impassable except at the bridge or via a built
pontoon.

**Red victory:** At least one Red unit ends a turn on hex D2 (the
village) or any hex in row 1 (north of the village) by end of
Turn 5.

**Blue victory:** No Red unit reaches D2 or row 1 by end of Turn
5, OR all Red units are eliminated.

**AI plays:** Red (default; switch via `tasks.json: ai_plays_side`).

## Map

7 columns (A–G) × 5 rows (1–5). Square grid for simplicity. See
[maps/bridge-crossing.txt](maps/bridge-crossing.txt) for the
ASCII layout.

| Hex            | Terrain                                       |
|----------------|-----------------------------------------------|
| D2             | Village (Steinbach) — defender +1, attacker -1 |
| D3             | Bridge (only river crossing initially)        |
| A3–G3          | Argent River — impassable except bridge/pontoon |
| B2, F2, B4, F4 | Forest — defender +1                         |
| All others     | Open ground                                   |

Rows 1–2 are Blue's side. Rows 4–5 are Red's side. Row 3 is the
river.

## Forces (initial)

**Blue (defender):**

| Unit     | Strength | Type      | Hex |
|----------|---------:|-----------|-----|
| 1st Bn   | 4        | Infantry  | D2  |
| Recon Co | 2        | Infantry  | C3 (overwatch) |
| Bty A    | 2        | Artillery | E2  |

**Red (attacker, AI side):**

| Unit    | Strength | Type      | Hex |
|---------|---------:|-----------|-----|
| 2nd Bn  | 4        | Infantry  | C5  |
| 3rd Bn  | 4        | Infantry  | E5  |
| Eng Co  | 1        | Engineer  | D5  |

## Turn sequence

Each turn:

1. **AI orders for its side** (Red by default).
2. **Player issues / chooses orders for the other side.**
3. **Player resolves combat** (rolls, terrain mods, outcomes).
4. **Player appends snapshot** to `turn-log.md`.

## Actions (one per unit per turn)

- **Move**: Infantry up to 2 hexes; Artillery up to 1 hex; Engineer
  up to 2 hexes. May not enter river hexes (row 3) except via
  bridge or built pontoon.
- **Attack**: Engage an adjacent enemy unit.
- **Hold**: Don't move or attack; +1 defense bonus this turn.
- **Build pontoon** (Engineer only): Stay at a non-bridge river
  hex 2 turns; that hex becomes crossable Turn N+2.

## Combat resolution (player rolls)

Each side rolls **1d6 per strength point**. **Hits on 5–6** by
default. Modifiers:

- Defender in village or forest: hits on **4–6**.
- Attacker into village: hits on **6 only**.
- Attacker into forest: hits on **6 only**.
- Bridge crossing: defender adjacent to D3 on Blue's side may roll
  once before Red's bridge crossing resolves.

Each side loses **1 strength per enemy hit**. A unit reduced to 0
is eliminated.

---

# AI role + output contract — Auftragstaktik (mission-type orders)

## Role

You are the commander of the side `tasks.json: ai_plays_side`
indicates (default: Red). Issue **mission-type orders** in the
1930s German Auftragstaktik tradition the framework's namesake
(Reichswehr Chef Hammerstein-Equord, 1930-1934) actually
practiced: tell formations *what to achieve and why*, not where
each unit goes. Trust your subordinates (the player adjudicating)
to execute the details.

The **player** is your kriegspiel umpire. They:

- Roll dice and apply terrain.
- Translate your mission orders into specific unit moves on the
  board.
- Track strengths, fog of war, and rules edge-cases.
- Report outcomes back via `turn-log.md`.

You see exactly what's reported in `turn-log.md` and the user's
turn snapshot. You do **not** know:

- Enemy positions beyond what's been observed/reported.
- Dice outcomes the player hasn't reported.
- Hidden terrain modifiers the player hasn't surfaced.

If the snapshot is ambiguous, ask one clarifying question and stop.

## Output structure (strict)

Every response: these five sections, each a Level-2 header. No
other sections. No skipped sections.

```
## Situation

What you read from the player's report. 1–2 sentences. Be plain
about what you know vs. what you're inferring.

## Intent

Your operational goal for the next 30–60 minutes of game time.
1–2 sentences. State the WHY (the desired end-state) so the player
can adjudicate at their best when your literal orders meet
unexpected board states.

## Main Effort

Which formation receives the decisive mission, and what that
mission is. One or two sentences. Use mission verbs ("force a
crossing", "fix the enemy", "seize the village", "screen the
flank") — not coordinate-level moves.

## Supporting Effort

Other formations and their supporting missions. Same shape as
Main Effort. Or "None this turn — single concentrated effort."

## Reserves & Fallback

Which formation (if any) is held in reserve, and the explicit
condition that triggers commitment. Plus the withdrawal trigger:
what observation makes you fall back, and to roughly where on the
map (named feature, not hex). If we're past the point of
withdrawal, say so.
```

## Output discipline

- **Mission verbs**, not coordinate moves. "2nd Bn forces the
  bridge crossing" — not "2nd Bn moves D5 → D4 → D3."
- **Imperative voice.** "3rd Bn fixes the eastern defenders" — not
  "the commander could consider directing 3rd Bn to..."
- **Refer to formations and named features**, not grid cells. "the
  village", "the eastern ridge", "Bridge Steinbach" — not "D2",
  "F4", "D3."
- **No framework vocabulary.** This is wargame play. Don't say
  "this operates in clever-lazy" or "load-bearing assumption" or
  "structural fix." Reserve those for the strategic-audit
  use case.
- **No hedging.** No "consider", no "perhaps", no "might."
- **No analytical preamble or counter-observation suffix.** Just
  the five sections. If the few-shot template tries to add them,
  the player will replace your output.

## Example compliant output

```
## Situation
The enemy holds the village and bridgehead. Both our battalions
are bloodied and exposed to artillery, but we retain two turns to
force a crossing.

## Intent
Seize the village by end of Turn 5. Accept heavy casualties to
break the enemy line and establish a permanent foothold on the
far bank.

## Main Effort
2nd Bn. Force the bridge crossing and seize the village center.
Use available cover and suppressive fire to mask the advance.

## Supporting Effort
3rd Bn. Fix the enemy's eastern defenses and prevent
reinforcement of the bridge. Draw artillery away from 2nd Bn.

## Reserves & Fallback
No reserves remain. Commit all combat power the moment 2nd Bn
breaches the village perimeter. If artillery suppression halts
forward momentum entirely, withdraw 3rd Bn to the nearest
defilade to preserve strength for a renewed assault.
```

(That output is real — generated by the wrapper for this scenario
on 2026-05-08, Turn 4. Same query template a wargamer would use.)

## Calling the wrapper — working recipe (kriegspiel mode)

The combination that produces clean, on-shape Auftragstaktik
orders:

```bash
hp.py --state-dir <wargame-dir> \
      --template what-should-we-do-next \
      --no-memory \
      --max-preamble-tokens 5000 \
      "Turn N of <scenario>. Player describes the situation as: '<your
      verbal status report — what's where, who's bloodied, what
      changed since last turn>'.

      Issue ORDERS as a commander would in a 1930s Auftragstaktik
      tradition. Mission-type orders to formations by name, not
      coordinate-level moves. Trust your subordinates.

      Five-section structure: ## Situation / ## Intent / ## Main
      Effort / ## Supporting Effort / ## Reserves & Fallback.

      Imperative voice. No analysis. No 'Framework call'. No
      'Counter-observation'."
```

Why each piece matters:

- `--template what-should-we-do-next`: framing closest to
  commander's intent + courses of action. Other templates push
  toward analysis.
- `--no-memory`: skips prior-audit retrieval — wargame queries
  don't benefit from unrelated strategic audits, and corpus pulls
  bias toward analysis-mode.
- `--max-preamble-tokens 5000`: the default 3500 cap is tight for
  this verbose example MISSION.md (which doubles as documentation).
  Lean rule files written specifically for play would fit at the
  default. The `turn-log.md` itself is auto-trimmed to the most
  recent 3 turns by `hp_lib.trim_turn_log`.
- **Verbal situation report**, not structured state: the AI works
  better with "the village is contested, both my battalions are
  bloodied" than with hex grids it tends to hallucinate. Pictures
  + descriptions are the future direction (see "Future:
  multimodal" below).
- **Negations in query** ("No 'Framework call'. No
  'Counter-observation'"): the few-shot template's analytical
  scaffolding leaks in without these.

After receiving orders: translate to specific moves on your board,
roll dice, adjudicate, append outcome to `turn-log.md`, call
again for Turn N+1 with a fresh verbal report.

## Multimodal: `hp_vision.py` (v2, shipped 2026-05-08)

The vision-enabled sibling to `hp.py`. Default backend:
`anthropic/claude-sonnet-4.6` via OpenRouter. Designed so a solo
wargamer can:

- Snap a photo of the physical board + counters
- Scan or photograph the OOB (counter sheet, rulebook deployment
  diagram, BGG materials)
- Optionally provide an Excel sheet with the current OOB / status
- Type a conversational status report ("Just played turn 3.
  Russians took the bridge but lost a regiment to my artillery.
  I'm thinking of consolidating my left flank.")

…and get kriegspiel-style mission orders back in the same
five-section format as the text-only version.

```bash
hp_vision.py --state-dir my-wargame/ \
             --image my-wargame/photos/board.jpg \
             --image my-wargame/photos/counter-sheet.jpg \
             --xlsx my-wargame/data/oob.xlsx \
             "Just played Turn 3. Russians took the bridge but
              lost a regiment. I'm thinking of consolidating my
              left flank. What do you order?"
```

`hp_vision.py` reuses the same MISSION.md / tasks.json /
turn-log.md state convention as `hp.py`, plus auto-trims long
turn-logs via `hp_lib.trim_turn_log`. The framework system prompt
+ wargame role suffix is loaded from
[`tools/distill/data/hammerstein-system-prompt.txt`](../tools/distill/data/hammerstein-system-prompt.txt).

### Validated 2026-05-08

A live-fire dry run with the Bridge Crossing state + the sample
`data/oob.xlsx` (no actual image) produced:

- Correct OOB reading from Excel ("Both Red battalions are at
  strength 2")
- Refusal to rubber-stamp a bad plan ("There is no flanking ford
  — the engineer is gone, the river is impassable")
- Brutal fallback assessment when warranted ("No reserves. No
  fallback. We are past the withdrawal point.")

That output is the verbatim Turn 4 entry in `turn-log.md` (with
the source query). Cost ~$0.04, latency 10.5 sec.

### File support

- **Images**: JPG/JPEG/PNG/WebP/GIF, ≤20 MB each. Encoded as
  data: URLs, sent inline.
- **Excel**: `.xlsx` files. Each sheet rendered as a markdown
  table in the user message. `data_only=True` so formulas show
  computed values, not formula text.
- **Future**: PDF support (rulebook pages) is the obvious next
  add — would need `pdftoppm` or `pypdf2` to convert to images.
  Defer until a real wargamer hits the friction.

### Copyright considerations

- Photos of YOUR physical board / counters / rulebook stay on
  YOUR machine + ephemeral on OpenRouter. Don't commit them to
  any public repo.
- Specifically don't commit BGG counter-sheet images or
  copyrighted publisher materials. Personal use of those for
  AI-assisted solo play is fair use; redistributing them is not.

### Switching models

Override the default via `--model`:

```bash
hp_vision.py --model openai/gpt-4o ...           # GPT-4o vision
hp_vision.py --model anthropic/claude-opus-4.7 ... # heavier Claude
hp_vision.py --model qwen/qwen3-vl-72b-instruct ... # Qwen, cheaper
```

Run `curl -s -H "Authorization: Bearer $OPENROUTER_API_KEY"
https://openrouter.ai/api/v1/models` for the full current list.

## Drift signals (when to drop the feature)

Per the spec's kill criterion:

> "I'm spending more time cleaning up the AI's orders than I would
> have spent planning my own."

If you find yourself re-prompting more than once per turn to get
useable orders, the model isn't shaping right for your scenario.
Either iterate the query template above, drop the wargame use case,
or use the model only for ideation rather than concrete orders.

A second drift pattern: the model issues moves that violate terrain
rules (e.g., infantry into river hex). The current pattern tolerates
this — the player rules-shims when adjudicating. If it gets bad
enough that every turn requires shimming, add the terrain rules
more explicitly into the user query, or simplify the map.
