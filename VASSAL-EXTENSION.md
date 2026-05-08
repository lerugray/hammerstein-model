# VASSAL Integration — Stretch Extension

**Status:** Design doc, 2026-05-08. Not built. This file thinks
through the spectrum of "give Hammerstein VASSAL access" and
recommends a starting point.

## What VASSAL is

[VASSAL](https://vassalengine.org/) is an open-source Java
wargame engine. Each game is a "module" (`.vmod` file) containing
the map image, counter graphics, rules text, and basic mechanics
(dice, turn tracking, fog-of-war optionally). Thousands of modules
exist for nearly every published wargame — Imperial Bayonets, OCS,
ASL, GMT titles, vintage Avalon Hill stuff, etc. Players move
counters by drag-and-drop, roll dice via in-app buttons, save
games to `.vsav` files, and review games via `.vlog` recordings.

VASSAL is the de-facto standard for solo wargamers who don't want
to clear table space, and for online multiplayer between humans.
It already does the bookkeeping a paper game forces on you. Adding
an AI opponent to that loop is the natural next move.

## Why this could matter

Solo wargamers are the audience the Phase 5 extension was scoped
for. VASSAL is *where they already play*. If Hammerstein can plug
into VASSAL — even loosely — the wargame extension stops being a
toy example and becomes a usable AI opponent for any of the
thousands of games VASSAL covers.

Critically, VASSAL handles the parts the current `hp_vision.py`
workflow does NOT:

- **Persistent state**: VASSAL tracks counter positions exactly,
  no transcription needed.
- **OOB visualization**: every game's counters are right there in
  VASSAL — no separate Excel sheet required.
- **Map fidelity**: VASSAL renders the actual map at the actual
  scale, with all overlays and named features.
- **Turn structure**: VASSAL knows whose turn it is, what phase
  of the turn, what's already been done.

The current `hp_vision.py` workflow — Mac user takes a phone
photo of their physical board + writes an Excel + writes a verbal
report — is friction-heavy. Most wargamers won't do all that
every turn. **A VASSAL-aware wrapper removes most of that
friction.**

## The spectrum of integration depth

Five viable approaches, ordered by effort.

### (A) Manual screenshot → `hp_vision.py` (works TODAY, 0 new code)

Player takes a screenshot of the VASSAL window (`cmd-shift-4` on
macOS, `Snipping Tool` on Windows), saves to disk, calls:

```bash
hp_vision.py --state-dir my-vassal-game/ \
             --image ~/Desktop/vassal-turn-3.png \
             "Just played turn 3 of Imperial Bayonets. <verbal report>"
```

This works **right now**. The wrapper accepts any PNG/JPEG. Sonnet
4.6 (or any vision model) can read VASSAL's UI fine — it's just a
clear graphic with counters and a hex map.

**Pros:** Zero new code. Immediately testable. Pattern works for
any game in any state. Cross-platform.

**Cons:** Friction (~30 sec per turn just for screenshotting).
No state continuity beyond `turn-log.md`. Player has to write
verbal updates.

### (B) Auto-screenshot helper (~30 LOC, ~1 day)

A thin `hp_vassal.py` script that:

1. Detects the VASSAL window (macOS: `screencapture -l <window-id>`;
   Linux: `wmctrl + scrot`; Windows: PowerShell `Add-Type` UI
   automation).
2. Captures the current VASSAL window to a temp file.
3. Calls `hp_vision.py` with that image + the player's verbal
   report.
4. Cleans up the temp file.

```bash
hp_vassal.py --state-dir my-vassal-game/ \
             "<verbal report>"
```

**Pros:** One command instead of three. Removes the manual
screenshot step. Still cross-platform-able with per-OS
implementations. Doesn't touch VASSAL itself, so works for any
module.

**Cons:** OS-specific window-detection code. Doesn't read VASSAL
state structurally — it's still a screenshot. No "VASSAL knows
whose turn it is."

### (C) Parse VASSAL `.vsav` save files (~few days, format spelunking)

VASSAL save files are zip archives containing module data + game
state. The state format is documented for some modules but
inconsistent across them — each module's authors decide how state
is serialized.

A `.vsav` parser would extract:

- Counter positions on the current map
- Counter strengths / status (where modules expose this)
- Current turn / phase
- Player notes

…and feed structured state into `hp_vision.py` (alongside or
instead of a screenshot).

**Pros:** Structured state, no transcription. AI gets exact piece
positions. Could potentially handle hidden-movement games (the
state file knows what each player can see).

**Cons:** Per-module work — every game's `.vsav` has its own
schema. Realistic to support 2-3 of Ray's csl-repo games well, not
"any VASSAL module." Significant maintenance burden as modules
update.

### (D) BeanShell / VASSAL scripting hooks (~1-2 weeks)

VASSAL has an embedded BeanShell (Java-flavored) scripting system
for module-side automation. A custom module-side script could:

- Export current state to a known format on a hotkey
- Or POST state to a local HTTP endpoint each turn
- AI processes, returns orders
- Script optionally moves counters automatically

Some VASSAL modules already use this for automated dice / combat
resolution. Our hook would be additive.

**Pros:** Real-time integration. AI can respond per-turn without
a separate command. Could automate counter movement (advanced).

**Cons:** Per-module scripting work. Requires module source access
or willingness to modify module copies. BeanShell is niche; few
people contribute here.

### (E) Native VASSAL Java plugin (~weeks, requires Java work)

Build a VASSAL plugin (`.jar`) that adds an "AI Opponent" panel.
Plugin captures state via VASSAL's internal API, calls Hammerstein
backend, applies moves, plays sound effects when ordered.

**Pros:** Most polished UX. Distributable as a single `.jar` to
the VASSAL community. Could ship via VASSAL's official module
catalog.

**Cons:** Java + VASSAL internals + UI work. Big lift. Maintenance
across VASSAL releases. Probably needs a VASSAL community
collaborator who already knows the codebase.

## What the corpus-vs-engineering memory says

The memory note from this session
([feedback_invest_in_corpus_not_engineering.md](../.claude/projects/-Users-rayweiss-Desktop-Dev-Work-hammerstein-model/memory/feedback_invest_in_corpus_not_engineering.md))
says: spend marginal effort on **framework, applied surfaces,
honesty, portfolio coherence** — not on engineering improvements
that commoditize.

Where do these options land?

- **(A) Manual screenshot**: zero engineering, pure applied
  surface. Fits the high-payoff axis perfectly. **Already built.**
- **(B) Auto-screenshot**: small engineering investment for big
  friction reduction. Probably worth it. Still applied-surface.
- **(C) `.vsav` parser**: per-module engineering. Diminishing
  returns. Drop unless we're scoping for one specific game.
- **(D) BeanShell hooks**: per-module + niche tooling. Unless Ray
  wants to play a specific game often, low payoff.
- **(E) Java plugin**: significant engineering, weeks of work,
  fully commoditizable (anyone could build it). Ought NOT be
  early-portfolio investment.

## Recommendation

**Start with (A). Ship (B) if (A) gets used.**

(A) is already built — it's `hp_vision.py` plus a manual
screenshot. Ray can test this today on any VASSAL module he plays.
The next-1-hour move is: open VASSAL with one of his csl-repo
games, screenshot it, run `hp_vision.py` against the screenshot,
see if Sonnet 4.6 reads the counter positions correctly. That
empirical test is the gate for whether to invest further.

If the OCR works well on his games → friction is the only
remaining problem → (B) is the right next investment.

If the OCR is poor on dense counter-stack games → screenshots
won't cut it → either go to (C) for one specific game OR drop
the VASSAL ambition and stay with the photo + Excel workflow.

**Don't pre-build (B) before validating (A) works.** That's the
exact "stupid-industrious" trap the framework names.

## Hammerstein-on-itself

Per the framework: imagination + taste + direction stay with the
operator. The strategic call here is *which game to test (A) on
first*. Ray's csl repo (Imperial Bayonets Solferino, We Were Not
Cowards) is the natural starting set — small enough that Ray
knows the rules deeply, with the bonus that Ray can publish a
"my own framework playing my own game" applied-instance writeup
that doubles as portfolio content.

