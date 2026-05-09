#!/bin/bash
# v2a + v2b training + eval — paste this on a fresh RunPod RTX 4090 pod.
#
# v2a: qwen3.6-plus teacher (data scaling test, same teacher as v1)
# v2b: DeepSeek v4-pro teacher (teacher quality test)
# Both use 1500 pairs, Qwen2.5-7B base, 3 epochs (single-variable per Hammerstein audit)
#
# Prereqs (on the dashboard FIRST):
#   1. Spin up RTX 4090 (24 GB), CUDA 12.4 + PyTorch 2.4 template, 30 GB disk
#   2. SSH in
#   3. Both v2 data files must be pushed to GitHub master before running this
#
# Idempotent — safe to re-run if it bails. Each step gated by a marker file.
#
# Total budget: ~$2.50 pod time. Each train ~50 min, each eval ~30 min.

set -e

REPO_DIR=/workspace/hammerstein-model
V2A_DATA=tools/distill/data/synthetic-2026-05-09.jsonl
V2B_DATA=tools/distill/data/synthetic-v2b-2026-05-09.jsonl
V2A_OUTPUT=tools/distill/output/qwen-7b-hammerstein-v2a-lora
V2B_OUTPUT=tools/distill/output/qwen-7b-hammerstein-v2b-lora
V1_ADAPTER_HF=lerugray/hammerstein-7b-lora
EVAL_DATE=$(date -u +%Y-%m-%d)

cd /workspace 2>/dev/null || cd ~

echo "=== v2a + v2b training + eval pipeline ==="
date

# --- 1. Repo + deps ---
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/8] Cloning hammerstein-model…"
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all
git checkout master
git pull

if [ ! -f "$V2A_DATA" ]; then
    echo "ERROR: $V2A_DATA not in repo. Push v2a data to master first."
    exit 1
fi
if [ ! -f "$V2B_DATA" ]; then
    echo "WARN: $V2B_DATA missing — will train v2a only."
    V2B_AVAILABLE=0
else
    V2B_AVAILABLE=1
fi

if [ ! -f /tmp/v2-deps-installed ]; then
    echo "[2/8] Installing deps (~3-5 min first time)…"
    pip install -q --upgrade pip
    pip install -q unsloth trl peft transformers datasets accelerate bitsandbytes
    touch /tmp/v2-deps-installed
fi

echo "[3/8] GPU check…"
nvidia-smi --query-gpu=name,memory.total --format=csv

# --- 4. Train v2a ---
if [ ! -f "$V2A_OUTPUT/lora-adapter/adapter_config.json" ]; then
    echo "[4/8] Training v2a (qwen3.6-plus teacher, ~50 min)…"
    python tools/distill/train.py \
        --data "$V2A_DATA" \
        --model-key qwen-7b \
        --backend unsloth \
        --output "$V2A_OUTPUT" \
        --execute
else
    echo "[4/8] v2a adapter exists — skipping."
fi

# --- 5. Train v2b ---
if [ "$V2B_AVAILABLE" = "1" ] && [ ! -f "$V2B_OUTPUT/lora-adapter/adapter_config.json" ]; then
    echo "[5/8] Training v2b (DeepSeek v4-pro teacher, ~50 min)…"
    python tools/distill/train.py \
        --data "$V2B_DATA" \
        --model-key qwen-7b \
        --backend unsloth \
        --output "$V2B_OUTPUT" \
        --execute
elif [ "$V2B_AVAILABLE" = "1" ]; then
    echo "[5/8] v2b adapter exists — skipping."
else
    echo "[5/8] v2b skipped (data not in repo)."
fi

