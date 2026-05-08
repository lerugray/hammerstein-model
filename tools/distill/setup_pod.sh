#!/bin/bash
# Pod setup — paste this after SSH'ing into a fresh RunPod RTX 4090 pod.
# Idempotent: re-running is safe.

set -e

REPO_DIR=/workspace/hammerstein-model

echo "=== hammerstein-model pod setup ==="

if [ ! -d "$REPO_DIR" ]; then
    echo "Cloning repo…"
    cd /workspace
    git clone https://github.com/lerugray/hammerstein-model.git
    cd "$REPO_DIR"
else
    echo "Repo exists; pulling latest…"
    cd "$REPO_DIR"
    git pull
fi

echo ""
echo "Installing Python deps (this takes ~3-5 min the first time)…"
pip install -q --upgrade pip
pip install -q unsloth trl peft transformers datasets

echo ""
echo "Verifying GPU availability…"
python -c "import torch; assert torch.cuda.is_available(), 'No CUDA GPU detected'; print(f'  CUDA: {torch.cuda.get_device_name(0)} ({torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB)')"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy synthetic data into tools/distill/data/synthetic-2026-05-08.jsonl"
echo "     (scp from your local machine, or git checkout the data branch if pushed)"
echo "  2. Run training:"
echo "       cd $REPO_DIR"
echo "       python tools/distill/train.py --data tools/distill/data/synthetic-2026-05-08.jsonl --model-key qwen-7b --backend unsloth --execute"
echo "  3. After training, scp the adapter back: tools/distill/output/qwen-7b-hammerstein-lora/"
echo "  4. STOP the pod in the RunPod dashboard"
