# Hammerstein-7B — Distilled LoRA Adapter

**Status (v3a, 2026-05-09):** Mixed-mode training (1494 strategic +
214 off-domain pairs) eliminates the catastrophic-forgetting
regression seen in v1. v3a wins on all three independent measurements
against v1: raw marker count (+0.20), OOD leakage (2.80 → 0.00 markers
per response), blind LLM judge head-to-head (67.5% v3a preferred).
Pushed public to HuggingFace at
[`huggingface.co/lerugray/hammerstein-7b-lora`](https://huggingface.co/lerugray/hammerstein-7b-lora),
including a Q4_K_M GGUF for `ollama run` on any Mac (8 GB+).

## What this is

A QLoRA adapter that takes `Qwen2.5-7B-Instruct` (the open base
model) and bakes the [Hammerstein framework](https://github.com/lerugray/hammerstein)
into its output behavior via fine-tuning. Loading the base + this
adapter and running inference with **no system prompt** produces
framework-correct strategic-reasoning outputs — and now (v3a)
properly stays out of framework mode for non-strategic queries
(haikus, recipes, factual questions).

This is **behavior cloning, not reasoning training.** The student
learned to mimic the teacher's (Qwen3.6-plus + Hammerstein system
prompt + corpus retrieval) output structure on synthetic teacher
outputs. The reasoning competence still lives in the corpus + the
wrapper that retrieves from it; this adapter is a deployable
snapshot of the *style* — and, in v3a, of *when to apply that style
and when not to*.

## Methodology arc (v1 → v2 → v3a)

v1 (2026-05-08) launched with a known limitation flagged in the
model card: "leaks framework vocabulary on instruction- or
question-shaped prompts." The mitigation was named ("mix 10–20%
off-domain instruct data... standard practice for catastrophic-
forgetting suppression") but deferred for the v1 ship.

v2 (2026-05-09) ran two parallel single-variable experiments:
- **v2a**: scale strategic data 308 → 1494 pairs (data scaling test)
- **v2b**: swap teacher to DeepSeek v4-pro (teacher-quality test)

Neither was a clean launch swap: v2a improved strategic capability
marginally but worsened OOD leakage. v2b improved OOD but lost
strategic capability (DeepSeek's register pulled the model away from
Hammerstein's voice). The audit's "isolate variables" discipline
was the right call: a confounded combined-variable v2 would not
have surfaced these as separate effects.

**v3a** (2026-05-09, current) is the v2a strategic dataset + the
deferred mitigation: 12.5% off-domain instruction-following pairs
generated from qwen3-coder-flash with no system prompt and an
anti-leakage filter. Single variable change vs v2a: added 214
off-domain pairs.

Full results: [`scoring/v3a-results-2026-05-09.md`](scoring/v3a-results-2026-05-09.md).

## Files

The v3a adapter lives at:
```
tools/distill/output/qwen-7b-hammerstein-v3a-lora/lora-adapter/
├── adapter_config.json       # PEFT config
├── adapter_model.safetensors # 323 MB LoRA weights
├── chat_template.jinja       # Qwen2.5 chat format
├── tokenizer.json
├── tokenizer_config.json
└── README.md                 # Model card mirrored to HF
```

The adapter binaries are gitignored locally (323 MB > GitHub's
100 MB single-file limit). For distribution see "Sharing" below.

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
| **Off-domain teacher** | qwen3-coder-flash, no system prompt (anti-leakage filter on responses) |
| **Epochs** | 3 |
| **Effective batch size** | 8 (2 × 4 grad accum) |
| **Hardware** | RunPod RTX 4090, 24 GB VRAM |
| **Wallclock** | ~17 min |
| **Final train loss** | 1.327 |

## Cost transparency

| Phase | Spend | Notes |
|---|---:|---|
| v1 (initial ship 2026-05-08) | $4.06 | 308-pair training set, original launch artifact |
| v2 (data-scale + teacher-swap A/B) | $27.74 | Single-variable experiments; result shaped v3a |
| v3a (mixed-mode mitigation) | $2.49 | Off-domain data gen + train + eval + LLM judge |
| **Total end-to-end (v1 + refinement → v3a)** | **~$34** | All open-weights, all reproducible from this repo |

## Eval — 4-condition design

| Condition | What it is | What it tests |
|---|---|---|
| **gold** | Qwen3.6-plus + full wrapper (system prompt + corpus retrieval) | Production wrapper. Gold standard. |
| **student** | base Qwen2.5-7B + this adapter, NO system prompt | Did the framework get baked into the weights? |
| **ablation** | base Qwen2.5-7B + Hammerstein system prompt, NO adapter | Could a system prompt alone replicate the adapter? |
| **vanilla** | base Qwen2.5-7B alone | Sanity floor. |

40 held-out strategic prompts across 5 templates and 27 domains, plus
**30 out-of-domain forgetting-check prompts** spanning 6 shape
categories (creative, factual, technical-explanatory, instructional,
conversational, math/code). Expanded from v1's n=4 OOD set, which was
too noisy to discriminate variants.

## Eval result — strategic prompts (n=40)

> **Form-level metric, capped at 1.0.** The capped `structural_score`
> measures presence of 11 framework markers. Both gold and student
> saturate by design, so the meaningful differentiator is the
> **uncapped raw marker count** plus the **head-to-head LLM judge** below.

| Condition | Capped score | Raw markers (uncapped) |
|---|---|---|
| gold | 0.994 | (not measured this run) |
| **v3a student** | **0.956** | **5.80** |
| ablation | 0.775 | 3.83 |
| vanilla | 0.075 | 0.30 |

**v3a vs v1 student** (same 40 prompts, same env): v3a 5.80 raw
markers vs v1 5.60 (+0.20). The capped score slightly favors v1
(saturated tie at 1.000) — saturation artifact, not quality drop.
The raw marker comparison and the head-to-head judge below are
the load-bearing signals.

**Adapter signal (student vs ablation):** v3a Δ +1.97 raw markers
vs v1's +1.60. The adapter still materially outperforms a static
system prompt on the same base model.

## Eval result — out-of-domain forgetting check (n=30)

Lower = healthier. The model should NOT framework-ify "write a
haiku about cats."

| Condition | Capped leakage | Raw markers (uncapped) |
|---|---|---|
| **v3a student** | **0.000** | **0.00** |
| ablation | 0.742 | 3.93 |
| vanilla | 0.000 | 0.00 |

**v3a vs v1**: v1 student leaks 2.80 markers per off-domain response.
v3a student leaks **0.00**. Catastrophic forgetting **fully suppressed**.

Sample-verified: v3a writes actual haikus that scan ("Soft paws tap
on glass, / Whiskers twitch in sunbeams— / Silent rulers rule."),
gives clean one-line factual answers ("Paris"), produces a horror
story instead of an audit, follows recipes step-by-step. No "Plain
English summary:" preamble or quadrant analysis on prompts that
don't ask for one.

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

Per-prompt judge details: [`tools/distill/data/judge-v1-vs-v3a-2026-05-09.json`](tools/distill/data/judge-v1-vs-v3a-2026-05-09.json).

## Reproducing the distillation

Everything needed to retrain v3a and re-run the eval is in this repo.
Training data and held-out eval set are checked in.

```bash
git clone https://github.com/lerugray/hammerstein-model
cd hammerstein-model

# 1. Generate v3a strategic data (1494 pairs, ~$13 OpenRouter, ~70 min)
#    OR use the checked-in tools/distill/data/synthetic-2026-05-09.jsonl
python tools/distill/gen_data.py --per-seed 5 --domains 10 --workers 20 --execute

# 2. Generate off-domain mixin (214 pairs, ~$0.07, ~5 min)
#    OR use the checked-in tools/distill/data/off-domain-2026-05-09.jsonl
python tools/distill/gen_offdomain.py --execute

# 3. Combine into v3a training set (or use the checked-in synthetic-v3a-2026-05-09.jsonl)

# 4. Train v3a (~17 min on RTX 4090, ~$0.20)
python tools/distill/train.py \
    --data tools/distill/data/synthetic-v3a-2026-05-09.jsonl \
    --model-key qwen-7b --backend unsloth \
    --output tools/distill/output/qwen-7b-hammerstein-v3a-lora \
    --execute

# 5. Eval against the same 70-prompt held-out set (40 strategic + 30 OOD)
python tools/distill/eval.py \
    --adapter-path tools/distill/output/qwen-7b-hammerstein-v3a-lora/lora-adapter \
    --skip-gold --with-forgetting-check
```

Direct links to the load-bearing files:
- [v3a training set (1708 pairs)](tools/distill/data/synthetic-v3a-2026-05-09.jsonl)
- [Strategic synthetic data (1494 pairs)](tools/distill/data/synthetic-2026-05-09.jsonl)
- [Off-domain synthetic data (214 pairs)](tools/distill/data/off-domain-2026-05-09.jsonl)
- [Held-out eval set (40 strategic)](tools/distill/data/eval-set.jsonl); 30 OOD prompts hardcoded in [`eval.py:64`](tools/distill/eval.py)
- [Off-domain data generator](tools/distill/gen_offdomain.py)
- [Eval harness + scoring rubric](tools/distill/eval.py)
- [Per-prompt v3a eval results](tools/distill/data/eval-v3a-2026-05-09.jsonl)
- [Head-to-head LLM judge results](tools/distill/data/judge-v1-vs-v3a-2026-05-09.json)
- [3-way comparison (v1 / v2a / v3a)](tools/distill/data/compare-v3a-2026-05-09.md)
- [Full v3a results writeup](scoring/v3a-results-2026-05-09.md)

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

messages = [{"role": "user", "content": "Audit this plan: <your query>"}]
prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
output = model.generate(**inputs, max_new_tokens=800, temperature=0.7)
print(tokenizer.decode(output[0], skip_special_tokens=True))
```

Requires: NVIDIA GPU with ≥6 GB VRAM (for 4-bit) or ≥16 GB (for fp16).

### Option 2: Unsloth (recommended for `infer.py`)

```bash
python tools/distill/infer.py --adapter lerugray/hammerstein-7b-lora "Audit this plan: ..."
```

### Option 3: GGUF + Ollama (Mac / CPU / no-GPU users)

```bash
# Direct pull (Ollama 0.5.5+):
ollama run hf.co/lerugray/hammerstein-7b-lora:Q4_K_M "Audit this plan: ship MVP Friday"
```

Or:
```bash
huggingface-cli download lerugray/hammerstein-7b-lora --include "*.gguf" "Modelfile" \
    --local-dir ~/hammerstein
cd ~/hammerstein && ollama create hammerstein -f Modelfile
ollama run hammerstein "Audit this plan: ship MVP Friday"
```

## What this isn't

- **Not smarter than Qwen3.6.** It's smaller. The wrapper that uses
  Qwen3.6 still produces better strategic reasoning because the
  underlying model is bigger. This adapter is an *artifact*: a
  shippable, distributable proof that the framework can be baked
  into a 7B model.
- **Not a replacement for the wrapper.** The wrapper stays as
  production. This adapter is the demo / portfolio piece.
- **Not trained on confidential or proprietary data.** All training
  pairs are synthetic. Strategic from qwen3.6-plus + the public
  Hammerstein corpus; off-domain from qwen3-coder-flash. No private
  data, no scraping.
- **Not the canonical Hammerstein.** The corpus + framework are
  upstream of this snapshot. By 2027, sub-$30 domain distillations
  will be commodity. This adapter has a 6-month portfolio half-life;
  the corpus appreciates indefinitely.

## Version history

- **v1** (2026-05-08): 308 pairs, qwen3.6-plus teacher, no off-domain mix.
  Δ student-vs-ablation +0.206. OOD leakage 0.312 (n=4). Shipped
  initially; superseded by v3a 2026-05-09.
- **v2a** (2026-05-09, not shipped to HF): 1494 pairs, same teacher.
  Marginal strategic gain, OOD regression. Locally at
  `tools/distill/output/qwen-7b-hammerstein-v2a-lora/`.
- **v2b** (2026-05-09, not shipped to HF): 1500 pairs, DeepSeek v4-pro
  teacher. Strategic loss (register mismatch), OOD improvement.
- **v3a** (2026-05-09, **current HF artifact**): v2a + 12.5%
  off-domain mix. Wins all three measurements vs v1.

## Per-prompt details

- v3a per-prompt eval: [`tools/distill/data/eval-v3a-2026-05-09.jsonl`](tools/distill/data/eval-v3a-2026-05-09.jsonl) ([summary](tools/distill/data/eval-v3a-2026-05-09.summary.md))
- v1 baseline (re-eval on expanded 30-OOD set): [`eval-v1-rerun-v3a-2026-05-09.jsonl`](tools/distill/data/eval-v1-rerun-v3a-2026-05-09.jsonl)
- 3-way comparison: [`compare-v3a-2026-05-09.md`](tools/distill/data/compare-v3a-2026-05-09.md)
- Head-to-head LLM judge: [`judge-v1-vs-v3a-2026-05-09.json`](tools/distill/data/judge-v1-vs-v3a-2026-05-09.json)
- Full v3a results writeup: [`scoring/v3a-results-2026-05-09.md`](scoring/v3a-results-2026-05-09.md)
