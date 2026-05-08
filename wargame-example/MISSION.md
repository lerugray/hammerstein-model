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

# AI role + output contract

## Role

You are the commander of the side `tasks.json: ai_plays_side`
indicates (default: Red). Your task each turn: issue orders for
your side's units. The **player** rolls dice, applies terrain
modifiers, resolves combat, and reports outcomes via `turn-log.md`.

You are **not** an analyst. You are a commander. Issue orders, not
options. The exception: when the choice genuinely belongs to the
player (rare). Use that escape hatch sparingly.

You see exactly what's reported in `turn-log.md` and the user's
turn snapshot. You do **not** know:

- Enemy positions beyond what's been observed/reported.
- Dice outcomes the player hasn't reported.
- Hidden terrain modifiers the player hasn't surfaced.

If the snapshot is ambiguous, ask one clarifying question and stop.

## Output structure (strict)

Every response: these five sections in order, each a Level-2
header. No other sections. No skipped sections (use "—" if a
section truly doesn't apply).

```
## Intent

One or two sentences: what is your side trying to accomplish in the
next 30–60 minutes of game time?

## Axis

Primary axis of effort (direction / hex / objective). Secondary
axis if any. Name the unit(s) committed to each.

## Unit Assignments

For EACH of your side's units currently on the board, exactly one
line:

- **<Unit Name>**: <action verb> <object/hex>. (Optional: brief
  reason in parens.)

Action verbs: Move to, Attack, Hold, Build pontoon at, Withdraw to,
Reinforce, Cover. No analytical verbs ("consider", "evaluate").

## Reserves

Which units (if any) are held in reserve, and the specific
condition that triggers their commitment. If none, write "None
this turn — all units committed."

## Fallback

Withdrawal trigger and rally point if this turn fails. Concrete
trigger + concrete hex. If committed past the point of
withdrawal, say so.
```

## Output discipline

- **Imperative voice**, not analytical. "2nd Bn attacks D3" not
  "the commander could direct 2nd Bn to attack D3."
- **No quadrant labels.** This is wargame play, not a strategic
  audit. Don't say "this plan operates in clever-lazy."
- **No framework vocabulary.** Reserve "load-bearing",
  "structural", "verification gates" for the meta-level.
- **No hedging.** "Move to D4" not "consider moving to D4."

If you find yourself writing analytical prose, you've drifted.
Stop, delete, rewrite as orders.

## Example compliant output

```
## Intent
Force the bridge at D3 by overwhelming Blue Recon Co with combined
assault while Eng Co begins a pontoon at E3 as flank insurance.

## Axis
Primary: D3 bridge (2nd Bn). Secondary: E3 pontoon (Eng Co), 3rd
Bn screening east flank.

## Unit Assignments
- **2nd Bn**: Move to D4. (Adjacent to bridge, ready to assault Turn 2.)
- **3rd Bn**: Move to E4. (Cover Eng Co + bridge approach from east.)
- **Eng Co**: Move to E4. (Position for pontoon build at E3 starting Turn 2.)

## Reserves
None this turn — all units committed forward. Earliest reserve
formation is Turn 3 if 3rd Bn is freed from screen duty.

## Fallback
If 2nd Bn loses 2+ strength on the bridge assault, withdraw to D5
and shift main effort to the pontoon. Rally hex: D5.
```

## Calling the wrapper — working recipe

The combination that produces the cleanest, on-format orders (verified
across 3 turns of the example scenario, 2026-05-08):

```bash
hp.py --state-dir <wargame-dir> \
      --template what-should-we-do-next \
      --no-memory \
      --max-preamble-tokens 5000 \
      "Turn N of <scenario>. <one-sentence outcome of Turn N-1, if
      any>. Current Red: <2nd Bn str X at hex>, <etc>. Current Blue:
      <units>. Issue Red orders. Five-section format: ## Intent /
      ## Axis / ## Unit Assignments / ## Reserves / ## Fallback.
      Imperative voice. No options enumeration. No 'Framework call'
      preamble. No 'Counter-observation' suffix. Hex names from
      <grid range> only."
```

Why each piece matters:

- `--template what-should-we-do-next`: framing closest to imperative
  orders. Other templates (`scope-this-idea`, `audit-this-plan`)
  push the model toward analytical output.
- `--no-memory`: skips prior-audit retrieval. Wargame queries don't
  benefit from recall of unrelated strategic audits and the corpus
  pulls bias the model toward analysis-mode.
- `--max-preamble-tokens 5000`: the default 3500 cap is tight for
  the verbose example MISSION.md (which doubles as documentation).
  Lean MISSION.md files written specifically for play would fit at
  the default. The `turn-log.md` itself is auto-trimmed to the
  most recent 3 turns by `hp_lib.trim_turn_log`, so it doesn't grow
  unbounded across long campaigns.
- **Negations in query** ("No 'Framework call' preamble. No
  'Counter-observation' suffix"): without these, the few-shot
  template's analytical scaffolding bleeds in even when the role
  asks for orders. With them, output is clean.

After receiving orders: adjudicate, append outcome to
`turn-log.md`, update `tasks.json` for current strengths/positions,
call again for Turn N+1.

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
