# hammerstein-model

![Hammerstein-7B. The framework, distilled. Persistent · Distilled · Local](docs/images/banner.png)

A persistent strategic-reasoning agent built around the
**[Hammerstein framework](https://github.com/rayweiss/hammerstein)**:
a clever-lazy / clever-industrious / stupid-industrious /
stupid-lazy diagnostic for catching misdirected effort in software,
design, and strategy decisions.

This repo ships two artifacts you can use today:

1. **`hp.py`**, a stateful CLI wrapper that adds cross-session
   memory and ambient project-context injection on top of the
   one-shot [hammerstein CLI](https://github.com/rayweiss/hammerstein).
   Production-shaped, ~$0.01/audit.
2. **Hammerstein-7B**, a QLoRA adapter on Qwen2.5-7B-Instruct
   distilled from synthetic teacher outputs. Q4_K_M GGUF on
   HuggingFace; runs on any 8 GB+ Mac via Ollama. Behavior
   cloning, not reasoning training.

The wrapper is the production path. The distilled adapter is the
shareable artifact. They ship independently.

## Origin

The 2026-05-07 hammerstein audit voted "bank" on this proposal: too
unconstrained to ship. The 2026-05-08 design session walked four
pre-flight questions (Q1-Q4) with the hammerstein CLI auditing
each answer. Re-running the audit against the refined scope flipped
the verdict to "proceed with modifications." Every design decision
from that walk lives in [`DESIGN.md`](DESIGN.md).

The pre-flight cost $0.054 in OpenRouter credits across five
hammerstein audits. Zero Anthropic quota.

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

"Persistent" here means continuity of context across audits, not a
daemon, not a scheduler, not a vector store, not background
execution. Q1 of the design walk locked that in.

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
| Phase 1.5 | Precision test on retrieval heuristic | ⚠️ ran. Corpus-id intersection scored 15%; the rare-token filter that replaced it scored 53%, below the 60% gate but enough for Phase 3 dogfood to validate. |
| Phase 2 | Pytest validation | ✅ done — 19/19 passing |
| Phase 3 | Dogfood + auto-enforced gate | ✅ CONTINUE verdict (cost ratio 1.23×, 3/5 last calls had conclusion_changed=true) |
| Phase 4 | Failure-pattern preflight | Deferred — gated on Phase 3 sustained pass |
| Phase 5 | Wargame solitaire opponent | ✅ v0 + v1 (kriegspiel pivot) + v2 (multimodal `hp_vision.py`) shipped 2026-05-08. Photo + Excel OOB + conversational input → Auftragstaktik mission orders via Sonnet 4.6. See [WARGAME-EXTENSION.md](WARGAME-EXTENSION.md). |
| Phase 5.1 | VASSAL integration | Design doc only, [VASSAL-EXTENSION.md](VASSAL-EXTENSION.md). The recommendation: pipe a manual screenshot into the existing `hp_vision.py` (works today, zero new code) and test on real games before building deeper integration. |
| Phase 6 | Local web UI | ✅ v0 shipped 2026-05-08. `hp_web.sh` runs a FastAPI + React/Tailwind dashboard on `127.0.0.1:8765`: Phase-3 verdict card, sortable table of recent calls (audit + wargame), one-click `conclusion_changed` toggle. See [WEB-UI-EXTENSION.md](WEB-UI-EXTENSION.md). |
| **Distillation experiment** | Hammerstein-7B QLoRA adapter + Q4_K_M GGUF | ✅ trained, 4-condition eval passed, GGUF / Ollama-ready 2026-05-08. ADAPTER WINS the prompt ablation by Δ=+0.206; student/gold ratio 1.01. Public at [`huggingface.co/lerugray/hammerstein-7b-lora`](https://huggingface.co/lerugray/hammerstein-7b-lora). Runs on any 8 GB+ Mac: `ollama run hf.co/lerugray/hammerstein-7b-lora:Q4_K_M`. See [HAMMERSTEIN-7B.md](HAMMERSTEIN-7B.md). Total spend ~$3.97 end-to-end. |

## Honest framing

`hp.py` is a **thin wrapper** by design. The framework (system
prompt + corpus + retrieval + few-shot templates) is the IP. The
wrapper adds state. You can swap the base inference model
(Qwen3.6-plus on OpenRouter today) without changing anything that
matters.

Distilling the framework into Hammerstein-7B started as a portfolio
move: "I built a wrapper" reads weaker than "I trained a model,"
even when the wrapper is the better tool. The
[hammerstein-on-itself audit](MODEL-EXPERIMENT.md#hammersteins-scoping-verdict-2026-05-08)
called it explicitly:

> "The FT path wins on signaling ROI even if it loses on capability
> ROI. Frame it as behavior cloning, not reasoning training."

The 4-condition eval cleared the ≥80%-of-gold gate. The adapter beat
the prompt-only ablation by Δ=+0.206 on the same base model, which
means the framework's portability lives in the weights, not just
the system prompt. Both the wrapper and the adapter ship; neither
blocks the other.

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

# Or open the local dashboard (http://127.0.0.1:8765):
./hp_web.sh
```

Requires `OPENROUTER_API_KEY` in env and the
[hammerstein CLI](https://github.com/rayweiss/hammerstein) installed.

## Reproducing the distillation

Everything needed to retrain the Hammerstein-7B adapter and re-run
the eval is in this repo. The synthetic training set
([`tools/distill/data/synthetic-2026-05-08.jsonl`](tools/distill/data/synthetic-2026-05-08.jsonl),
308 pairs, ~1 MB) and the held-out eval set
([`tools/distill/data/eval-set.jsonl`](tools/distill/data/eval-set.jsonl),
40 strategic + 4 forgetting-check prompts) are checked in. The
teacher system prompt used for generation +
ablation-arm conditioning is at
[`tools/distill/data/hammerstein-system-prompt.txt`](tools/distill/data/hammerstein-system-prompt.txt).

```bash
# 1. Cloud setup (RunPod RTX 4090 24 GB, ~$0.50/hr) — see
#    tools/distill/HOWTO-CLOUD.md for the full walk
bash <(curl -sL https://raw.githubusercontent.com/lerugray/hammerstein-model/master/tools/distill/setup_pod.sh)

# 2. Train (~50 min, ~$0.50)
python tools/distill/train.py --model-key qwen-7b --backend unsloth --execute

# 3. Eval — 4 conditions on 40 prompts (~$0.32 for the gold OpenRouter calls)
python tools/distill/eval.py \
    --student-path tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter \
    --vanilla-path unsloth/Qwen2.5-7B-Instruct-bnb-4bit

# 4. (Optional) GGUF + Ollama (~6 min on RTX A5000, ~$0.07)
python tools/distill/convert_gguf.py --quant q4_k_m
```

Hyperparameters, hardware specs, and dataset provenance are detailed
in [HAMMERSTEIN-7B.md](HAMMERSTEIN-7B.md). The full workflow sequence
+ Hammerstein audit-driven gate decisions are in
[tools/distill/README.md](tools/distill/README.md).

## Cost arc

| Stage | Spend |
|---|---|
| Q1-Q4 design walk | $0.04 |
| Phase 1 implementation + dogfood | $0.05 |
| Phase 1.5 precision test | $0.00 (analysis only) |
| Phase 2/3 setup | $0.00 |
| **Total to ship the wrapper** | **~$0.10** |
| Distillation: data gen (308 synthetic pairs) | $2.31 |
| Distillation: training (RunPod RTX 4090, ~50 min) | ~$0.50 |
| Distillation: gold eval (40 OpenRouter calls) | $0.315 |
| Distillation: pod eval (RunPod RTX 4090, ~1 hr) | ~$0.50 |
| Distillation: GGUF conversion (RunPod A5000, ~6 min + dud-pod retry) | ~$0.22 |
| Wargame extension dogfood (text + multimodal) | ~$0.10 |
| Web UI (Phase 6) build | $0 (no inference; local FastAPI + React) |
| **Total end-to-end** | **~$4.05** |
| | |
| Anthropic quota burned by hammerstein | $0 |

## License

License pending (MIT most likely, matching the upstream framework).
The [hammerstein corpus + framework](https://github.com/rayweiss/hammerstein)
has its own license; this repo is downstream tooling.

## The framework, in one paragraph

Kurt von Hammerstein-Equord (Chef der Heeresleitung 1930-1934)
classified officers along two axes: clever/stupid by
lazy/industrious. The dangerous quadrant is **stupid-industrious**:
working hard in the wrong direction with total commitment. The
framework's central claim, applied to software and strategy: that
kind of misdirected commitment is more dangerous than plain
incapability, and the defense is structural (verification gates,
role assignment, legible failure logging) rather than
dispositional (better instructions, more careful execution). This
repo applies the framework to itself: a wrapper that audits its
own use, a precision test that scored its own heuristic at 53%
and forced a pivot, an abandonment gate that can vote ABORT
without asking permission.
