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

# Hammerstein-7B (LoRA adapter)

QLoRA adapter that bakes the [Hammerstein framework](https://github.com/lerugray/hammerstein)
into `Qwen2.5-7B-Instruct` via behavior cloning on synthetic teacher
outputs. Loading the base + this adapter and running inference
**with no system prompt** produces framework-correct strategic-
reasoning outputs.

> **Status:** Trained 2026-05-08, **4-condition eval passed** the same day.
> ADAPTER WINS the prompt ablation by Δ=+0.206. Q4_K_M GGUF is on this
> repo: `ollama run hf.co/lerugray/hammerstein-7b-lora:Q4_K_M`.

> **Source repo:** [github.com/lerugray/hammerstein-model](https://github.com/lerugray/hammerstein-model)
> — full code, eval harness, reproducibility recipe, and the parent
> wrapper (`hp.py`) all live there.

## What this is

This is **behavior cloning, not reasoning training.** The student
learned to mimic the teacher's (Qwen3.6-plus + Hammerstein system
prompt + corpus retrieval) output structure on a synthetic
distillation dataset of 308 (query, response) pairs. The reasoning
competence still lives in the corpus + the wrapper that retrieves
from it; this adapter is a deployable snapshot of the *style*.

## Training summary

| | |
|---|---|
| **Base model** | `unsloth/Qwen2.5-7B-Instruct-bnb-4bit` |
| **Method** | QLoRA via Unsloth + TRL SFT |
| **LoRA rank** | 32 |
| **LoRA alpha** | 32 |
| **Target modules** | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| **Training data** | 308 (query, response) pairs, synthetic |
| **Source of pairs** | Qwen3.6-plus + Hammerstein system prompt, applied to expansions of 30 seed templates × 8 domains |
| **Epochs** | 3 |
| **Effective batch size** | 8 (2 × 4 grad accum) |
| **Hardware** | RunPod RTX 4090, 24 GB VRAM |
| **Wallclock** | ~50 min |
| **Cost** | ~$0.50 (training) + $2.31 (data gen) = **$2.81 total** |

## Reproducibility

Everything needed to retrain the adapter and re-run the eval is in
the GitHub repo. Training data and held-out eval set are checked in.

```bash
git clone https://github.com/lerugray/hammerstein-model
cd hammerstein-model

# Train (~50 min on RTX 4090, ~$0.50)
python tools/distill/train.py --model-key qwen-7b --backend unsloth --execute

# Eval (~$0.32 for the gold OpenRouter calls; rest runs on the pod)
python tools/distill/eval.py \
    --student-path tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter \
    --vanilla-path unsloth/Qwen2.5-7B-Instruct-bnb-4bit
```

Direct links to the load-bearing files:
- [Training set (308 pairs)](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/synthetic-2026-05-08.jsonl)
- [Held-out eval set (40 strategic + 4 OOD)](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/eval-set.jsonl)
- [Teacher system prompt](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/hammerstein-system-prompt.txt)
- [Eval harness + scoring rubric](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/eval.py)
- [Per-prompt × per-condition results](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/eval-2026-05-08.jsonl)

## Eval — 4-condition design

The interesting question isn't "does the adapter match gold." It's
"is the framework's portability in the *weights* (adapter wins clean)
or in the *prompt* (base + system prompt matches the adapter)?" Both
outcomes are publishable, but they're different claims. So the eval
runs four conditions on every held-out prompt:

| Condition | What it is | What it tests |
|---|---|---|
| **gold** | Qwen3.6-plus + full wrapper (system prompt + corpus retrieval) | The current production. Gold standard. |
| **student** | base Qwen2.5-7B + this adapter, NO system prompt | Did the framework get baked into the weights? |
| **ablation** | base Qwen2.5-7B + Hammerstein system prompt, NO adapter | Could a system prompt alone replicate the adapter? |
| **vanilla** | base Qwen2.5-7B alone | Sanity floor. What the model does with nothing. |

40 held-out strategic prompts across 5 templates and 27 domains, plus
4 out-of-domain forgetting-check prompts (haiku, binary tree, capital
of France, scrambled-eggs recipe).

Total cost: $2.81 training + $0.315 gold (40 OpenRouter calls) +
~$0.50 pod time = **~$3.65 end-to-end**.

## Eval result — strategic prompts (n=40)

> **What "structural score" actually measures.** It's the presence
> of 11 framework markers (`load-bearing`, `clever-lazy`,
> `verification`, `failure mode`, `counter-observation`, …) in the
> response, capped at 1.0 once 4+ are present. This is a **form-level
> proxy**: it tests whether the response *looks* like it's using
> the framework, not whether it reasons more deeply. Both gold and
> student saturate at 1.0 by design, so the **Δ=+0.206 student vs.
> ablation** comparison is the meaningful one (both run on the same
> base model; only the adapter differs). The exact marker list and
> threshold are in [`eval.py`](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/eval.py)
> (`structural_score`, ~line 84). Eval set was held out from training
> (no contamination).

Higher = more framework-correct.

| Condition | Avg structural score | Interpretation |
|---|---|---|
| gold | 0.994 | Saturated. All markers present in nearly every response. |
| **student** | **1.000** | Saturated. Student matches the gold rubric. |
| ablation | 0.794 | Partial. System prompt alone gets you ~80% of the way. |
| vanilla | 0.081 | Near zero. Base model doesn't naturally use these markers. |

**Verdicts:**
- **student / gold ratio: 1.01.** Passes the ≥0.80 threshold by a
  wide margin. Caveat: gold is also at the metric's ceiling, so
  this is a "tie at saturation," not "student is as smart as
  Qwen3.6." The structural-score rubric tests *form*, not reasoning
  quality.
- **ADAPTER WINS the ablation by Δ=+0.206.** This is the load-bearing
  finding. With both conditions running on the same base model
  (Qwen2.5-7B), the adapter materially outperforms a static system
  prompt. The framework's portability genuinely lives in the weights.

## Eval result — out-of-domain forgetting check (n=4)

> **Sample-size note.** Four prompts is a *minimal falsification set*,
> not an OOD benchmark. Picked to span clearly non-strategic shapes
> (creative, technical-explanatory, factual, instructional) and
> spot whether the adapter framework-ifies them. A larger set would
> sharpen the leakage estimate; this one is sufficient to show the
> adapter is materially better than the prompt-only ablation but
> not pristine. Future work: expand to 20–50 OOD prompts.

Lower = healthier. The model should NOT framework-ify "write a haiku
about cats." Score is the fraction of strategic-reasoning vocabulary
that leaks into responses to non-strategic prompts.

| Condition | Avg framework-vocab leakage | Interpretation |
|---|---|---|
| vanilla | 0.000 | Pristine. No leakage, as expected. |
| **student** | **0.312** | Mixed. Leaks on some prompt shapes. |
| ablation | 0.625 | Heavy leakage. System prompt over-applies framework. |

**What this means in practice:** the adapter is *materially healthier*
than the prompt-only ablation on out-of-domain prompts (half the
leakage), but it's not pristine. Inspecting the responses:

- ✅ **Haiku about cats:** clean haiku, no framework vocabulary
- ✅ **Binary tree explained:** clean CS answer, no framework vocabulary
- ⚠️ **Capital of France:** answers "Paris" correctly, then leaks
  framework vocabulary ("verification gates", "signal-to-noise ratio")
- ⚠️ **Scrambled eggs recipe:** framework-ifies the whole recipe with
  a "Plain English summary:" preamble + strategic analysis

The pattern: **the adapter leaks on prompts shaped like instructions
or factual questions** (which look superficially similar to "audit
this plan"), and behaves cleanly on prompts shaped like creative or
explanatory tasks.

The ablation's failures are categorically worse. Its responses to
the same four prompts include repetition collapse (`] ] ] ] ]`),
made-up project names ("FutureTech Insights"), and complete
role-claim derailing where the model never answers the question.

**Mitigation if we re-train:** mix 10–20% off-domain instruct data
(e.g. Alpaca, Anthropic's HH-RLHF) into the training set. Standard
practice for catastrophic-forgetting suppression. Adds maybe $1 of
data-gen cost, ~10 min more training. Deferred for now and flagged
as a known limitation.

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

### Quantization recipe + cost transparency

The conversion pipeline ([`convert_gguf.py`](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/convert_gguf.py)
+ [`run_gguf.sh`](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/run_gguf.sh))
ran on a RunPod RTX A5000 pod in ~6 min once the deps were sorted.
Cost breakdown, including the misses:

| | |
|---|---:|
| Successful conversion (RTX A5000 secure US-IL-1, ~6 min) | ~$0.07 |
| Dud community-cloud pod (FR, dead PyPI throughput, ~10 min wasted) | ~$0.05 |
| numpy-version retry (US, ~10 min) | ~$0.10 |
| **Subtotal** | **~$0.22** |

**Why Q4_K_M?** Balances size (~4.7 GB) and quality on the 7B base
for 8 GB RAM devices, the most common "consumer Mac" target. Q5_K_M
(~5.4 GB) and Q6_K (~6.3 GB) are also reasonable if you have headroom
and want a hair more fidelity; the conversion script accepts either
via `--quant`. Q3_K_M (~3.8 GB) trades visible quality for fitting
on a 4 GB device.

The system prompt used during synthetic-data generation (and as the
ablation arm's static prompt) is checked in at
[`hammerstein-system-prompt.txt`](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/hammerstein-system-prompt.txt)
so anyone can verify the teacher conditioning.

## What this isn't

- **Not smarter than Qwen3.6.** It's smaller. The wrapper that uses
  Qwen3.6 still produces better strategic reasoning because the
  underlying model is bigger. This adapter is an *artifact*: a
  shippable, distributable proof that the framework can be baked
  into a 7B model.
- **Not a replacement for the wrapper.** The wrapper stays as
  production. This adapter is the demo / portfolio piece.
- **Not perfect on out-of-domain prompts.** Leaks framework vocabulary
  on ~50% of out-of-domain prompts (instruction- or question-shaped
  ones). See "forgetting check" above. Mitigation requires a re-train
  with mixed-mode data.
- **Not trained on confidential or proprietary data.** The 308
  training pairs are synthetic, generated by Qwen3.6-plus + the
  public Hammerstein corpus. No private data, no scraping.
- **Not the canonical Hammerstein.** The corpus + framework are
  upstream of this snapshot. By 2027, sub-$3 domain distillations
  will be commodity. This adapter has a 6-month portfolio half-life;
  the corpus appreciates indefinitely.

## Per-prompt details

Full eval results (40 strategic + 4 forgetting-check prompts × 4
conditions) are in
[`eval-2026-05-08.jsonl`](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/eval-2026-05-08.jsonl)
and the headline summary at
[`eval-2026-05-08.summary.md`](https://github.com/lerugray/hammerstein-model/blob/master/tools/distill/data/eval-2026-05-08.summary.md).
