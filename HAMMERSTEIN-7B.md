# Hammerstein-7B — Distilled LoRA Adapter

**Status:** Trained 2026-05-08, **4-condition eval passed** the same day.
ADAPTER WINS the prompt ablation by Δ=+0.206 — the framework lives in
the weights, not just in the system prompt. Pushed to HuggingFace at
[`huggingface.co/lerugray/hammerstein-7b-lora`](https://huggingface.co/lerugray/hammerstein-7b-lora).

## What this is

A QLoRA adapter that takes `Qwen2.5-7B-Instruct` (the open base
model) and bakes the [Hammerstein framework](https://github.com/rayweiss/hammerstein)
into its output behavior via fine-tuning. Loading the base + this
adapter and running inference with **no system prompt** produces
framework-correct strategic-reasoning outputs.

This is **behavior cloning, not reasoning training.** The student
learned to mimic the teacher's (Qwen3.6-plus + Hammerstein system
prompt + corpus retrieval) output structure on a synthetic
distillation dataset of 308 (query, response) pairs. The reasoning
competence still lives in the corpus + the wrapper that retrieves
from it; this adapter is a deployable snapshot of the *style*.

## Files

The adapter lives at:
```
tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter/
├── adapter_config.json       # PEFT config
├── adapter_model.safetensors # 323 MB LoRA weights
├── chat_template.jinja       # Qwen2.5 chat format
├── tokenizer.json
├── tokenizer_config.json
└── README.md (model card; mirrored to HF)
```

This directory is gitignored locally (323 MB exceeds GitHub's
100 MB single-file limit). For distribution see "Sharing" below.

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
| **vanilla** | base Qwen2.5-7B alone | Sanity floor — what the model does with nothing. |

40 held-out strategic prompts ([eval-set.jsonl](tools/distill/data/eval-set.jsonl))
across 5 templates and 27 domains, plus 4 out-of-domain
forgetting-check prompts (haiku, binary tree, capital of France,
scrambled-eggs recipe).

Total cost: $2.81 training + $0.315 gold (40 OpenRouter calls) +
~$0.50 pod time = **~$3.65 end-to-end**.

## Eval result — strategic prompts (n=40)

Higher = more framework-correct. Score is the fraction of structural
markers (`load-bearing`, `clever-lazy`, `verification`, `failure mode`,
`counter-observation`, etc.) present in the response, capped at 1.0.

| Condition | Avg structural score | Interpretation |
|---|---|---|
| gold | 0.994 | Saturated — all markers present in nearly every response |
| **student** | **1.000** | Saturated — student matches the gold rubric |
| ablation | 0.794 | Partial — system prompt alone gets you ~80% of the way |
| vanilla | 0.081 | Near zero — base model doesn't naturally use these markers |

**Verdicts:**
- **student / gold ratio: 1.01** — passes the ≥0.80 threshold by a
  wide margin. Caveat: gold is also at the metric's ceiling, so this
  is a "tie at saturation" not "student is as smart as Qwen3.6."
  The structural-score rubric tests *form*, not reasoning quality.
- **ADAPTER WINS the ablation by Δ=+0.206.** This is the load-bearing
  finding. With both conditions running on the same base model
  (Qwen2.5-7B), the adapter materially outperforms a static system
  prompt. The framework's portability genuinely lives in the weights.

## Eval result — out-of-domain forgetting check (n=4)

Lower = healthier. The model should NOT framework-ify "write a haiku
about cats." Score is the fraction of strategic-reasoning vocabulary
that leaks into responses to non-strategic prompts.

| Condition | Avg framework-vocab leakage | Interpretation |
|---|---|---|
| vanilla | 0.000 | Pristine — no leakage, as expected |
| **student** | **0.312** | Mixed — leaks on some prompt shapes |
| ablation | 0.625 | Heavy leakage — system prompt over-applies framework |

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

The ablation's failures are categorically worse — its responses to
the same four prompts include repetition collapse (`] ] ] ] ]`),
made-up project names ("FutureTech Insights"), and complete
role-claim derailing where the model never answers the actual
question.

**Mitigation if we re-train:** mix 10–20% off-domain instruct data
(e.g. Alpaca, Anthropic's HH-RLHF) into the training set. Standard
practice for catastrophic-forgetting suppression. Adds maybe $1 of
data-gen cost, ~10 min more training. Deferred for now — flagging
as known limitation in the v0 model card.

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

# No system prompt — framework is in the weights
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

### Option 3: GGUF + Ollama (deferred)

For local inference on Ray's Mac (8 GB unified memory) or any non-CUDA
device, the adapter needs to be:
1. Merged into the base model
2. Converted to GGUF via llama.cpp's `convert_hf_to_gguf.py`
3. Quantized to Q4_K_M for size
4. Registered with Ollama via [Modelfile.template](tools/distill/Modelfile.template)

This is a follow-up step. The merge + convert needs ~16 GB system
RAM; not viable on the 8 GB Mac without swap. Spin up a RunPod pod
for ~30 min ($0.20) to do the conversion.

## Sharing / portfolio distribution

Pushed to HuggingFace at
[`huggingface.co/lerugray/hammerstein-7b-lora`](https://huggingface.co/lerugray/hammerstein-7b-lora)
via [`tools/distill/hf_push.py`](tools/distill/hf_push.py). The
public-flip gates have all landed:

1. ✅ Full 40-prompt × 4-condition eval (ADAPTER WINS)
2. ✅ Forgetting check ran (mixed result, disclosed in this card)
3. ✅ Model card updated with full eval results

To flip public: `python tools/distill/hf_push.py --public`.

## What this isn't

- **Not smarter than Qwen3.6.** It's smaller. The wrapper that uses
  Qwen3.6 still produces better strategic reasoning because the
  underlying model is bigger. This adapter is a *artifact* — a
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

## Next steps (Ray's call)

- [ ] Flip HuggingFace repo public (one CLI command, reversible)
- [ ] Update top-level [README.md](README.md) status table
- [ ] (Optional) Convert to GGUF + register with Ollama for local
      Mac inference
- [ ] (Optional) Re-train with mixed-mode data to fix out-of-domain
      leakage — would push the forgetting-check score to ~0.05 if
      done right. Cost: ~$1, ~1 hr

## Per-prompt details

Full eval results (40 strategic + 4 forgetting-check prompts × 4
conditions) are in
[`tools/distill/data/eval-2026-05-08.jsonl`](tools/distill/data/eval-2026-05-08.jsonl)
and the headline summary is at
[`tools/distill/data/eval-2026-05-08.summary.md`](tools/distill/data/eval-2026-05-08.summary.md).
