#!/bin/bash
# Single-paste setup + training run for the RunPod pod.
# Designed to be invoked via:
#   curl -sL https://raw.githubusercontent.com/lerugray/hammerstein-model/master/tools/distill/run_training.sh | bash
#
# Or in JupyterLab's terminal:
#   bash <(curl -sL <same-url>)
#
# Idempotent — safe to re-run if it bails.

set -e

REPO_DIR=/workspace/hammerstein-model
DATA_BRANCH=data

echo "============================================="
echo " Hammerstein-7B distillation training run"
echo "============================================="
echo ""

# 1. Get the repo (the data branch has both code and the 308 training pairs)
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/4] Cloning repo…"
    cd /workspace
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all
git checkout $DATA_BRANCH
git pull origin $DATA_BRANCH

# 2. Verify GPU
echo ""
echo "[2/4] Verifying GPU…"
nvidia-smi --query-gpu=name,memory.total --format=csv

# 3. Install Python deps (~3-5 min first time)
echo ""
echo "[3/4] Installing dependencies (this takes ~3-5 min)…"
pip install -q --upgrade pip
pip install -q unsloth trl peft transformers datasets accelerate bitsandbytes

# 4. Run training
echo ""
echo "[4/4] Starting training (will take ~45-60 min on RTX 4090)…"
echo ""
python tools/distill/train.py \
    --data tools/distill/data/synthetic-2026-05-08.jsonl \
    --model-key qwen-7b \
    --backend unsloth \
    --execute

echo ""
echo "============================================="
echo " Training complete."
echo " Adapter saved to:"
echo "   $REPO_DIR/tools/distill/output/qwen-7b-hammerstein-lora/"
echo ""
echo " Quick spot-check (1 prompt):"
echo "   python tools/distill/infer.py \\"
echo "     --adapter $REPO_DIR/tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter \\"
echo "     --sample 3"
echo ""
echo " Then download the adapter via JupyterLab's file browser."
echo "============================================="
