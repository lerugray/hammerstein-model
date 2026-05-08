# Hammerstein Model Experiment — Deep Dive

**Status:** Thought-experiment plan, not yet executed. Awaiting Ray's
go/no-go decision after reading.

**Source:** Ray's 2026-05-08 reframe — "wrapper feels less impressive,
willing to spend some cash, hammerstein advises, I'm final judge."

## The reframe

The wrapper architecture (Phase 1-3 + 1.5) is technically sound but
has a portfolio-signaling weakness: "I built a wrapper around an API"
reads weaker than "I trained a Hammerstein model." Ray's pushback is
honest and worth taking seriously.

**Hammerstein's verdict (`hp --template review-from-different-angle`,
2026-05-08):** wrapper for production, distillation experiment for
signaling. Both ship; neither blocks the other.

> "The FT path wins on signaling ROI even if it loses on capability
> ROI… frame it as behavior cloning. This removes the expectation
> that the 7B will out-reason Qwen3.6 and sets the correct success
> metric: output alignment, not reasoning depth."

The framework is the IP. Fine-tuning bakes the framework into a
distributable static artifact — it doesn't make the system smarter.
That trade is the entire point.

## What "create a model" actually means (four paths)

| Path | Cost | Outcome | Verdict |
|---|---|---|---|
| **Pretrain from scratch** | $10K+ minimum | Custom architecture | ❌ Out — MISSION explicit ban; not low-cost |
| **Continued pretraining** on a base | $500-5K | Base model with Hammerstein-flavored next-token distribution | ❌ Out — still expensive, marginal vs. fine-tuning |
| **Fine-tuning (SFT/QLoRA)** on synthetic Hammerstein data | $25-50 | Distributable model that mimics framework outputs | ✅ Recommended |
| **Retrieval-only** (status quo) | $0 | Wrapper around hosted Qwen3.6 | ✅ Already shipped |

Path 3 is the only one that's both feasible at low cost AND produces
a portfolio-grade artifact ("a model I trained"). That's the
experiment.

## Cost landscape (2026 research-verified)

Numbers below are from current cloud GPU pricing and 2026
fine-tuning guides:

- **RunPod RTX 4090**: $0.34/hr; community cloud $0.29/hr
- **RunPod H100 SXM**: $1.99/hr on-demand
- **Lambda A100 80GB**: $2.49/hr
- **Apple Silicon MLX-LM**: free (uses your hardware), but 8GB
  unified memory is borderline for 7B QLoRA — comfortable for 1-3B
- **Unsloth on RTX 4090**: ~70% less VRAM, 2× faster than vanilla
  LoRA; 7B QLoRA fits in 8-10GB VRAM; full job in <$5 on cloud

For a single distillation experiment:
- **Synthetic data generation** (2K Qwen3.6 teacher outputs at
  $0.01 each on OpenRouter): **~$20**
- **QLoRA training** on cloud RTX 4090 (4-8 hours): **$1.50-3**
- **Eval** (60 OpenRouter calls): **~$0.60**
- **Total cloud-only**: **~$25**
- **Total if local-training works**: **~$20** (just data)

Hard cap: **$100 budget for the entire experiment.** Abandon at $75.

## The recommended path: distillation experiment

Frame: **behavior cloning**, not "training a smarter model." The
student learns to mimic the teacher's output structure. Success
criterion is output alignment, not reasoning depth.

### Architecture

```
Teacher: Qwen3.6-plus + Hammerstein system prompt + corpus retrieval
                 |
                 | (generate 2K synthetic strategic-reasoning outputs)
                 v
         Synthetic dataset
                 |
                 | (QLoRA fine-tune)
                 v
Student: Qwen 2.5 7B (or Llama 3.2 3B) + LoRA adapter
                 |
                 | (merge + quantize)
                 v
       Hammerstein-7B.gguf  ← portfolio artifact
```

### Base model choice

| Base | Size | Mac (8GB) | Cloud | Why |
|---|---|---|---|---|
| **Llama 3.2 3B** | 3B | ✅ MLX-LM 4-bit | $1.50 | Smallest viable; fastest iteration |
| **Qwen 2.5 7B** | 7B | ⚠️ borderline | $3 | Same family as teacher (best behavior cloning) |
| **Phi 4 7B** | 7B | ⚠️ borderline | $3 | Strong reasoning baseline |
| **Gemma 3 7B** | 7B | ⚠️ borderline | $3 | Google's small model |

**Recommended primary**: Qwen 2.5 7B, trained on cloud RTX 4090
($3 + $20 data = $23 total). Same model family as teacher, so
distillation fidelity is highest.

