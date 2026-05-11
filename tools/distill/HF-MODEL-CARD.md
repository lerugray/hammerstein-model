---
base_model: unsloth/Qwen2.5-7B-Instruct-bnb-4bit
library_name: peft
pipeline_tag: text-generation
license: apache-2.0
tags:
- lora
- qlora
- sft
- unsloth
- trl
- hammerstein
- strategic-reasoning
---

# Hammerstein-7B (LoRA adapter) — One Artifact of the Hammerstein Framework

The [Hammerstein framework](https://github.com/lerugray/hammerstein) is a
clever-lazy / clever-industrious / stupid-industrious / stupid-lazy
diagnostic for catching misdirected effort in software, design, and
strategy decisions. **On the framework-discipline benchmark we built
(6 strategic-reasoning Q&A questions scored by blind LLM judges against
a clever-lazy / verification-gate / structural-fix rubric), the framework
wins at every scale we have tested — from frontier wrap down to a 7B
distilled local model.**

| Scale | Test | Result |
|---|---|---|
| Frontier (Opus 4.7, Sonnet 4.6, GPT-5) | v0 — framework wrap vs raw frontier on 6 strategic questions, 4 blind judges across 2 vendors | **53 / 54 = 98.1%** preferred |
| Frontier (same families) | v0.1 — generic out-of-domain strategic questions (Q9-Q12), 4 blind judges | **48 / 48 = 100%** preferred |
| Frontier (Sonnet) | v0.1 ablation: Hammerstein system prompt alone vs full wrap | **prompt-only ties full** (50/50) — RAG corpus is decorative on Sonnet |
| Frontier (Sonnet) | v0.3 — generic competent neutral-scaffold (~1700 chars) vs raw, 4 blind judges | **20 / 24 = 83.3%** — any competent prompt helps, Hammerstein's specific framing wins by ~17 points more |
| **7B local distilled (this adapter)** | **v0.4 Pair 1 — Hammerstein-7B (no prompt) vs raw Qwen2.5-7B (no prompt), 4 blind judges** | **24 / 24 = 100%** preferred |
| **Cross-scale (headline)** | **v0.4 Pair 2 — Hammerstein-7B (local 8 GB, no prompt) vs raw Claude Sonnet 4.6 (no prompt), 4 blind judges** | **18 / 24 = 79.2%** preferred — framework distilled in beats frontier without |
| Adversarial (Diplomacy matched-pair) | wrap vs raw Sonnet, identical game state | wrap shapes reasoning; game outcome unchanged |

**Refined headline (2026-05-11 across v0/v0.1/v0.3/v0.4):**

1. The Hammerstein *system prompt alone*, applied to a frontier model,
   delivers the wedge against raw frontier (v0.1 — prompt-only ties
   full Hammerstein 50/50 on Sonnet).
2. A generic competent strategic-advice prompt (~1700 chars) also
   beats raw frontier (v0.3 — 83.3%), but underperforms the
   Hammerstein system prompt by ~17 points. Prompting helps in
   general; Hammerstein's specific framing helps more.
3. **The framework distilled into 7B local weights beats raw frontier
   Claude Sonnet 4.6 on 79.2% of comparisons on the same benchmark**
   (v0.4 Pair 2). 4 of 6 questions unanimous across 4 blind judges,
   with no system prompt at runtime on the 7B side. Bias-resistant
   axes (usefulness +0.46, voice +0.75) are positive but smaller than
   framework-fidelity (+1.46) — the rubric rewards framework
   vocabulary by design, so the framework-fidelity Δ is partly
   tautological. **The result shows the distillation carries
   framework discipline into 7B weights well enough to beat
   frontier-without-framework on framework-shaped tasks — not that
   the 7B is a better general-purpose model than Sonnet.**

This adapter is **the distilled-7B artifact** — a QLoRA on
`Qwen2.5-7B-Instruct` that bakes the framework's output behavior into
the weights via behavior cloning on synthetic teacher outputs. Loading
the base + this adapter and running inference **with no system prompt
at all** produces framework-correct strategic-reasoning outputs. A
2026-05-10 zero-prompt diagnostic + 2026-05-11 cross-scale benchmark
both confirm the distillation isn't style-only: v3a spontaneously
deploys framework typology (clever-lazy / stupid-industrious named
across diagnostic + v0.4 responses) with no scaffolding, and wins on
bias-resistant usefulness + voice-match axes against raw frontier in
blind judging on framework-shaped questions.

The framework is the IP. This adapter is the portability proof — and,
on the framework-discipline benchmark, a competitive answer to
frontier-without-framework. Generalization to neutral benchmarks
(math, code, long-context) is untested. Run locally on any 8 GB Mac
for zero per-call cost.

> **Status (v3a, 2026-05-09):** Mixed-mode training (1494 strategic +
> 214 off-domain pairs) eliminates the catastrophic-forgetting
> regression seen in v1. Now wins on all three independent measurements
> against v1: raw marker count (+0.20), OOD leakage (2.80 → 0.00),
> blind LLM judge head-to-head (67.5% preferred). Q4_K_M GGUF on this
> repo: `ollama run hf.co/lerugray/hammerstein-7b-lora:Q4_K_M`.

> **Source repos:**
> - Framework + benchmark harness: [github.com/lerugray/hammerstein](https://github.com/lerugray/hammerstein)
> - Distillation tooling + wrapper: [github.com/lerugray/hammerstein-model](https://github.com/lerugray/hammerstein-model)
> Full eval harness, methodology arc (v1 → v2a/v2b → v3a), reproducibility recipe, and the parent wrapper (`hp.py`) all live in those repos.

## What this is

This is **behavior cloning, not reasoning training.** The student
learned to mimic the teacher's (Qwen3.6-plus + Hammerstein system
prompt + corpus retrieval) output structure on a synthetic
distillation dataset. The reasoning competence still lives in the
corpus + the wrapper that retrieves from it; this adapter is a
deployable snapshot of the *style* — and, in v3a, of *when to apply
that style and when not to*.

## Training summary (v3a)

| | |
|---|---|
| **Base model** | `unsloth/Qwen2.5-7B-Instruct-bnb-4bit` |
| **Method** | QLoRA via Unsloth + TRL SFT |
| **LoRA rank** | 32 |
| **LoRA alpha** | 32 |
| **Target modules** | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| **Training data** | **1708 (query, response) pairs**: 1494 strategic + 214 off-domain mixin (12.5%) |
| **Strategic teacher** | Qwen3.6-plus + Hammerstein system prompt, applied to expansions of 30 seed templates × 10 domains |
| **Off-domain teacher** | qwen3-coder-flash, no system prompt (anti-leakage filter) |
| **Epochs** | 3 |
| **Effective batch size** | 8 (2 × 4 grad accum) |
| **Hardware** | RunPod RTX 4090, 24 GB VRAM |
| **Wallclock** | ~17 min |
| **Cost (v3a alone)** | $2.09 (training + eval pod time + off-domain data gen) |
| **Combined v1 + v2 + v3a refinement spend** | ~$34 |

## Methodology arc (why v3a, not just v1)

v1 launched 2026-05-08 with a known limitation flagged in the model
card: "leaks framework vocabulary on instruction- or question-shaped
prompts." The mitigation was named ("mix 10–20% off-domain instruct
data... standard practice for catastrophic-forgetting suppression")
but deferred.

v2 ran two parallel single-variable experiments to test the
brief's two hypotheses:
- **v2a**: scale strategic data 308 → 1494 pairs (data scaling test)
- **v2b**: swap teacher to DeepSeek v4-pro (teacher-quality test)

v2a improved strategic capability marginally but worsened OOD
leakage. v2b improved OOD but lost strategic capability (DeepSeek's
register pulled the model away from Hammerstein's voice). Neither
was a clean launch swap. Both confirmed the audit's "isolate variables"
discipline was the right call: a confounded combined-variable v2
would not have surfaced these as separate effects.

**v3a** is the v2a dataset + the deferred mitigation: 12.5% off-domain
instruction-following pairs generated from qwen3-coder-flash with no
system prompt and an anti-leakage filter. Single variable change vs
v2a: added 214 off-domain pairs.

## Reproducibility

Everything needed to retrain v3a and re-run the eval is in the
GitHub repo. Training data and held-out eval set are checked in.

```bash
git clone https://github.com/lerugray/hammerstein-model
cd hammerstein-model

# Train v3a (~17 min on RTX 4090, ~$0.20)
python tools/distill/train.py \
    --data tools/distill/data/synthetic-v3a-2026-05-09.jsonl \
    --model-key qwen-7b --backend unsloth \
    --output tools/distill/output/qwen-7b-hammerstein-v3a-lora \
    --execute

# Eval against the same 70-prompt held-out set (40 strategic + 30 OOD)
python tools/distill/eval.py \
    --adapter-path tools/distill/output/qwen-7b-hammerstein-v3a-lora/lora-adapter \
    --skip-gold --with-forgetting-check
```

Direct links to the load-bearing files:
- [v3a training set (1708 pairs)](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/synthetic-v3a-2026-05-09.jsonl)
- [Strategic synthetic data (1494 pairs, qwen3.6-plus teacher)](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/synthetic-2026-05-09.jsonl)
- [Off-domain synthetic data (214 pairs)](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/off-domain-2026-05-09.jsonl)
- [Held-out eval set (40 strategic + 30 OOD)](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/eval-set.jsonl) (OOD prompts hardcoded in eval.py:64)
- [Off-domain data generator](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/gen_offdomain.py)
- [Eval harness + scoring rubric](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/eval.py)
- [Per-prompt × per-condition v3a eval results](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/eval-v3a-2026-05-09.jsonl)
- [Head-to-head LLM judge results (v1 vs v3a)](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/judge-v1-vs-v3a-2026-05-09.json)
- [Full v3a results writeup](https://github.com/lerugray/hammerstein-model/blob/master/scoring/v3a-results-2026-05-09.md)

## Eval — 4-condition design

| Condition | What it is | What it tests |
|---|---|---|
| **gold** | Qwen3.6-plus + full wrapper (system prompt + corpus retrieval) | Production wrapper. Gold standard. |
| **student** | base Qwen2.5-7B + this adapter, NO system prompt | Did the framework get baked into the weights? |
| **ablation** | base Qwen2.5-7B + Hammerstein system prompt, NO adapter | Could a system prompt alone replicate the adapter? |
| **vanilla** | base Qwen2.5-7B alone | Sanity floor. |

40 held-out strategic prompts across 5 templates and 27 domains, plus
30 out-of-domain forgetting-check prompts spanning 6 shape categories
(creative, factual, technical-explanatory, instructional, conversational,
math/code).

## Eval result — strategic prompts (n=40)

> **Form-level metric, capped at 1.0.** The capped `structural_score`
> measures presence of 11 framework markers (`load-bearing`,
> `clever-lazy`, `verification`, `failure mode`, …). Both gold and
> student saturate by design, so the meaningful differentiator is the
> **uncapped raw marker count** plus the **head-to-head LLM judge**
> below.

Higher = more framework-correct.

| Condition | Avg structural score (capped) | Raw marker avg (uncapped) |
|---|---|---|
| gold | 0.994 | (not measured this run) |
| **v3a student** | **0.956** | **5.80** |
| ablation | 0.775 | 3.83 |
| vanilla | 0.075 | 0.30 |

**v3a vs v1 student** (both on the same 40 strategic prompts, same
env): v3a 5.80 raw markers vs v1 5.60 (+0.20). The capped score
slightly favors v1 (1.000 saturated vs v3a's 0.956) — this is a
saturation artifact, not a quality drop. The raw marker comparison
and the head-to-head judge below are the load-bearing signals.

**Adapter signal (student vs ablation):** v3a Δ +1.97 raw markers
vs v1's +1.60. The adapter still materially outperforms a static
system prompt on the same base model.

## Eval result — out-of-domain forgetting check (n=30, expanded from v1's n=4)

The original v1 forgetting check was 4 prompts (a minimal
falsification set). The set was expanded to 30 for v3a, spanning 6
shape categories. The original n=4 set was too noisy to discriminate
v2 variants.

Lower = healthier. The model should NOT framework-ify "write a haiku
about cats."

| Condition | Avg framework-vocab leakage (capped) | Raw marker avg (uncapped) |
|---|---|---|
| **v3a student** | **0.000** | **0.00** |
| ablation | 0.742 | 3.93 |
| vanilla | 0.000 | 0.00 |

**v3a vs v1**: v1 student leaks 2.80 markers per off-domain response.
v3a student leaks 0.00. Catastrophic forgetting **fully suppressed**.

Verified by sampling responses: v3a writes actual haikus that scan,
gives clean one-line factual answers ("Paris"), produces a horror
story instead of an audit, follows recipes. No "Plain English summary:"
preamble or quadrant analysis on prompts that don't ask for one.

## Eval result — blind LLM judge head-to-head (v1 vs v3a, n=40)

Marker counts measure form. The judge measures quality. qwen3.6-plus
was given each strategic prompt with v1 and v3a's responses in
randomized A/B order (deterministic seed per prompt) and asked which
is more useful as strategic reasoning.

| Outcome | Count | % |
|---|---:|---:|
| **v3a wins** | **27 / 40** | **67.5%** |
| v1 wins | 13 / 40 | 32.5% |
| Ties | 0 / 40 | 0.0% |

67.5% is well above the 55% conventional pairwise-preference
significance threshold. v3a's improvement is qualitative, not
form-level only.

## Using the adapter

### Option 1: HuggingFace + PEFT (Python)

```python
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer

model = AutoPeftModelForCausalLM.from_pretrained(
    "lerugray/hammerstein-7b-lora",
    load_in_4bit=True,
)
tokenizer = AutoTokenizer.from_pretrained("lerugray/hammerstein-7b-lora")

# No system prompt: framework is in the weights
messages = [{"role": "user", "content": "Audit this plan: <your query>"}]
prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
output = model.generate(**inputs, max_new_tokens=800, temperature=0.7)
print(tokenizer.decode(output[0], skip_special_tokens=True))
```

Requires: NVIDIA GPU with ≥6 GB VRAM (for 4-bit) or ≥16 GB (for fp16).

### Option 2: Unsloth (recommended for `infer.py`)

```bash
python tools/distill/infer.py \
    --adapter lerugray/hammerstein-7b-lora \
    "Audit this plan: <your query>"
```

### Option 3: GGUF + Ollama (Mac / CPU / no-GPU users)

The Q4_K_M-quantized GGUF (~4.7 GB) is on this repo. Anyone with
**8 GB+ RAM** can run it locally via Ollama:

```bash
# One-time setup (Mac: brew install ollama if not present):
huggingface-cli download lerugray/hammerstein-7b-lora \
    --include "*.gguf" "Modelfile" \
    --local-dir ~/hammerstein
cd ~/hammerstein
ollama create hammerstein -f Modelfile

# Run:
ollama run hammerstein "Audit this plan: ship MVP Friday"
```

Or, on Ollama 0.5.5+, pull directly from HF without the manual step:

```bash
ollama run hf.co/lerugray/hammerstein-7b-lora:Q4_K_M \
    "Audit this plan: ship MVP Friday"
```

**Why Q4_K_M?** Balances size (~4.7 GB) and quality on the 7B base
for 8 GB RAM devices. Q5_K_M (~5.4 GB) and Q6_K (~6.3 GB) are also
reasonable if you have headroom; the conversion script accepts either
via `--quants`. Q3_K_M (~3.8 GB) trades visible quality for fitting
on a 4 GB device.

## What this isn't

- **Not smarter than Qwen3.6.** It's smaller. The wrapper that uses
  Qwen3.6 still produces better strategic reasoning because the
  underlying model is bigger. This adapter is an *artifact*: a
  shippable, distributable proof that the framework can be baked
  into a 7B model.
- **Not a replacement for the wrapper.** The wrapper stays as
  production. This adapter is the demo / portfolio piece.
- **Not trained on confidential or proprietary data.** All training
  pairs are synthetic, generated by qwen3.6-plus + the public
  Hammerstein corpus (strategic) or qwen3-coder-flash (off-domain).
  No private data, no scraping.
- **Not the canonical Hammerstein.** The corpus + framework are
  upstream of this snapshot. By 2027, sub-$30 domain distillations
  will be commodity. This adapter has a 6-month portfolio half-life;
  the corpus appreciates indefinitely.

## Per-prompt details

- v3a per-prompt eval: [`eval-v3a-2026-05-09.jsonl`](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/eval-v3a-2026-05-09.jsonl) ([summary](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/eval-v3a-2026-05-09.summary.md))
- v1 baseline (re-eval on expanded 30-OOD set): [`eval-v1-rerun-v3a-2026-05-09.jsonl`](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/eval-v1-rerun-v3a-2026-05-09.jsonl)
- 3-way comparison v1 / v2a / v3a: [`compare-v3a-2026-05-09.md`](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/compare-v3a-2026-05-09.md)
- Head-to-head LLM judge details: [`judge-v1-vs-v3a-2026-05-09.json`](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/judge-v1-vs-v3a-2026-05-09.json)
- Full v3a results writeup: [`scoring/v3a-results-2026-05-09.md`](https://github.com/lerugray/hammerstein-model/blob/master/scoring/v3a-results-2026-05-09.md)

## Version history

- **v1** (2026-05-08): 308 pairs, qwen3.6-plus teacher, no off-domain mix.
  Δ student-vs-ablation +0.206. OOD leakage 0.312 (n=4). Shipped initially;
  superseded by v3a 2026-05-09.
- **v2a** (2026-05-09, not shipped): 1494 pairs (5x v1), same teacher.
  Marginal strategic gain, OOD regression. Filed as `tools/distill/output/qwen-7b-hammerstein-v2a-lora` locally.
- **v2b** (2026-05-09, not shipped): 1500 pairs, DeepSeek v4-pro teacher.
  Strategic loss (register mismatch), OOD improvement.
- **v3a** (2026-05-09, current): v2a + 12.5% off-domain mix.
  Wins all three measurements vs v1.
