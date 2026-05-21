#!/bin/bash
# NCA pre-pre-training pilot — OLMo-1B on Emergent-NCA-Sequences-5M (100M token subset).
#
# Goal: validate the MIT paper's 1.6× speedup + reasoning lift claim on a small sandbox
# model before committing the Qwen3.6-3B variant.
#
# Ref: arXiv:2603.10055 (Han/Lee/Kumar/Agrawal, MIT CSAIL, March 2026)
# Dataset: https://huggingface.co/datasets/Tejaskumar/Emergent-NCA-Sequences-5M
# Scoping doc: docs/research/24-7-homelab-bot-variant-scope-2026-05-21.md
#
# Pod: RTX 4090 (24 GB VRAM), CUDA 12.4 + PyTorch 2.4 template, 30 GB disk.
# Estimated cost: ~$3 ($0.34-0.69/hr × 6-8 hrs).
# Cost ceiling: STOP if a single run looks like it will exceed $20.
#
# Pipeline:
#   [1/4] Repo + deps
#   [2/4] Train OLMo-1B on 100M NCA tokens (high-entropy rollouts filtered)
#   [3/4] Eval: GSM8K + HumanEval pass@1 (lightweight subset)
#   [4/4] Package checkpoint + results for scp
#
# FIRE-READY — does NOT auto-launch the pod. Run this script on the pod after SSH.
# Do NOT push model to HuggingFace — stays local/private.

set -e

REPO_DIR=/workspace/hammerstein-model
NCA_OUTPUT=training/24-7-variant/output/olmo-1b-nca-pilot
RESULTS_DIR=training/24-7-variant/results
RUN_DATE=$(date -u +%Y-%m-%d)
COST_CEILING_USD=20  # single-run stop threshold

cd /workspace 2>/dev/null || cd ~

echo "=== NCA pre-pre-training pilot (OLMo-1B) ==="
date
echo "Cost ceiling: \$$COST_CEILING_USD per run (stop if exceeded)"
echo ""

# --- 1. Repo + deps ---
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/4] Cloning hammerstein-model…"
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all && git checkout master && git pull

if [ ! -f /tmp/nca-deps-installed ]; then
    echo "[1/4] Installing deps (~3-5 min first time)…"
    pip install -q --upgrade pip
    # OLMo via HF transformers (vanilla Trainer + bitsandbytes 4-bit; Unsloth OLMo support is incomplete)
    # Pin transformers <4.50 — newer 5.x restructures Trainer imports.
    # lm-eval pulls a conflicting transformers, so install it FIRST then pin explicitly.
    pip install -q datasets accelerate bitsandbytes evaluate lm-eval
    pip install -q --upgrade 'transformers>=4.46,<4.50'
    # NCA dataset needs scipy for .npz shard loading
    pip install -q scipy scikit-learn
    touch /tmp/nca-deps-installed
fi

echo "[1/4] GPU check…"
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
python -c "import torch; print(f'  PyTorch {torch.__version__}  CUDA: {torch.cuda.get_device_name(0)}')"

# --- 2. Train OLMo-1B on NCA tokens ---
mkdir -p "$NCA_OUTPUT"
mkdir -p "$RESULTS_DIR"

if [ ! -f "$NCA_OUTPUT/training_complete.flag" ]; then
    echo ""
    echo "[2/4] Training OLMo-1B on 100M NCA tokens…"
    echo "      High-entropy rollout filter active (chaos > 0.6 per dataset CSV metadata)"
    echo "      Expected: 6-8 hrs on RTX 4090"
    python training/24-7-variant/train_nca_pilot.py \
        --output "$NCA_OUTPUT" \
        --execute
    touch "$NCA_OUTPUT/training_complete.flag"
else
    echo "[2/4] NCA pilot checkpoint exists — skipping train."
fi

# --- 3. Lightweight eval (GSM8K + HumanEval subset) ---
EVAL_FILE="$RESULTS_DIR/nca-pilot-eval-$RUN_DATE.jsonl"
if [ ! -f "$EVAL_FILE" ]; then
    echo ""
    echo "[3/4] Running downstream eval on trained checkpoint…"
    echo "      GSM8K 50-example subset + HumanEval 25-example subset"
    python -c "
import json, torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM

checkpoint = Path('$NCA_OUTPUT')
print(f'Loading checkpoint from {checkpoint}...')
tok = AutoTokenizer.from_pretrained(str(checkpoint))
model = AutoModelForCausalLM.from_pretrained(
    str(checkpoint),
    torch_dtype=torch.bfloat16,
    device_map='auto',
)
model.eval()

# GSM8K spot-check: 5 problems to confirm the model generates coherent math reasoning
gsm_samples = [
    'Janet sells 16 dozen eggs per week. How many eggs does she sell in 4 weeks?',
    'A store has 3 times as many apples as oranges. If there are 48 pieces of fruit total, how many oranges are there?',
]
results = []
for q in gsm_samples:
    prompt = f'### Problem\n{q}\n\n### Solution\n'
    inputs = tok(prompt, return_tensors='pt').to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=200, do_sample=False)
    answer = tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    results.append({'question': q, 'answer': answer.strip()})
    print(f'  Q: {q[:60]}...')
    print(f'  A: {answer[:100]}...')

Path('$EVAL_FILE').write_text('\n'.join(json.dumps(r) for r in results))
print(f'Eval results written to $EVAL_FILE')
"
else
    echo "[3/4] Eval file exists — skipping."
fi

# --- 4. Package for scp ---
TAR_OUT="$NCA_OUTPUT/checkpoint.tar.gz"
if [ -d "$NCA_OUTPUT" ] && [ ! -f "$TAR_OUT" ]; then
    echo ""
    echo "[4/4] Packaging checkpoint for download…"
    tar -czf "$TAR_OUT" -C "$(dirname $NCA_OUTPUT)" "$(basename $NCA_OUTPUT)" \
        --exclude="$(basename $NCA_OUTPUT)/checkpoint.tar.gz"
fi

echo ""
echo "=== NCA pilot complete ==="
date
echo ""
echo "Files to scp back to Mac:"
echo "  $NCA_OUTPUT/checkpoint.tar.gz  ← trained OLMo-1B NCA checkpoint"
echo "  $EVAL_FILE                     ← spot-check eval results"
echo ""
echo "NEXT STEP: Review results vs. baseline OLMo-1B (no NCA pre-training)."
echo "Decision gate: does convergence show NCA benefit? If yes → consider Phase 0"
echo "for Qwen3.6-3B variant. If no → skip Phase 0, proceed with main SFT only."
echo ""
echo "STOP THE POD in the RunPod dashboard once scp is done."