**Fallback if cloud is friction**: Llama 3.2 3B trained locally
via MLX-LM on Mac ($20 data, $0 compute). Smaller artifact but
fully local.

### Tooling (verified current as of 2026-05)

- **[Unsloth](https://unsloth.ai)**: lightning-fast QLoRA, 70% less
  VRAM, 2× faster than vanilla. Industry default for cheap fine-tunes.
- **[MLX-LM](https://github.com/ml-explore/mlx-lm)**: Apple's native
  framework for Apple Silicon. Supports Qwen2, Llama, Mistral, Phi
  fine-tuning natively.
- **[LlamaFactory](https://github.com/hiyouga/LlamaFactory)**: unified
  fine-tuning interface for 100+ models. Heavier than Unsloth but
  more flexible.
- **[llama.cpp](https://github.com/ggerganov/llama.cpp)**: GGUF
  conversion + quantization for the final shippable artifact.

### Data generation strategy

The 65 logged hp/hammerstein calls aren't enough for fine-tuning
(need 1K+ minimum). We generate synthetic strategic-reasoning data
by running Qwen3.6 + Hammerstein system prompt on diverse synthetic
prompts:

1. **Seed prompts** (manual, ~30): real strategic-reasoning queries
   covering audit, scope, worth, next, review-from-different-angle
   templates.
2. **Prompt expansion** (LLM-generated, ~2000): use Qwen3.6 to
   generate variations on the seed prompts (different domains:
   software, business, design, life decisions).
3. **Teacher outputs** (Qwen3.6 + framework, ~2000): each prompt
   produces a (query, response) pair.
4. **Filter for quality**: drop responses that are too short, miss
   the framework structure (no "load-bearing" / "structural fix" /
   "counter-observation" markers), or hallucinate.

Cost: ~$20 in OpenRouter credits (2000 × $0.01).

### Evaluation methodology

A held-out test set of **30-50 strategic-reasoning prompts** never
seen during training. Three runs per prompt:

1. **Vanilla baseline**: bare base model, no framework, no fine-tune
   ("can the base model already do this?")
2. **Fine-tuned student**: trained model, no system prompt
   (framework baked in)
3. **Gold standard**: Qwen3.6 + Hammerstein system prompt (the
   wrapper today)

Scoring (manual, ~1 hour per pass):
- Structural shape: does the output have load-bearing/failure-mode/
  structural-fix/counter-observation markers? (boolean)
- Quality vs. gold: 1-5 scale on whether the response is comparable
- Hallucination rate: % of responses citing things that don't exist
- Catastrophic forgetting check: 5-10 generic tasks (math, writing,
  trivia) — does the fine-tune still handle them?

**Pass criteria (per hammerstein's audit):**
- Fine-tuned scores ≥80% of gold on structural shape
- ≤15% hallucination rate
- No catastrophic forgetting on generic tasks
- Outperforms vanilla base on strategic-reasoning (otherwise the
  fine-tune did nothing)

**Fail handling (per hammerstein's audit):**
- If fail, publish the **failure log itself** as the portfolio
  artifact: "What I learned trying to distill Hammerstein into a
  7B model." Negative results have signaling value.

## Phased plan

| Phase | Hours | Cost | Output |
|---|---|---|---|
| **E0 — Scope confirm** | 0.5 | $0 | Base model picked, eval set drafted |
| **E1 — Eval set + benchmark gold** | 2 | $1 | 30 prompts, gold answers logged |
| **E2 — Synthetic data generation** | 4 | $20 | 2000 (query, response) pairs |
| **E3 — Train QLoRA** | 4-8 | $0-5 | LoRA adapter |
| **E4 — Eval fine-tune** | 2 | $1 | Comparison table |
| **E5 — Decision + ship** | 1 | $0 | Either GGUF artifact or failure log |
| **Total** | 14-18 | $22-27 | Pass/fail + artifact |

Hard ceiling: $100, abandon at $75.

## Hardware assessment

This Mac (running this conversation): Apple A18 Pro, 8 GB unified
memory, Ollama.app installed.

- **Llama 3.2 3B QLoRA**: ✅ feasible locally (~30 min training),
  ~3GB peak memory
- **Qwen 2.5 7B QLoRA**: ⚠️ borderline (5GB model + 2GB training =
  near the 8GB ceiling). Will likely OOM under load.
- **Inference of 7B GGUF after merge**: ✅ works in Ollama
  (4-bit quant fits easily)

Ray's PC: NVIDIA, 8-12 GB VRAM (model unconfirmed — run
`nvidia-smi --query-gpu=name,memory.total --format=csv` on the PC).

The 8-12 GB range bifurcates the recommendation:

- **12 GB+** (e.g., RTX 3060 12GB, 4070 Ti 12GB, 4080, 4090):
  ✅ Qwen 2.5 7B QLoRA fits comfortably with Unsloth. Local training
  is the right path. Total cost: just data ($20).
- **8-10 GB** (e.g., RTX 3060 Ti, 3070, 4060, 4060 Ti 8GB):
  ⚠️ Qwen 7B QLoRA is tight (Unsloth claims 8-10GB minimum but OOM
  is a real risk under load). Two options:
  - Train Llama 3.2 3B locally (safer, smaller artifact)
  - Train Qwen 2.5 7B on rented cloud GPU ($1.50-3 one-shot)

## On cloud GPU subscriptions

Ray asked if a "subscription to virtual GPU services" makes sense.
For a one-shot experiment (this is one-shot), pay-per-hour usually
beats subscription. The math:

| Service | Cost shape | Fit for this experiment |
|---|---|---|
| **Kaggle Notebooks** | Free, 30 hr/week T4/P100 | ✅ Best free option. Enough for 7B QLoRA. Slight friction (Kaggle UI). |
| **Google Colab Pro** | $10/mo, T4/V100 limited | OK if planning multiple runs over a month. |
| **Google Colab Pro+** | $50/mo, A100/V100 | Overkill for one-shot; only sensible if you'll do 5+ runs |
| **RunPod RTX 4090** | $0.34/hr pay-per-use | ✅ Best paid option for one-shot. ~$1.50-3 total. |
| **Lambda Labs A100** | $2.49/hr | More expensive than RunPod; same quality. |
| **vast.ai marketplace** | $0.20-0.40/hr | Cheapest; less reliable hosts. |

**Recommendation:** if your PC has 12GB+, train locally — total cost
is the $20 of synthetic data. If 8-10GB, pick one:
- Free + slightly friction-y: **Kaggle Notebooks**
- Paid + clean: **RunPod RTX 4090** at $1.50-3 one-shot

Either path keeps total under $25.

A monthly subscription only makes sense if you plan to do **multiple
fine-tuning experiments**. For one Hammerstein-7B distillation, no.

## What ships at the end

**Pass case:** A `hammerstein-7b.gguf` (or 3b.gguf) file, ~4-8GB,
runnable in Ollama with `ollama run hammerstein`. Plus a
`HAMMERSTEIN-MODEL.md` writeup describing the process, eval results,
and limitations. Both committed to the public side of this repo
(or a separate `hammerstein-7b` repo for the model artifact).

**Fail case:** A `FAILURE-LOG.md` with the eval table, what didn't
work, what was tried, and the structural lessons. Per hammerstein's
recommendation, this also has portfolio value.

Either way: the wrapper (`hp.py`) stays as production. The model is
demo / artifact / reference implementation.

## Decision points (Ray's call)

These are the non-routine decisions I won't make autonomously:

1. **Greenlight to spend $25-30?** The experiment isn't free. I won't
   fire E2 (data generation, ~$20) without explicit approval.
2. **Base model: Qwen 2.5 7B (cloud) vs. Llama 3.2 3B (Mac local)?**
   Default to 7B-cloud unless you want to keep everything on your
   hardware.
3. **PC GPU spec?** If your PC has an NVIDIA 12GB+ card, we skip
   cloud entirely and save $5. Affects nothing else.
4. **Public release?** If the artifact passes, do you want it on
   HuggingFace under your name, or kept private?

## Why this might fail (counter-frame)

Hammerstein's audit noted: a 7B model fine-tuned on 2K behavior-
cloned outputs from Qwen3.6 will probably *not* match Qwen3.6's
reasoning. The model is smaller; the data is sparse; the framework
is structural rather than purely lexical.

**If the fine-tune fails the 80% gate**, that's data, not
catastrophe. The right move is publishing the failure log and
keeping the wrapper as the only production path. The framework's
value lives in the corpus + system prompt + retrieval — those don't
need a custom model to be useful.

## Open question I need from you

**What's your PC GPU?** (model + VRAM). This determines whether the
training step is $0 (your PC) or $5 (cloud). Cost-irrelevant for the
overall budget but it affects the workflow shape.

If you don't know: open Settings → System → About → Display adapters
on Windows. Or open the System Information / About This Mac / Activity
Monitor on Mac. Or just run `nvidia-smi` in a PC terminal.
