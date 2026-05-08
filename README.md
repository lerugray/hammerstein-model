# hammerstein-model

A persistent strategic-reasoning agent built around the
**[Hammerstein framework](https://github.com/rayweiss/hammerstein)** —
a clever-lazy / clever-industrious / stupid-industrious /
stupid-lazy diagnostic for catching misdirected effort in
software, design, and strategy decisions.

This repo contains two complementary artifacts:

1. **`hp.py`** — a stateful CLI wrapper that adds cross-session
   memory + ambient project-context injection on top of the existing
   one-shot [hammerstein CLI](https://github.com/rayweiss/hammerstein).
   Production-shaped, ~$0.01/audit.
2. **A distillation experiment** (in flight) that fine-tunes a small
   open base model on synthetic Hammerstein outputs to produce a
   distributable `hammerstein-7b.gguf` artifact. Behavior cloning,
   not reasoning training.

The wrapper is the production path. The distilled model is the
shareable artifact.

## Origin

Built as a focused Opus design session 2026-05-08, walking pre-flight
questions Q1-Q4 with the hammerstein CLI advising. The 2026-05-07
audit verdict on this proposal was "bank" — too unconstrained.
Refining the scope through Q1-Q4 with audit checks at each step
flipped the verdict to "proceed with modifications." The walk + every
subsequent design decision is recorded in
[`DESIGN.md`](DESIGN.md).

The whole pre-flight walk cost $0.054 in OpenRouter credits across
five hammerstein audits. Zero Anthropic quota burned.

## What `hp.py` is

A ~120-LOC Python script that pipes the existing one-shot CLI:

```
hp <query>
   ↓
1. Pre-fetch corpus IDs via `hammerstein --show-prompt` (free, ~200ms)
2. Read prior call logs (~/.hammerstein/logs/{hammerstein,hp}-calls.jsonl)
3. Filter for relevance (rare-token + recency-decay; see Phase 1.5)
4. Build token-budgeted preamble: prior audits + GS project state
5. Subprocess hammerstein --context-file <preamble> with hard timeout
6. Validate response shape, quarantine on schema drift
7. Append to hp-calls.jsonl + hp-metrics.jsonl
8. Pass-through to stdout
```

What it *isn't*: a daemon, a scheduler, a vector store, a chat agent,
a UI. Per Q1 of the design walk: "persistent" means continuity of
context, not background execution.

## What's in this repo

| Path | What it is |
|---|---|
| [DESIGN.md](DESIGN.md) | Q1-Q4 walk, locked-in scope, Phase 1.5 finding |
| [MISSION.md](MISSION.md) | Constraints + status |
| [RESEARCH-QUESTIONS.md](RESEARCH-QUESTIONS.md) | Pre-flight Q1-Q4 |
| [hp.py](hp.py) | The wrapper CLI (123 LOC) |
| [hp_lib.py](hp_lib.py) | Helpers (200 LOC) |
| [hp_filter.py](hp_filter.py) | Phase 1.5 rare-token filter (115 LOC) |
| [hp_status.py](hp_status.py) | Phase 3 abandonment-gate script (131 LOC) |
| [tests/test_hp.py](tests/test_hp.py) | 19 pytest cases (188 LOC) |
| [tools/precision_test.py](tools/precision_test.py) | Phase 1.5 scoring harness |
| [tools/distill/](tools/distill/) | Distillation experiment (gen / train / eval) |
| [WARGAME-EXTENSION.md](WARGAME-EXTENSION.md) | Phase 5 stretch — solitaire wargame opponent |
| [WEB-UI-EXTENSION.md](WEB-UI-EXTENSION.md) | Phase 6 stretch — local web UI |
| [MODEL-EXPERIMENT.md](MODEL-EXPERIMENT.md) | Distillation experiment design + cost analysis |
| [scoring/precision-2026-05-08.md](scoring/precision-2026-05-08.md) | Phase 1.5 honestly-scored precision evaluation |

## Phase status (2026-05-08)

| Phase | What | Status |
|---|---|---|
| Phase 0 | Substrate verification | ✅ done |
| Phase 1 | MVP wrapper | ✅ done |
| Phase 1.5 | Precision test on retrieval heuristic | ⚠️ ran — corpus-id intersection at 15%, replaced with rare-token filter at 53% (below 60% gate, but Phase 3 dogfood validates empirically) |
| Phase 2 | Pytest validation | ✅ done — 19/19 passing |
| Phase 3 | Dogfood + auto-enforced gate | ✅ CONTINUE verdict (cost ratio 1.23×, 3/5 last calls had conclusion_changed=true) |
| Phase 4 | Failure-pattern preflight | Deferred — gated on Phase 3 sustained pass |
| Phase 5 | Wargame solitaire opponent | Stretch — see WARGAME-EXTENSION.md |
| Phase 6 | Local web UI | Stretch — see WEB-UI-EXTENSION.md |
| **Distillation experiment** | Hammerstein-7B GGUF artifact | In flight — see MODEL-EXPERIMENT.md |

## Honest framing

`hp.py` is a **thin wrapper.** That is intentional, per the
clever-lazy frame. The framework — system prompt + corpus +
retrieval + few-shot templates — is the IP. The wrapper just adds
state. The base inference model (Qwen3.6-plus on OpenRouter) is
interchangeable.

The distillation experiment exists because "I built a wrapper" reads
weaker than "I trained a model" for portfolio signaling, even if
the wrapper is technically the better tool. Per the
[hammerstein-on-itself audit](MODEL-EXPERIMENT.md#hammersteins-scoping-verdict-2026-05-08):

> "The FT path wins on signaling ROI even if it loses on capability
> ROI. Frame it as behavior cloning, not reasoning training."

Both ship; neither blocks the other. If the distillation passes its
≥80%-of-gold structural-score gate, we ship `hammerstein-7b.gguf`.
If it fails, the failure log itself becomes the portfolio piece.

## Running the wrapper

```bash
# In a project dir with auto-detectable GS state:
.venv/bin/python hp.py "Audit this plan: <your strategic question>"

# Or with an explicit template:
hp.py --template scope-this-idea "<query>"

# Dry-run (build preamble, don't burn the OpenRouter call):
hp.py --dry-run "<query>"

# Check the Phase 3 gate verdict:
.venv/bin/python hp_status.py
```

Requires `OPENROUTER_API_KEY` in env and the
[hammerstein CLI](https://github.com/rayweiss/hammerstein) installed.

## Cost arc

| Stage | Spend |
|---|---|
| Q1-Q4 design walk | $0.04 |
| Phase 1 implementation + dogfood | $0.05 |
| Phase 1.5 precision test | $0.00 (analysis only) |
| Phase 2/3 setup | $0.00 |
| **Total to ship the wrapper** | **~$0.10** |
| Distillation experiment (in flight) | ~$10 estimated |
| | |
| Anthropic quota burned by hammerstein | $0 |

## License

TBD — MIT or Apache 2.0 likely. The
[hammerstein corpus + framework](https://github.com/rayweiss/hammerstein)
has its own license; this repo is downstream tooling.

## Ray's framework, in one paragraph

The Hammerstein framework is named for Kurt von Hammerstein-Equord
(Chef der Heeresleitung 1930-1934), who classified officers along
two axes: clever/stupid × lazy/industrious. The dangerous quadrant
is **stupid-industrious** — working hard in the wrong direction
with total commitment. The framework's central claim is that
misdirected effort with commitment is more dangerous than
incapability, and the right defense is structural (verification
gates, role assignment, legible failure logging) rather than
dispositional (better instructions, more careful execution).
This repo is one applied instance of the framework: a wrapper that
audits its own use, a precision test that honestly graded its own
heuristic at 53% and pivoted, an abandonment gate that votes ABORT
without operator approval. The framework auditing itself is the
design.