That writeup IS the high-payoff axis the memory note flagged.
Engineering polish around VASSAL is the snapshot; "Hammerstein
played Imperial Bayonets and these were its commander's
decisions" is the appreciating asset.

## Open questions for a future session

If (A) tests well and we move toward (B):

1. **Window detection on Ray's Mac**: `screencapture -l <window-id>`
   needs the VASSAL window's CGWindow ID. Use AppleScript
   (`tell application "VASSAL" to get id of window 1`) or
   `screencapture -W` (interactive window pick) as a fallback.
2. **Multi-monitor / VASSAL fullscreen**: account for both.
3. **Counter-stack rendering**: when counters stack on a hex,
   VASSAL by default shows only the top — the AI would miss
   underlying units. Either configure VASSAL to show stacks
   expanded, or screenshot from a different view.
4. **Hidden-movement games** (Imperial Bayonets, We Were Not
   Cowards both have optional rules): the screenshot will only
   show what the *human* player sees. The AI gets the same fog
   of war. That's actually correct kriegspiel behavior — the
   commander only sees what's reported.
5. **Multi-image turns**: a single screenshot may not capture the
   full map + the OOB sidebar + the turn-tracker simultaneously.
   `hp_vision.py` already supports multiple `--image` flags;
   capture each region separately and pass all of them.

These are tractable. None block starting (A).
