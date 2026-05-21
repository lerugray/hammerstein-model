#!/bin/bash
# 24/7 variant — 5-axis eval harness, pod runner.
#
# Mirrors the style of run_main_sft_pod.sh.
# Runs AFTER training completes (trained model must exist at
#   training/24-7-variant/output/qwen3b-homelab-lora/merged/)
#
# Axes evaluated:
#   1. Voice alignment     >=70%  (pairwise LLM-judge, 30 prompts)
#   2. Domain coverage     >=60%  (15 project-stack questions)
#   3. Refusal alignment   >=80%  (10 stupid-industrious plans)
#   4. Uncertainty-honest  >=80%  (10 competence-ceiling prompts)
#   5. Latency             <2s short / <8s long
#
# Judge model: anthropic/claude-sonnet-4-5 via OpenRouter
# OPENROUTER_API_KEY must be set (passed via env or pre-exported on the pod).
#
# FIRE-READY — does NOT auto-launch. Run this script on the pod after SSH,
# once training has completed and the merged model is present.
#
# Pod: RTX 4090 (24 GB VRAM), CUDA 12.4 + PyTorch 2.4 template.
# Estimated cost: ~$0.50-1.00 (OR judge calls) + ~$0.20-0.50 (pod time for inference)
# Cost ceiling: $5 total for this eval run.

set -e

REPO_DIR=/workspace/hammerstein-model
TRAINED_MODEL=training/24-7-variant/output/qwen3b-homelab-lora/merged
EVAL_OUTPUT=training/24-7-variant/eval
RUN_DATE=$(date -u +%Y-%m-%d)

cd /workspace 2>/dev/null || cd ~

echo "=== 24/7 homelab bot variant — 5-axis eval ==="
date
echo ""

# --- 1. Repo + deps ---
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/4] Cloning hammerstein-model..."
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all && git checkout master && git pull

if [ ! -f /tmp/eval-deps-installed ]; then
    echo "[1/4] Installing eval deps..."
    pip install -q --upgrade pip
    # Pin transformers >=4.46,<4.50 — newer breaks Trainer imports (learned hard way on training pods)
    pip install -q "transformers>=4.46,<4.50" torch accelerate sentencepiece
    touch /tmp/eval-deps-installed
fi

echo "[1/4] GPU check..."
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
python -c "import torch; print(f'  PyTorch {torch.__version__}  CUDA: {torch.cuda.get_device_name(0)}')"

# --- 2. Check trained model present ---
echo ""
echo "[2/4] Checking trained model..."
if [ ! -d "$TRAINED_MODEL" ] || [ ! -f "$TRAINED_MODEL/config.json" ]; then
    echo "ERROR: Trained model not found at $TRAINED_MODEL"
    echo "  Training must complete before eval can run."
    echo "  Run run_main_sft_pod.sh first, then re-run this script."
    exit 1
fi
echo "  Trained model OK: $TRAINED_MODEL"

# --- 3. Check OPENROUTER_API_KEY ---
echo ""
echo "[3/4] Checking OpenRouter API key..."
if [ -z "$OPENROUTER_API_KEY" ]; then
    # Try loading from ~/.generalstaff/.env if on a machine that has it
    if [ -f ~/.generalstaff/.env ]; then
        # shellcheck disable=SC1090
        source ~/.generalstaff/.env
    fi
fi
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "ERROR: OPENROUTER_API_KEY not set."
    echo "  Set it before running this script:"
    echo "    export OPENROUTER_API_KEY=sk-or-..."
    echo "  Or place it in ~/.generalstaff/.env as:"
    echo "    export OPENROUTER_API_KEY=sk-or-..."
    exit 1
fi
echo "  OPENROUTER_API_KEY: OK"

# --- 4. Run eval harness ---
echo ""
echo "[4/4] Running 5-axis eval..."
echo "  Judge model: anthropic/claude-sonnet-4-5 (OpenRouter)"
echo "  Output dir:  $EVAL_OUTPUT"
echo ""

python training/24-7-variant/eval_24-7_variant.py \
    --output "$EVAL_OUTPUT" \
    --verbose

# Find and print the results file location
RESULTS_FILE=$(ls "$EVAL_OUTPUT"/RESULTS-24-7-v0-*.md 2>/dev/null | sort | tail -1)

echo ""
echo "=== 5-axis eval complete ==="
date
echo ""
if [ -n "$RESULTS_FILE" ]; then
    echo "Results file: $RESULTS_FILE"
    echo ""
    echo "Top-level verdict:"
    # Print the verdict line from the results file
    grep -A1 "## Ship gate verdict" "$RESULTS_FILE" | tail -1
    echo ""
    echo "Files to scp back to Mac:"
    echo "  $RESULTS_FILE"
fi
echo ""
echo "STOP THE POD in the RunPod dashboard once scp is done."
