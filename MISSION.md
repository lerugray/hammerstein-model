# Hammerstein Model — Mission

A persistent strategic-reasoning agent built around the Hammerstein
framework. The dedicated dogfood/showcase deployment of the framework
itself: not the CLI tool that audits plans, not the TUI that runs
sessions — the persistent conversational layer the operator reaches
for when the question is strategic, multi-step, and ongoing.

## Why this exists

The Hammerstein framework is anecdotally proven and brand-new to
the AI field. Worth attempting a clever-lazy DIY build before
banking on something heavier. Constraints:

- **Dev costs <$100/mo** — clever-lazy spirit; jerry-rigged, minimal
  new infrastructure
- **Wraps existing infra** — hammerstein CLI + hammerstein-tui +
  corpus + project state likely cover ~70% of the substrate
- **Dogfood + showcase + possibly monetize** — the operator runs it
  on their own work; the build itself is portfolio-grade evidence
  the framework works

## What this is NOT

- Not a fine-tuned model from scratch (no training-grade infra)
- Not a heavy custom backend (the clever-lazy answer wraps what exists)
- Not a replacement for hammerstein CLI or hammerstein-tui (those are
  the substrate; this is the persistent layer above them)
- Not something to design ad hoc in mixed sessions — the design pass
  belongs in a dedicated session with Hammerstein advising

## Status

Phase 1 wrapper, Phase 1.5 precision test, Phase 2 tests, Phase 3
dogfood gate, Phase 5 wargame extension (text + multimodal), Phase 6
local web UI, and the Hammerstein-7B distillation experiment have
all shipped. See [README.md](README.md) for the phase status table
and [DESIGN.md](DESIGN.md) for the full design walk that locked in
scope.

## Repo

[github.com/lerugray/hammerstein-model](https://github.com/lerugray/hammerstein-model)

---

> **What's "GS state" / "GS audit log"?** The operator runs a
> personal command-and-control system called *General Staff* (private
> repo) which keeps `MISSION.md` / `tasks.json` / a per-call audit
> log per active project. The hp wrapper auto-detects that layout
> when run inside a project directory the GS knows about, and falls
> back gracefully to no-state when run outside it. None of the GS
> internals are required to use the wrapper or reproduce the
> distillation experiment — they're just the live data source for
> the operator's own dogfood.
