# Distillation Experiment — Workflow

Scaffold for the Hammerstein-model fine-tuning experiment. See
`MODEL-EXPERIMENT.md` at the repo root for full design.

**Status: not yet executed.** Awaiting Ray's go/no-go.

## Files

- `seeds.py` — 30 seed prompts × 12 domains. Generates ~2000 expansions.
- `gen_data.py` — synthetic data generation pipeline. Default mode is
  dry-run; pass `--execute` to actually call OpenRouter.
- `eval.py` — three-way comparison harness (vanilla / student / gold).
  Stub backends until E3 (training) ships.
- `data/` — generated artifacts (gitignored once it exists).

## Workflow (in order)

```bash
# E0 — confirm scope (free)
python tools/distill/seeds.py     # see seed count + estimate

# E1 — curate eval set (manual, ~30 prompts)
# Hand-write `data/eval-set.jsonl` with prompts that probe strategic
# reasoning across templates. Ideally not derivable from the seeds.

# E1.5 — log gold answers (~$0.30, requires OPENROUTER_API_KEY)
python tools/distill/eval.py --skip-student --skip-vanilla

# E2 — generate synthetic training data (~$20, ~30-60 minutes)
python tools/distill/gen_data.py                 # dry-run plan
python tools/distill/gen_data.py --execute       # ACTUALLY fire

# E3 — train QLoRA (NOT IN THIS REPO YET)
# Use Unsloth or MLX-LM. Inputs: data/synthetic-<DATE>.jsonl
# Output: a LoRA adapter or merged GGUF.
# Recommended cloud: RunPod RTX 4090 ($0.34/hr, ~4 hours = ~$1.50)
# Recommended local: MLX-LM on Apple Silicon (Llama 3.2 3B) or
#                    Unsloth on NVIDIA 12GB+ (Qwen 2.5 7B)

# E4 — eval fine-tune (~$0.30 for fresh gold; free thereafter)
python tools/distill/eval.py \
    --student-path /path/to/trained \
    --vanilla-path /path/to/base

# E5 — decision (gates from MODEL-EXPERIMENT.md):
#   PASS:  student structural score ≥ 80% of gold
#   FAIL:  student structural score < 70% of gold OR catastrophic forgetting
#   GREY:  70-80% — manual judgment
```

## Cost & time budget

| Stage | Time | Cost |
|---|---|---|
| E0-E1: scope + eval set curation | 2 hr | $0 |
| E1.5: gold benchmarks | 30 min | ~$0.30 |
| E2: synthetic data generation | 1-2 hr | ~$20 |
| E3: QLoRA training (cloud) | 4-8 hr | $1.50-5 |
| E4: post-train eval | 1 hr | ~$0.60 |
| E5: writeup | 2 hr | $0 |
| **Total** | **10-14 hr** | **~$22-27** |

Hard ceiling: **$100**, abandon at **$75**.

## Refused for v1 (per Hammerstein audit)

- Pretraining from scratch (out of scope; MISSION ban)
- Continued pretraining (too expensive)
- Multi-epoch fine-tuning beyond 3 epochs (overfitting risk)
- Custom architecture changes
- Fine-tuning the teacher (Qwen3.6-plus is closed)
- Anything that requires Ray's PC GPU before he confirms its specs

## Decision points

These are Ray's calls before E2 fires:

1. **Greenlight $25-30 spend?**
2. **Base model: Qwen 2.5 7B (cloud) or Llama 3.2 3B (Mac local)?**
3. **PC GPU spec known?** (skip cloud if yes + adequate)
4. **Public release plan?** (HuggingFace under your name vs. private)

## What ships at the end

**Pass case:** `hammerstein-7b.gguf` artifact + `HAMMERSTEIN-MODEL.md`
writeup. Runnable via `ollama run hammerstein`.

**Fail case:** `FAILURE-LOG.md` with the eval table and structural
lessons. Per Hammerstein's audit, this also has portfolio value.

Either way: the wrapper (`hp.py`) stays as the production path.
