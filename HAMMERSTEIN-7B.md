# Hammerstein-7B — Distilled LoRA Adapter

**Status:** Trained 2026-05-08, 3-prompt spot-check passed, pushed to
HuggingFace as private at `huggingface.co/lerugray/hammerstein-7b-lora`.
Full 40-prompt eval + base+sysprompt ablation + dedicated forgetting
check are pending — not yet a defensible portfolio claim.

## What this is

A QLoRA adapter that takes `Qwen2.5-7B-Instruct` (the open base
model) and bakes the [Hammerstein framework](https://github.com/rayweiss/hammerstein)
into its output behavior via fine-tuning. Loading the base + this
adapter and running inference with **no system prompt** still
produces framework-correct strategic-reasoning outputs.

This is **behavior cloning**, not reasoning training. The student
learned to mimic the teacher's (Qwen3.6-plus + Hammerstein system
prompt + corpus retrieval) output structure on a synthetic
distillation dataset.

## Files

The adapter lives at:
```
tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter/
├── adapter_config.json       # PEFT config
├── adapter_model.safetensors # 323 MB LoRA weights
├── chat_template.jinja       # Qwen2.5 chat format
├── tokenizer.json
├── tokenizer_config.json
└── README.md (v0 model card; mirrored to HF)
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

## Eval result (2026-05-08 spot-check)

3 prompts from the held-out [eval-set.jsonl](tools/distill/data/eval-set.jsonl)
were run through the trained model with NO system prompt. All three
produced framework-correct outputs:

**Prompt 1** (audit-this-plan / saas-startup): "Audit this plan: ship
an MVP of my SaaS to 5 beta users this Friday before adding payment
integration."
- ✅ "Plain English summary:" preamble
- ✅ Quadrant identified: clever-industrious with stupid-industrious risk
- ✅ Failure modes section (4 named items)
- ✅ Verification gates as Booleans
- ✅ Structural-fix candidates (decouple validation from monetization)
- ✅ Explicit recommendation
- ✅ Counter-observation

**Prompt 2** (audit-this-plan / infrastructure): "Audit this plan:
switch our 50K-row Postgres database to MongoDB to 'scale better'
before our Series A."
- ✅ All framework markers present
- ✅ Domain-correct reasoning (50k rows is trivial for PostgreSQL,
  ACID vs eventual consistency, sharding overhead)
- ✅ Concrete verdict: "Don't ship as planned"

**Prompt 3** (audit-this-plan / frontend): "Audit this plan: spend 2
weeks rewriting our React UI in Svelte to 'improve performance' on
a stable production app."
- ✅ All framework markers present
- ✅ Domain-correct reasoning (Web Vitals/Lighthouse profiling first,
  framework choice is rarely the bottleneck)
- ✅ Concrete verdict + falsification test

**Spot-check observations** (n=3, NOT yet a portfolio claim):
- All required structural markers present in all 3 responses
- No fabricated facts in domain reasoning (minor typos only)
- Outputs coherent across saas/infra/frontend domains

The Hammerstein-audit pass criteria (≥80% of gold structural score,
≤15% hallucination rate, no catastrophic forgetting on out-of-domain
tasks) require the full 40-prompt eval + base+sysprompt ablation +
dedicated forgetting check. None of those have run yet. Until they
do, treat the spot-check as internal validation only — not as
gate-pass evidence.

## Using the adapter

### Option 1: PEFT (Python)

```python
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer

model = AutoPeftModelForCausalLM.from_pretrained(
    "tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter",
    load_in_4bit=True,  # if you have bitsandbytes
)
tokenizer = AutoTokenizer.from_pretrained(
    "tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter"
)
# No system prompt — framework is in the weights
messages = [{"role": "user", "content": "Audit this plan: <your query>"}]
prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
output = model.generate(**inputs, max_new_tokens=800, temperature=0.7)
print(tokenizer.decode(output[0], skip_special_tokens=True))
```

Requires: NVIDIA GPU with ≥6 GB VRAM (for 4-bit) or ≥16 GB (for fp16).

### Option 2: Unsloth (recommended for re-using `infer.py`)

```bash
python tools/distill/infer.py \
    --adapter tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter \
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
RAM; not viable on the 8 GB Mac without swap. Two paths:
- Spin up a RunPod pod for ~30 min ($0.20) to do the conversion
- Run on Ray's home PC if it has enough system RAM (not VRAM)

## Sharing / portfolio distribution

Pushed to HuggingFace as **private** at
[`huggingface.co/lerugray/hammerstein-7b-lora`](https://huggingface.co/lerugray/hammerstein-7b-lora)
on 2026-05-08 via [`tools/distill/hf_push.py`](tools/distill/hf_push.py).
Durability backup is now in place (drive failure no longer means a
50-min retrain).

The flip from private → public is gated on:
1. The full 40-prompt × 4-condition eval landing (gold / student /
   base+sysprompt / base-no-prompt)
2. A dedicated catastrophic-forgetting check (haiku, binary-tree
   explanation, etc.)
3. Updating this card with eval results + ablation finding

To flip public when ready: `python tools/distill/hf_push.py --public`.

## What this isn't

- **A smarter model than Qwen3.6.** It's smaller. The wrapper
  (`hp.py`) still produces better strategic reasoning because the
  underlying model is bigger. This adapter is an *artifact* — a
  shippable, distributable proof that the framework can be
  baked into a 7B model.
- **A replacement for the wrapper.** The wrapper stays as production.
  This adapter is the demo / portfolio piece.
- **Trained on confidential or proprietary data.** The 308 training
  pairs are synthetic, generated by Qwen3.6-plus + the public
  Hammerstein corpus. No private data, no scraping.

## Next steps (any of these is fine)

- [ ] Push to HuggingFace Hub for distribution
- [ ] Convert to GGUF + register with Ollama for local inference
- [ ] Run the full 40-prompt eval to get a clean PASS/FAIL number
- [ ] Re-train with more data (we used 308 of a possible 720+) if
      we want to push quality further
- [ ] Update README.md with eval result reference

The training itself is done. Everything else is downstream
distribution and packaging.