# --- 6. Eval v1 (re-eval, same-env baseline) ---
EVAL_V1_FILE="tools/distill/data/eval-v1-rerun-$EVAL_DATE.jsonl"
if [ ! -f "$EVAL_V1_FILE" ]; then
    echo "[6/8] Re-eval v1 from HF for same-env baseline (~30 min)…"
    rm -f tools/distill/data/eval-$EVAL_DATE.jsonl tools/distill/data/eval-$EVAL_DATE.summary.md
    python tools/distill/eval.py \
        --adapter-path "$V1_ADAPTER_HF" \
        --skip-gold \
        --with-forgetting-check \
        --overwrite
    mv tools/distill/data/eval-$EVAL_DATE.jsonl "$EVAL_V1_FILE"
    mv tools/distill/data/eval-$EVAL_DATE.summary.md "${EVAL_V1_FILE%.jsonl}.summary.md"
else
    echo "[6/8] v1 re-eval exists — skipping."
fi

# --- 7. Eval v2a ---
EVAL_V2A_FILE="tools/distill/data/eval-v2a-$EVAL_DATE.jsonl"
if [ ! -f "$EVAL_V2A_FILE" ]; then
    echo "[7a/8] Eval v2a (~30 min)…"
    rm -f tools/distill/data/eval-$EVAL_DATE.jsonl tools/distill/data/eval-$EVAL_DATE.summary.md
    python tools/distill/eval.py \
        --adapter-path "$V2A_OUTPUT/lora-adapter" \
        --skip-gold \
        --with-forgetting-check \
        --overwrite
    mv tools/distill/data/eval-$EVAL_DATE.jsonl "$EVAL_V2A_FILE"
    mv tools/distill/data/eval-$EVAL_DATE.summary.md "${EVAL_V2A_FILE%.jsonl}.summary.md"
else
    echo "[7a/8] v2a eval exists — skipping."
fi

# --- 7b. Eval v2b ---
EVAL_V2B_FILE="tools/distill/data/eval-v2b-$EVAL_DATE.jsonl"
if [ "$V2B_AVAILABLE" = "1" ] && [ ! -f "$EVAL_V2B_FILE" ]; then
    echo "[7b/8] Eval v2b (~30 min)…"
    rm -f tools/distill/data/eval-$EVAL_DATE.jsonl tools/distill/data/eval-$EVAL_DATE.summary.md
    python tools/distill/eval.py \
        --adapter-path "$V2B_OUTPUT/lora-adapter" \
        --skip-gold \
        --with-forgetting-check \
        --overwrite
    mv tools/distill/data/eval-$EVAL_DATE.jsonl "$EVAL_V2B_FILE"
    mv tools/distill/data/eval-$EVAL_DATE.summary.md "${EVAL_V2B_FILE%.jsonl}.summary.md"
elif [ "$V2B_AVAILABLE" = "1" ]; then
    echo "[7b/8] v2b eval exists — skipping."
fi

# --- 8. Tar adapters for download ---
for OUT in "$V2A_OUTPUT" "$V2B_OUTPUT"; do
    if [ -d "$OUT/lora-adapter" ] && [ ! -f "$OUT/lora-adapter.tar.gz" ]; then
        echo "[8/8] Packaging $(basename $OUT) for download…"
        tar -czf "$OUT/lora-adapter.tar.gz" -C "$OUT" lora-adapter
    fi
done

echo ""
echo "=== Pipeline complete ==="
echo "Files to scp back to Mac:"
echo "  $V2A_OUTPUT/lora-adapter.tar.gz       ← v2a LoRA adapter (~323 MB)"
[ -d "$V2B_OUTPUT/lora-adapter" ] && echo "  $V2B_OUTPUT/lora-adapter.tar.gz       ← v2b LoRA adapter (~323 MB)"
echo "  $EVAL_V1_FILE                         ← v1 re-eval (same env)"
echo "  $EVAL_V2A_FILE                        ← v2a eval"
[ -f "$EVAL_V2B_FILE" ] && echo "  $EVAL_V2B_FILE                        ← v2b eval"
echo ""
echo "On Mac, then: STOP THE POD before stepping away."
date
