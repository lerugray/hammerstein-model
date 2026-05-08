#!/bin/bash
# Single-paste eval run for the RunPod pod.
#
# Designed to be invoked via:
#   curl -sL https://raw.githubusercontent.com/lerugray/hammerstein-model/master/tools/distill/run_eval.sh | bash
#
# Or in JupyterLab's terminal:
#   bash <(curl -sL <same-url>)
#
# Prereqs (Ray):
#   1. Repo is public (or accessible via the pod) — flip private→public
#      in GitHub Settings before pasting; flip back when done.
#   2. HF_TOKEN env var set with a Read-or-better token for
#      lerugray/hammerstein-7b-lora (private). To set:
#        export HF_TOKEN=hf_xxxxxxxx
#
# Idempotent — safe to re-run.

set -e

REPO_DIR=/workspace/hammerstein-model
REPO_URL=https://github.com/lerugray/hammerstein-model.git

echo "============================================="
echo " Hammerstein-7B 4-condition eval run"
echo "============================================="
echo ""

# 1. HF auth check
if [ -z "$HF_TOKEN" ]; then
    echo "ERROR: HF_TOKEN not set. Required to download the private adapter."
    echo "  Run: export HF_TOKEN=hf_xxxxxxxx"
    echo "  Then re-paste this command."
    exit 1
fi

# 2. Get the repo
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/5] Cloning repo…"
    cd /workspace
    git clone "$REPO_URL"
fi
cd "$REPO_DIR"
echo "[1/5] Pulling latest…"
git fetch --all --quiet
git checkout master --quiet
git pull origin master --quiet

# 3. Verify GPU
echo ""
echo "[2/5] Verifying GPU…"
nvidia-smi --query-gpu=name,memory.total --format=csv

# 4. Install deps (idempotent)
echo ""
echo "[3/5] Installing dependencies (~3-5 min first time, instant after)…"
pip install -q --upgrade pip
pip install -q unsloth trl peft transformers datasets accelerate bitsandbytes huggingface_hub

# 5. HF login (so Unsloth can fetch the private adapter)
echo ""
echo "[4/5] Authenticating to HuggingFace…"
python -c "from huggingface_hub import login; import os; login(token=os.environ['HF_TOKEN'], add_to_git_credential=False); print('  HF login OK')"

# 6. Run the eval
echo ""
echo "[5/5] Running 4-condition eval (vanilla / ablation / student) + forgetting check…"
echo "      ~40 prompts × 3 local conditions + 4 forgetting prompts × 3 conditions"
echo "      ~50-70 min on RTX 4090"
echo ""
python tools/distill/eval.py \
    --skip-gold \
    --with-forgetting-check

echo ""
echo "============================================="
echo " Eval complete."
echo ""
echo " Results:"
echo "   $REPO_DIR/tools/distill/data/eval-$(date -u +%Y-%m-%d).jsonl"
echo "   $REPO_DIR/tools/distill/data/eval-$(date -u +%Y-%m-%d).summary.md"
echo ""
echo " To pull results back to your Mac, from your Mac terminal:"
echo "   POD=<pod-ip-or-host>"
echo "   scp -i ~/.ssh/your-pod-key root@\$POD:$REPO_DIR/tools/distill/data/eval-*.jsonl \\"
echo "     '/Users/rayweiss/Desktop/Dev Work/hammerstein-model/tools/distill/data/'"
echo "   scp -i ~/.ssh/your-pod-key root@\$POD:$REPO_DIR/tools/distill/data/eval-*.summary.md \\"
echo "     '/Users/rayweiss/Desktop/Dev Work/hammerstein-model/tools/distill/data/'"
echo ""
echo " Then STOP the pod in the RunPod dashboard."
echo "============================================="
