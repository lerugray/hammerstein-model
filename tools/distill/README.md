# Distillation Experiment — Workflow

Scaffold + actuals for the Hammerstein-model fine-tuning experiment.
See [`MODEL-EXPERIMENT.md`](../../MODEL-EXPERIMENT.md) at the repo
root for the full design and [`HAMMERSTEIN-7B.md`](../../HAMMERSTEIN-7B.md)
for the full eval write-up + hyperparameters + hardware specs.

**Status: shipped 2026-05-08.** Adapter trained, 4-condition eval
ran (ADAPTER WINS the prompt ablation by Δ=+0.206), Q4_K_M GGUF
converted, all artifacts public on
[`huggingface.co/lerugray/hammerstein-7b-lora`](https://huggingface.co/lerugray/hammerstein-7b-lora).

## Files

- `seeds.py` — 30 seed prompts × 12 domains. Generates ~2000 expansions.
- `gen_data.py` — synthetic data generation pipeline. Default mode is
  dry-run; pass `--execute` to actually call OpenRouter.
- `train.py` — QLoRA training scaffold (Unsloth backend, 7B/3B model
  keys, dry-run by default; `--execute` to actually train).
- `eval.py` — 4-condition comparison harness (gold / student /
  ablation / vanilla) + structural-score rubric.
- `infer.py` — single-prompt inference against a local or HF adapter.
- `convert_gguf.py` — base+adapter merge → llama.cpp → GGUF +
  Ollama Modelfile + HF push.
- `hf_push.py` — HuggingFace adapter push + visibility flip.
- `setup_pod.sh` / `run_training.sh` / `run_eval.sh` / `run_gguf.sh`
  — single-paste RunPod orchestration scripts (pod-side; assume
  GH_TOKEN + HF_TOKEN env vars).
- `data/` — eval-set.jsonl (held-out, hand-curated),
  synthetic-2026-05-08.jsonl (training set), eval-2026-05-08.jsonl
  (full per-prompt × per-condition results),
  hammerstein-system-prompt.txt (teacher system prompt; checked in
  for transparency).

## Workflow (in order)

```bash
# E0 — confirm scope (free)
python tools/distill/seeds.py     # see seed count + estimate

# E1 — curate eval set (manual, ~30 prompts)
# Hand-write `data/eval-set.jsonl` with prompts that probe strategic
# reasoning across templates. Ideally not derivable from the seeds.

# E1.5 — log gold answers (~$0.30, requires OPENROUTER_API_KEY)
python tools/distill/eval.py --skip-student --skip-vanilla

# E2 — generate synthetic training data (~$2.31 actual, ~30-60 min)
python tools/distill/gen_data.py                 # dry-run plan
python tools/distill/gen_data.py --execute       # ACTUALLY fire

# E3 — train QLoRA (~50 min on RTX 4090, ~$0.50)
python tools/distill/train.py --model-key qwen-7b           # dry-run
python tools/distill/train.py --model-key qwen-7b --execute # ACTUAL training
# Or for Mac (Apple Silicon):
python tools/distill/train.py --model-key llama-3b --backend mlx --execute

# E4 — eval fine-tune (~$0.32 for fresh gold; free thereafter)
python tools/distill/eval.py \
    --student-path tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter \
    --vanilla-path unsloth/Qwen2.5-7B-Instruct-bnb-4bit

# E5 — decision gate (per MODEL-EXPERIMENT.md):
#   PASS:  student structural score ≥ 80% of gold
#   FAIL:  student structural score < 70% of gold OR catastrophic forgetting
#   GREY:  70-80% — manual judgment
# Actual outcome 2026-05-08: PASS (student/gold = 1.01; ADAPTER WINS
#   ablation by Δ=+0.206). OOD leakage 0.312 disclosed in the model
#   card as a known limitation, mitigatable via mixed-mode retrain.

# E6 — Q4_K_M GGUF + Ollama (optional, ~6 min on A5000, ~$0.07)
python tools/distill/convert_gguf.py --quant q4_k_m
```

## Cost & time — planned vs. actual

| Stage | Planned (time / cost) | Actual (time / cost) |
|---|---|---|
| E0-E1: scope + eval set curation | 2 hr / $0 | ~2 hr / $0 |
| E1.5: gold benchmarks | 30 min / ~$0.30 | ~30 min / $0.32 |
| E2: synthetic data generation | 1-2 hr / ~$20 | ~1 hr / $2.31 (stopped early at 308 pairs) |
| E3: QLoRA training (cloud) | 4-8 hr / $1.50-5 | ~50 min / ~$0.50 (Unsloth efficiency) |
| E4: post-train eval | 1 hr / ~$0.60 | ~1 hr / ~$0.50 (pod time) |
| E5: writeup | 2 hr / $0 | ~1 hr / $0 |
| E6: GGUF + Ollama | not planned | ~6 min / ~$0.22 (incl. dud-pod retry) |
| **Total** | **10-14 hr / ~$22-27** | **~6 hr / ~$3.97** |

Hard ceiling was $100; landed at ~16% of that.

## Refused for v1 (per Hammerstein audit)

- Pretraining from scratch (out of scope; MISSION ban)
- Continued pretraining (too expensive)
- Multi-epoch fine-tuning beyond 3 epochs (overfitting risk)
- Custom architecture changes
- Fine-tuning the teacher (Qwen3.6-plus is closed)

## What shipped

**Pass case:** [`HAMMERSTEIN-7B.md`](../../HAMMERSTEIN-7B.md) writeup
+ public Q4_K_M GGUF on HuggingFace. Runnable via:

```bash
ollama run hf.co/lerugray/hammerstein-7b-lora:Q4_K_M \
    "Audit this plan: ship MVP Friday"
```

The wrapper ([`hp.py`](../../hp.py)) stays as the production path;
the adapter is the deployable snapshot.
