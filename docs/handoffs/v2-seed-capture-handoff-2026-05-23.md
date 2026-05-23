# Handoff: v2 seed capture continuation - 2026-05-23

This brief picks up the home-PC evening session (2026-05-22 continuing
into 2026-05-23) where the orchestrator session moves from
generalstaff-private cwd into hammerstein-model cwd. Ray is opening
generalstaff-private on his Mac in parallel for unrelated work; this
session must stay out of generalstaff-private's mutation surface
(reads OK, edits not OK) until the Mac session finishes.

## Where to start

**Read these in order before doing anything else:**

1. `data/v2-casual-seeds-scratchpad.md` (this repo) - single source
   of truth for v2 design. Has the locked decisions, revised dataset
   spec, target voice, and Seed 01 already captured.
2. `data/README-sft-datasets.md` (this repo) - v1's dataset shape +
   sanitization rules + the playbook for the OpenRouter teacher
   expansion that produced the 339-pair Mac expansion file.
3. `C:\Users\rweis\OneDrive\Documents\homelab\log\conversations.md` -
   v1's actual outputs from tonight's Telegram dogfood. Seed 01 was
   built from the Napoleon III exchange here.

## What's locked

All four design-axis decisions for v2 are locked (see scratchpad).
The four-source dataset spec is also locked. The remaining work is
mechanical execution.

## What's next (in order)

1. **Ray writes Seeds 02-30** in the scratchpad. Workflow Ray
   prefers: he sends casual messages via Telegram to
   `@hammerstein_homelab_bot`, the bot logs the exchanges to
   `homelab/log/conversations.md`, Claude pulls the exchange + drafts
   an ideal-response candidate in scratchpad, Ray approves/edits/replaces.
   Alternative: Ray cold-writes seeds without going through the bot.
   He liked the Telegram dogfood approach for the first one - "perfect
   suggestion claude - and will be fun too" - so keep that as primary.
2. **OpenRouter teacher expansion script.** Once seeds are at ~30,
   write a script (here in hammerstein-model) that: (a) samples ~100
   prompts from `HuggingFaceH4/no_robots`, ~50 multi-turn from
   `OpenAssistant/oasst2`, ~20 refusal-pattern from `anthropic/hh-rlhf`;
   (b) for each, calls Qwen3.6-plus on OpenRouter with the locked
   voice spec + Ray's seeds as exemplars, asking the teacher to
   rewrite the response into the staff-officer voice; (c) writes the
   restyled pairs to `data/v2-casual-restyled-2026-05-23.jsonl`.
   Sanitize per the existing pattern (no real collaborator names,
   no API keys, no medical content). Estimated OpenRouter spend:
   $1-3 for the full expansion.
3. **Audit-trigger discrimination set (~50 pairs).** Claude writes
   these directly. Positive examples: prompts that DO trigger audit
   (audit-shape language, /audit command). Negative examples:
   prompts that look almost-audity but shouldn't (e.g. "testing the
   relay" - ambiguous, should be casual; "what are you thinking
   about" - casual, NOT framework). File at
   `data/v2-audit-discrimination-2026-05-23.jsonl`.
4. **Concatenate + sanitization pass.** Combine seeds + restyled +
   discrimination into `data/ray-stack-sft-v0.2-additions.jsonl`.
   Run the same sanitization grep regex as v0.1 (`(Jason|Ricky|Kunal|
   James Rodgers|Ryan Fyr|sk-[a-zA-Z0-9]{10,}|hf_[A-Za-z0-9]+)`).
5. **Training run config.** Add the new file to the v0.2 training
   recipe. Decide: full retrain from base Qwen2.5-7B vs continued
   training from the v0.1 LoRA checkpoint (continued is faster +
   cheaper; full retrain is safer if v0.1's bad habits persist).
   Probably continued; revisit if eval shows the bad habits don't
   shift.
6. **RunPod fire.** Run the training. Eval against the v1 failure
   modes (auditify-casual-greeting; fabricate GSD references; refuse-
   then-fabricate on historicals; sentence-continuation quirk).
7. **Deploy to home PC.** Replace `hammerstein-7b` model in Ollama
   with v0.2; smoke via Telegram; update homelab README.

## Running services state on home PC (don't touch)

- **Ollama**: HTTP up on `localhost:11434`, autostart wired (login
  shortcut). Closes Ollama desktop window after launch are fine -
  server stays in tray.
- **Telegram bot**: visible cmd window on home PC, HTTP /state up on
  `localhost:8765`, autostart wired via
  `homelab/scripts/install-autostart.ps1` + Startup folder shortcut.
- **CRT face**: open in browser, polling bot /state, displaying the
  staff-officer face.

The bot has 6+ messages in history (preserved across the reset via
`bot/state.json`). Conversation log is auto-appending to
`homelab/log/conversations.md`.

## Cross-machine constraint

Ray is on his Mac running a parallel session in generalstaff-private
for unrelated work. This session in hammerstein-model can:
- READ from `C:\Users\rweis\OneDrive\Documents\generalstaff-private\`
  via absolute path (CLAUDE.local.md context, MEMORY.md, recent
  session notes, tasks state). Reads are safe.
- WRITE to hammerstein-model (this repo), homelab, or any other
  non-generalstaff-private repo.
- NOT mutate generalstaff-private until the Mac session is done.
  No tasks.json edits, no docs/sessions/ writes, no commits there.

When tonight's work is wrapping AND the Mac session is done, the
canonical session note for tonight gets written to
`generalstaff-private/docs/sessions/` per usual pattern.

## Tasks state at handoff

Tracked in-session only (not in any repo file). Open at handoff:
- Capture v2 casual seeds via Telegram dogfood (in_progress; 1 of ~30
  done as Seed 01)
- Design hm-010 v2 dataset shape (in_progress; spec locked, execution
  pending)
- Rung 1 capability - web search + bookfinder-general lookup (pending;
  filed as followup to v2)

The new session can recreate these via TaskCreate as needed; the
canonical state is the scratchpad + this brief, not the in-session
task list.

## What v2 should NOT do

Per the locked decisions, v2 should NOT:
- Default to audit register on casual prompts
- Fabricate GSD-prefixed manual references
- Refuse historical questions and then start making up dates/outcomes
- Continue the user's sentence before pivoting to its own response
- Be "AI designed for engineering judgment, not historical analysis"
  (Hammerstein framework applies to history fine; the actual block is
  no internet access, not topic competence)

v2 SHOULD:
- Default to staff-officer character casual voice
- Trigger audit register on natural audit-shape OR /audit command
- Refuse with honest constraint-naming when factual + no tools
- Offer the framework-shape angle as a hedged alternative when
  appropriate
