# Session 2026-05-22 / 2026-05-23 - v2 design lock + seed capture started

Continuation of the home-PC evening session that deployed hammerstein-7b
and shipped the Rung 0 homelab (CRT face + Telegram bot + log). After
Ray reset the PC to resolve the Focusrite USB enumeration issue (which
worked), services were restored manually, then we shifted into v2 design.

Started in generalstaff-private cwd as orchestrator session. Moving
into hammerstein-model cwd at the end of this note so Ray can run a
parallel session in generalstaff-private on his Mac for unrelated work.

## What landed

**Homelab autostart wired** (committed in homelab as `4076da3`).
`scripts/install-autostart.ps1` + `scripts/bot-launcher.bat` register
a Startup folder shortcut for the bot with a wait-for-Ollama poll.
Ollama already had its own startup shortcut from April. README updated.
Activation: reboot to test (Ray's call).

**Services restored after reset.** Ollama HTTP up on `localhost:11434`,
bot HTTP /state up on `localhost:8765`. Bot's `state.json` preserved 6
messages of conversation history across the reset. CRT face open in
browser, polling /state, reflecting the staff-officer face.

**v2 design decisions locked** (all four bite-sized questions answered):

1. **Casual register: staff-officer character, framework off.** Keeps
   the period-coded staff-officer voice in casual mode. Audit register
   reserved for explicit triggers.
2. **Audit trigger: natural detection + /audit command override.**
   Natural language (audit / review / failure-modes / what's-wrong)
   triggers the register; `/audit <x>` is the explicit override.
3. **Casual data source: Ray writes ~30 seeds, OpenRouter teacher
   expands to ~200.** Matches the playbook that produced the 339-pair
   Mac expansion. Plus restyling from `no_robots` / `oasst2` / `hh-rlhf`.
4. **Sequential to Rung 1.** v2 ships casual register first. Web
   search + bookfinder-general lookup (Rung 1 tool layer) is a separate
   followup, layered on the same model via system-prompt + tool calling
   without retraining.

**Revised v2 dataset spec** (see `data/v2-casual-seeds-scratchpad.md`):
~250 new pairs across seeds (30) + no_robots restyled (100) + oasst2
restyled (50) + hh-rlhf refusal (20) + audit-trigger discrimination
(50). Plus the existing v0.1 (541 pairs) + Hammerstein synthetic (~5k)
that v1 already trained on.

**Seed 01 captured** from the Napoleon III exchange. v1 refused
correctly but then auditified the refusal AND started fabricating
("Napoleon III captured Rome and proclaimed Victor Emmanuel II as King
of Italy" - factually wrong). Ideal response drafted in the locked
voice, approved by Ray. Lives in scratchpad as the template for the
remaining ~29.

## v1's diagnosed failure modes (from tonight's Telegram dogfood)

- Auditifies every casual prompt ("welcome home" → JSON operating-state)
- Fabricates GSD-prefixed manual references ("testing the relay" →
  invented GSD-028 troubleshooting flow)
- Refuses historical questions and then starts making things up mid-answer
- User-sentence-continuation quirk (model completes user's prompt
  before pivoting to its own response)

All four addressed by the v2 dataset shape above. Sentence-continuation
is a JSONL-shape fix (explicit assistant-turn-start tokens).

## What's next

See `docs/handoffs/v2-seed-capture-handoff-2026-05-23.md` for the full
execution plan. Short version:

1. Ray writes Seeds 02-30 in the scratchpad (via Telegram dogfood
   workflow he liked, or cold-write)
2. OpenRouter teacher expansion script for the restyled pairs
3. Audit-trigger discrimination set (Claude writes)
4. Concatenate + sanitize per v0.1 pattern
5. Training run config (likely continued training from v0.1 LoRA, not
   full retrain from base)
6. RunPod fire, eval against the four v1 failure modes
7. Deploy v0.2 to home PC, smoke via Telegram

**Followup filed:** Rung 1 capability (web search + bookfinder-general
lookup). Separate project. Layered on the model via system prompt +
tool calling; no retraining needed.

## Pointers (cross-repo)

- v2 design SSOT: `data/v2-casual-seeds-scratchpad.md` (this repo)
- Execution plan: `docs/handoffs/v2-seed-capture-handoff-2026-05-23.md`
  (this repo)
- v1 conversation log: `C:\Users\rweis\OneDrive\Documents\homelab\log\conversations.md`
- v0.1 dataset README: `data/README-sft-datasets.md` (this repo)
- Homelab bot service: `C:\Users\rweis\OneDrive\Documents\homelab\bot\server.mjs`
- Originating session note for the 2026-05-22 home-PC evening:
  `C:\Users\rweis\OneDrive\Documents\generalstaff-private\docs\sessions\2026-05-22-home-pc-evening-hammerstein-deploy-and-homelab-build.md`
  (continuation of the 2026-05-22 Mac-night handoff)

## Cross-machine state at handoff

Ray's home PC: this session continues in hammerstein-model cwd after
the close-and-reopen.
Ray's Mac (sibling parallel): may be running a generalstaff-private
session for unrelated work. Until that's done:
- This session can READ from generalstaff-private (CLAUDE.local.md
  context, MEMORY.md, recent session notes) via absolute paths.
- This session must NOT write to generalstaff-private. No tasks.json
  edits, no docs/sessions/ writes, no commits there.
- When tonight's work wraps AND Mac is done, the canonical
  generalstaff-private session note for tonight gets folded in there.
