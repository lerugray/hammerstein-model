# Research Questions — Pre-flight for the dedicated design session

Before any design work, the dedicated session opens with these four
questions. Answering them sharpens scope and either validates or
refines the prior Hammerstein audit verdict ("bank") against the
operator's clever-lazy DIY frame.

## Q1: What does "persistent" mean concretely vs. existing one-shot CLI?

The hammerstein CLI today runs one-shot audits / scope checks / worth
checks / next-step suggestions per invocation. "Persistent" needs a
concrete behavior delta:
- Does it remember prior conversations?
- Does it track the operator's currently-active project mix as
  ambient context?
- Does it volunteer observations between explicit asks?
- Does it have its own clock / scheduling awareness?

Until "persistent" has a concrete shape, we can't price it.

## Q2: What's the user story / invocation moment?

When does the operator reach for it instead of the existing CLI/TUI?
- "I'm thinking about X — what would Hammerstein say across the
  context of all my projects?" (cross-project strategic synthesis)
- "Audit this plan but with memory of every prior plan" (audit
  with deeper recall than a single invocation)
- "What did we decide about Y three weeks ago?" (long-term memory)
- "Is there a pattern across my last month's Hammerstein audits?"
  (meta-reasoning over the audit log)

The user story drives the surface (chat? slash-command? always-on
sidebar?) and the surface drives the cost shape.

## Q3: What wrap-existing-infra path keeps it under $100/mo?

The substrate that already exists:
- **hammerstein CLI** — audit/scope/worth/next + adversarial framing
- **hammerstein-tui (hamt)** — interactive conversation TUI (DeepSeek)
- **corpus** — 55+ failure-mode → fix → gate entries
- **project state** — live per-project context (MISSION.md,
  tasks.json, per-call audit log) — the operator's own General Staff
  layout, but the wrapper accepts any directory via `--state-dir`
- **Hammerstein audit log** — memory of past judgments
- **PROGRESS.jsonl + git history** — what shipped and when

Plausible clever-lazy path:
- System prompt encoding the framework + voice
- RAG over corpus + project state + audit log
- Memory layer (vector store or structured) for cross-session recall
- Routes to existing CLI tools for one-shot operations
- Hosted cheaply (DeepSeek as default model + Claude/OpenRouter for
  hard reasoning; budget gate per the existing scheduler pattern)

Question: where does the cost actually land? Inference is cheap on
DeepSeek; storage is trivial; the budget cap forces "use Claude only
when DeepSeek isn't enough." Is $100/mo the right cap, too tight,
too loose?

## Q4: Does Hammerstein-the-tool still say "bank" against the refined scope?

The prior audit evaluated "Hammerstein Agent" as an unconstrained
build. Re-run the audit against the refined scope from Q1-Q3:
- Defined "persistent" behavior
- Concrete user story
- Wrap-existing-infra path with budget cap

If Hammerstein still says "bank" — heed that and bank for real.
If the verdict flips — proceed with v0 design.

## Process

The dedicated session walks Q1 → Q2 → Q3 → Q4 in order. Each answer
sharpens the next. Don't pre-empt Q4 by deciding the verdict in
advance; the audit-this-plan template runs against whatever scope
emerges from Q1-Q3, not against assumptions baked in early.
