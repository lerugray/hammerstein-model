# Hammerstein Model — Mission

A persistent strategic-reasoning agent built around the Hammerstein
framework. The dedicated dogfood/showcase deployment of the framework
itself: not the CLI tool that audits plans, not the TUI that runs
sessions — the persistent conversational agent Ray reaches for when
the question is strategic, multi-step, and ongoing.

## Why this exists

The Hammerstein audit (2026-05-07) verdict on Option B (persistent
strategic agent) was "bank." Ray's pushing back 2026-05-08: the
framework is anecdotally proven, brand-new to the AI field, and worth
attempting a clever-lazy DIY build before banking. Constraints:

- **Dev costs <$100/mo** — clever-lazy spirit; jerry-rigged, minimal
  new infrastructure
- **Wraps existing infra** — hammerstein CLI + hammerstein-tui +
  corpus + GS state likely cover ~70% of the substrate
- **Dogfood + showcase + possibly monetize** — Ray runs it himself;
  the build itself is portfolio-grade evidence the framework works

## What this is NOT

- Not a fine-tuned model from scratch (no training-grade infra)
- Not a heavy custom backend (the clever-lazy answer wraps what exists)
- Not a replacement for hammerstein CLI or hammerstein-tui (those are
  the substrate; this is the persistent layer above them)
- Not something to design ad hoc in mixed sessions — the design pass
  belongs in a dedicated Opus session with Hammerstein advising

## Status

**Folder/repo prep landed 2026-05-08.** Awaiting dedicated Opus
research session. Pre-flight questions in `RESEARCH-QUESTIONS.md`.

## Repo

Private at https://github.com/lerugray/hammerstein-model.

## Source brief

Memory entry from 2026-05-08:
`generalstaff-private/.claude/projects/.../memory/project_hammerstein_ai_diy_pushback.md`.
