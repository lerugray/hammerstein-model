# hp precision test — 2026-05-08

Picked 10 recent audit-this-plan queries. For each, the matches
the corpus-id intersection filter would inject are listed below.

**Score:** for each match, change `[ ]` → `[x]` if structurally relevant
(same failure pattern, not just topically similar). Leave `[ ]` if noise.

Then run: `python tools/precision_test.py --score scoring/precision-2026-05-08.md`

Gate: ≥60% to commit to the intersection heuristic.

## Query 1 — 2026-05-08T14:09:29Z

**Target query (excerpt):** TWAR PTO-LENS P1.3 sentiment-cosmetic resolution — plan to ship.  CONTEXT: PTO-LENS audit (docs/PTO-LENS-EVENT-BEAT-AUDIT-2026-05-08.md) found that the `sentiment` field on press-report effect_data (v…

**Target retrieved corpus IDs:** [1, 31, 35, 50]
**Matched prior entries:** 3

- [ ] **match 1.1** — 2026-05-08T13:10:28Z — shared IDs: [31, 50]
  - prior query: Day plan for 2026-05-08 (Anthropic week reset just hit). Goal: push 6 priority projects (VC, ZPP, Retrogaze, GTA, TWAR, FnordOS) where leverage exists…
- [ ] **match 1.2** — 2026-05-05T19:26:32Z — shared IDs: [31, 50]
  - prior query: Phase 3 of the Hammerstein Continuity Track: bounded state-injection in hsh (Hammerstein Shell).  Context: hsh already auto-injects the last 3 turns o…
- [ ] **match 1.3** — 2026-05-05T19:23:18Z — shared IDs: [31, 50]
  - prior query: Phase 3 of the Hammerstein Continuity Track: bounded state-injection in hsh (Hammerstein Shell).  Context: hsh already auto-injects the last 3 turns o…

## Query 2 — 2026-05-08T14:08:53Z

**Target query (excerpt):** Audit this plan: write a Phase 2 validation harness for hp.py with five real audit queries and Boolean gates for token cap, JSONL integrity, subprocess timeout, and schema validation

**Target retrieved corpus IDs:** [1, 3, 6, 9]
**Matched prior entries:** 1

- [x] **match 2.1** — 2026-05-08T13:46:58Z — shared IDs: []
  - prior query: Audit the V1 IMPLEMENTATION PLAN in DESIGN.md (the file you have as context). The locked-in scope is settled — that's not what I'm auditing. I'm audit…

## Query 3 — 2026-05-08T14:02:16Z

**Target query (excerpt):** Scope this idea: a small Python CLI that summarizes git diffs into commit messages using a local LLM

**Target retrieved corpus IDs:** [5, 6, 18, 19]
**Matched prior entries:** 1

- [x] **match 3.1** — 2026-05-08T14:03:58Z — shared IDs: [5, 6, 18, 19]
  - prior query: Scope this idea: a small Python CLI that summarizes git diffs into commit messages using a local LLM

## Query 4 — 2026-05-08T14:00:41Z

**Target query (excerpt):** Audit this plan: rebuild the dispatcher to use a single retry loop with exponential backoff, removing the existing fallback chain to OpenRouter / DeepSeek / Ollama

**Target retrieved corpus IDs:** [18, 19, 33, 47]
**Matched prior entries:** 1

- [x] **match 4.1** — 2026-05-08T13:58:16Z — shared IDs: [18, 19, 33, 47]
  - prior query: Audit this plan: rebuild the dispatcher to use a single retry loop with exponential backoff, removing the existing fallback chain to OpenRouter / Deep…

## Query 5 — 2026-05-08T13:59:25Z

**Target query (excerpt):** tiny test query

**Target retrieved corpus IDs:** [3, 4, 9, 20]
**Matched prior entries:** 0

_(no matches at ≥2 or ≥1 fallback — nothing to score)_

## Query 6 — 2026-05-08T13:58:16Z

**Target query (excerpt):** Audit this plan: rebuild the dispatcher to use a single retry loop with exponential backoff, removing the existing fallback chain to OpenRouter / DeepSeek / Ollama

**Target retrieved corpus IDs:** [18, 19, 33, 47]
**Matched prior entries:** 1

- [x] **match 6.1** — 2026-05-08T14:00:41Z — shared IDs: [18, 19, 33, 47]
  - prior query: Audit this plan: rebuild the dispatcher to use a single retry loop with exponential backoff, removing the existing fallback chain to OpenRouter / Deep…

## Query 7 — 2026-05-08T13:46:58Z

**Target query (excerpt):** Audit the V1 IMPLEMENTATION PLAN in DESIGN.md (the file you have as context). The locked-in scope is settled — that's not what I'm auditing. I'm auditing the implementation cuts:  1. Single-file Pytho…

**Target retrieved corpus IDs:** [19, 31, 32, 50]
**Matched prior entries:** 3

- [ ] **match 7.1** — 2026-05-05T17:49:25Z — shared IDs: []
  - prior query: Operator-usage data + a critical operator-skill constraint contradicts a key assumption in this morning's Hammerstein TUI/REPL audit. Revisit the verd…
- [x] **match 7.2** — 2026-05-08T14:19:15Z — shared IDs: [19]
  - prior query: Stretch-goal feature for the persistent Hammerstein wrapper (hp.py, just shipped Phase 1-3): solitaire wargame opponent.  Player uploads/references lo…
- [x] **match 7.3** — 2026-05-08T13:32:57Z — shared IDs: [19]
  - prior query: Q3 follow-on for the persistent Hammerstein agent. Q1 fixed scope at 'stateful pull-based CLI wrapper'. Q2 fixed primary invocation as audit-with-deep…

## Query 8 — 2026-05-08T13:34:30Z

**Target query (excerpt):** Audit the following refined scope for the persistent Hammerstein agent v1. The 2026-05-07 audit said 'bank' against an unconstrained 'Hammerstein Agent'. This refined scope emerged from Q1-Q3 walked w…

**Target retrieved corpus IDs:** [9, 18, 32, 50]
**Matched prior entries:** 3

- [x] **match 8.1** — 2026-05-08T13:32:57Z — shared IDs: [18]
  - prior query: Q3 follow-on for the persistent Hammerstein agent. Q1 fixed scope at 'stateful pull-based CLI wrapper'. Q2 fixed primary invocation as audit-with-deep…
- [ ] **match 8.2** — 2026-05-05T17:49:25Z — shared IDs: []
  - prior query: Operator-usage data + a critical operator-skill constraint contradicts a key assumption in this morning's Hammerstein TUI/REPL audit. Revisit the verd…
- [x] **match 8.3** — 2026-05-08T13:30:50Z — shared IDs: [50]
  - prior query: Q2 follow-on for the persistent Hammerstein agent. Q1 settled scope at a 'stateful pull-based CLI wrapper': rungs 1+2 (cross-session memory with decay…

## Query 9 — 2026-05-08T13:10:28Z

**Target query (excerpt):** Day plan for 2026-05-08 (Anthropic week reset just hit). Goal: push 6 priority projects (VC, ZPP, Retrogaze, GTA, TWAR, FnordOS) where leverage exists, while dogfooding hammerstein-tui + Cursor IDE Au…

**Target retrieved corpus IDs:** [18, 19, 31, 50]
**Matched prior entries:** 3

- [ ] **match 9.1** — 2026-05-07T13:27:46Z — shared IDs: [18, 19, 50]
  - prior query: TWAR PC: next steps before UI focus (post twpc-007y PTO lens).  Goal: convert PTO-LENS into concrete design constraints, then do the minimum strategic…
- [ ] **match 9.2** — 2026-05-08T14:09:29Z — shared IDs: [31, 50]
  - prior query: TWAR PTO-LENS P1.3 sentiment-cosmetic resolution — plan to ship.  CONTEXT: PTO-LENS audit (docs/PTO-LENS-EVENT-BEAT-AUDIT-2026-05-08.md) found that th…
- [ ] **match 9.3** — 2026-05-05T18:33:18Z — shared IDs: [50]
  - prior query: Operator usage-driven request: build an interactive shell mode for Hammerstein. Validate or refute the proposed carve-out.  # Context — what's already…

## Query 10 — 2026-05-07T15:32:56Z

**Target query (excerpt):** TWAR PC: implement Kerch expedition (May 1855) as a scenario-authored event beat.  Goal: add one more pre-UI campaign-rhythm lever that is graph-first and testable headless.  Approach: - Extend Scenar…

**Target retrieved corpus IDs:** [3, 20, 31, 32]
**Matched prior entries:** 1

- [x] **match 10.1** — 2026-05-06T14:31:49Z — shared IDs: [31]
  - prior query: PLAN: TWAR PC Surface 5 (Operational Map) — corrected spec, ready for Friday Claude Design pickup.  CONTEXT: - TWAR PC = PC video game version of "The…
