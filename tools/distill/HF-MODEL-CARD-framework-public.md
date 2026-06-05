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

# Hammerstein-7B Framework — a small, opinionated strategic-reasoning model

A QLoRA adapter on `Qwen2.5-7B-Instruct` that bakes the
[Hammerstein framework](https://github.com/lerugray/hammerstein) into the
weights via behavior cloning. Load base + adapter, run inference **with no
system prompt at all**, and you get framework-correct strategic reasoning:
it names which failure quadrant a plan sits in (clever-lazy /
clever-industrious / stupid-industrious / stupid-lazy), pairs claims with
counter-observations, and proposes structural fixes over discipline fixes.

This is the **framework-only public artifact** (refreshed 2026-06-05). It is
trained on a framework-corpus distillation **with zero personal data** — the
training set was deterministically scrubbed and passed an adversarial
multi-agent privacy sweep before release. (Ongoing personal-corpus
fine-tuning of the author's daily-driver continues privately and is not
published here.)

## What it does that frontier assistants are tuned *not* to do

The framework deliberately reinforces three behaviors the big labs train
toward agreeableness and away from:

- **Refusal-with-pathway** — when the right answer is "don't do this," it
  says so, and surfaces what *would* unblock a yes, instead of a flat no or
  a reluctant yes.
- **Hold-your-ground** — it does not sycophantically fold when you push back
  with confidence but no new evidence. It restates the structural reason and
  tells you exactly what evidence would change its call.
- **Refuse stupid-industrious** — it declines to validate a confidently-stated
  plan that works hard in the wrong direction; it names the quadrant and
  offers a verification gate + structural alternative.

## Training data (framework-only, 1,994 pairs)

| Source | Pairs | What |
|---|---|---|
| Strategic (scrubbed v3a corpus) | 1,708 | audit-this-plan / scope-this-idea / is-this-worth-doing / what-should-we-do-next / review-from-different-angle, across 12 generic domains |
| Unique-behavior reinforcement | 72 | the three doctrine behaviors above (24 each) |
| Off-domain instruction-following | 214 | suppresses catastrophic forgetting (keeps general competence) |

Teacher: Qwen3.6-plus running the Hammerstein framework prompt (no corpus
retrieval, neutralized persona — clean by construction). Behavior-cloning
frame: **no system prompt in the training targets** — the framework is what
the student learns to bake in.

## Eval (framework-discipline benchmark, 2026-06-05)

Structural framework-correctness on 40 held-out strategic prompts
(higher = more framework-correct), and an out-of-domain forgetting check
on 30 prompts (framework-vocab leakage into off-domain answers; lower =
healthier):

| Condition | Strategic (n=40) | OOD leakage (n=30) |
|---|---|---|
| **student** (this adapter, **no system prompt**) | **0.975** | **0.000** |
| ablation (base + framework system prompt) | 0.675 | 0.783 |
| vanilla (base Qwen2.5-7B alone) | 0.081 | 0.000 |

**Adapter wins (Δ=+0.300 vs the prompt-only ablation) — the framework
lives in the weights, not just a runtime prompt.** OOD leakage is 0.000:
the distillation adds framework discipline with no measurable
catastrophic forgetting. Note the prompt-only ablation actually *leaks*
framework vocabulary into off-domain answers (0.783) where the distilled
student does not — the student fires the framework when the task calls
for it and stays quiet when it doesn't.

The framework-fidelity axis is partly tautological (the rubric rewards
framework vocabulary by design); the load-bearing signal is that the
distillation carries the *discipline* into 7B weights with no runtime
scaffolding, and does not wreck general competence (forgetting ≈ 0).

## Usage

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = "Qwen/Qwen2.5-7B-Instruct"
tok = AutoTokenizer.from_pretrained(base)
model = AutoModelForCausalLM.from_pretrained(base, device_map="auto")
model = PeftModel.from_pretrained(model, "lerugray/hammerstein-7b-framework")

msgs = [{"role": "user", "content": "Audit this plan: rewrite our API gateway from scratch in Rust to fix latency."}]
ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to(model.device)
print(tok.decode(model.generate(ids, max_new_tokens=600)[0][ids.shape[1]:], skip_special_tokens=True))
```

No system prompt needed. Runs locally on an 8 GB GPU at zero per-call cost.

## What this is not

Not a general-purpose frontier replacement. It is tuned for framework-shaped
strategic-reasoning tasks; generalization to neutral benchmarks (math, code,
long-context) is untested. The **framework is the IP**; this adapter is the
portability proof — a small owned model that holds an opinionated reasoning
doctrine you can run yourself.

Built alongside [hammerstein.ai](https://hammerstein.ai). Framework + corpus:
[github.com/lerugray/hammerstein](https://github.com/lerugray/hammerstein).
