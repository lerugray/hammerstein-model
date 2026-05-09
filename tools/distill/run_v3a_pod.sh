#!/bin/bash
# v3a: mixed-mode training (v2a strategic data + off-domain instruction mix).
#
# Goal: keep v2a's strategic gain, fix the OOD regression we saw in v2.
# Single variable change vs v2a: added ~220 off-domain pairs.
#
# Pod: RTX 4090, 30 GB disk. Reuses v2 pod template.
#
# Pipeline:
#   [1/5] Repo + deps
#   [2/5] Train v3a (combined dataset)
#   [3/5] Re-eval v1 on expanded 30-OOD set (same env baseline)
#   [4/5] Re-eval v2a on expanded 30-OOD set
#   [5/5] Eval v3a on expanded 30-OOD set
#
# Total pod time: ~2 hr × $0.69/hr = ~$1.40

set -e

REPO_DIR=/workspace/hammerstein-model
V3A_DATA=tools/distill/data/synthetic-v3a-2026-05-09.jsonl
V3A_OUTPUT=tools/distill/output/qwen-7b-hammerstein-v3a-lora
V1_ADAPTER_HF=lerugray/hammerstein-7b-lora
V2A_OUTPUT=tools/distill/output/qwen-7b-hammerstein-v2a-lora
EVAL_DATE=$(date -u +%Y-%m-%d)
SUFFIX="v3a"

cd /workspace 2>/dev/null || cd ~

echo "=== v3a training + eval pipeline ==="
date

# --- 1. Repo + deps ---
if [ ! -d "$REPO_DIR" ]; then
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all && git checkout master && git pull

if [ ! -f "$V3A_DATA" ]; then
    echo "ERROR: $V3A_DATA not in repo. Push v3a data to master first."
    exit 1
fi

if [ ! -f /tmp/v2-deps-installed ]; then
    pip install -q --upgrade pip
    pip install -q unsloth trl peft transformers datasets accelerate bitsandbytes
    touch /tmp/v2-deps-installed
fi

nvidia-smi --query-gpu=name,memory.total --format=csv

# --- 2. Train v3a ---
if [ ! -f "$V3A_OUTPUT/lora-adapter/adapter_config.json" ]; then
    echo "[2/5] Training v3a (mixed-mode, ~15 min)…"
    python tools/distill/train.py \
        --data "$V3A_DATA" \
        --model-key qwen-7b \
        --backend unsloth \
        --output "$V3A_OUTPUT" \
        --execute
else
    echo "[2/5] v3a adapter exists — skipping."
fi

# --- 3. Re-eval v1 (on expanded 30-OOD set) ---
EVAL_V1_FILE="tools/distill/data/eval-v1-rerun-${SUFFIX}-$EVAL_DATE.jsonl"
if [ ! -f "$EVAL_V1_FILE" ]; then
    echo "[3/5] Re-eval v1 on 30-OOD set (~30 min)…"
    rm -f tools/distill/data/eval-$EVAL_DATE.jsonl tools/distill/data/eval-$EVAL_DATE.summary.md
    python tools/distill/eval.py \
        --adapter-path "$V1_ADAPTER_HF" \
        --skip-gold \
        --with-forgetting-check \
        --overwrite
    mv tools/distill/data/eval-$EVAL_DATE.jsonl "$EVAL_V1_FILE"
    mv tools/distill/data/eval-$EVAL_DATE.summary.md "${EVAL_V1_FILE%.jsonl}.summary.md"
else
    echo "[3/5] v1 re-eval exists — skipping."
fi

# --- 4. Re-eval v2a (on expanded 30-OOD set) ---
EVAL_V2A_FILE="tools/distill/data/eval-v2a-rerun-${SUFFIX}-$EVAL_DATE.jsonl"
if [ ! -f "$EVAL_V2A_FILE" ]; then
    # v2a adapter must be on the pod first (scp'd from Mac before running this script)
    if [ ! -d "$V2A_OUTPUT/lora-adapter" ] && [ -f /tmp/v2a-lora-adapter.tar.gz ]; then
        echo "[4/5] Unpacking v2a adapter from /tmp…"
        mkdir -p "$V2A_OUTPUT"
        tar -xzf /tmp/v2a-lora-adapter.tar.gz -C "$V2A_OUTPUT"
    fi
    if [ ! -d "$V2A_OUTPUT/lora-adapter" ]; then
        echo "[4/5] WARN: v2a adapter not on pod — skipping v2a re-eval. scp lora-adapter.tar.gz to /tmp/v2a-lora-adapter.tar.gz before running."
    else
        echo "[4/5] Re-eval v2a on 30-OOD set (~30 min)…"
        rm -f tools/distill/data/eval-$EVAL_DATE.jsonl tools/distill/data/eval-$EVAL_DATE.summary.md
        python tools/distill/eval.py \
            --adapter-path "$V2A_OUTPUT/lora-adapter" \
            --skip-gold \
            --with-forgetting-check \
            --overwrite
        mv tools/distill/data/eval-$EVAL_DATE.jsonl "$EVAL_V2A_FILE"
        mv tools/distill/data/eval-$EVAL_DATE.summary.md "${EVAL_V2A_FILE%.jsonl}.summary.md"
    fi
else
    echo "[4/5] v2a re-eval exists — skipping."
fi

# --- 5. Eval v3a ---
EVAL_V3A_FILE="tools/distill/data/eval-v3a-$EVAL_DATE.jsonl"
if [ ! -f "$EVAL_V3A_FILE" ]; then
    echo "[5/5] Eval v3a (~30 min)…"
    rm -f tools/distill/data/eval-$EVAL_DATE.jsonl tools/distill/data/eval-$EVAL_DATE.summary.md
    python tools/distill/eval.py \
        --adapter-path "$V3A_OUTPUT/lora-adapter" \
        --skip-gold \
        --with-forgetting-check \
        --overwrite
    mv tools/distill/data/eval-$EVAL_DATE.jsonl "$EVAL_V3A_FILE"
    mv tools/distill/data/eval-$EVAL_DATE.summary.md "${EVAL_V3A_FILE%.jsonl}.summary.md"
else
    echo "[5/5] v3a eval exists — skipping."
fi

# Tar adapter
if [ -d "$V3A_OUTPUT/lora-adapter" ] && [ ! -f "$V3A_OUTPUT/lora-adapter.tar.gz" ]; then
    tar -czf "$V3A_OUTPUT/lora-adapter.tar.gz" -C "$V3A_OUTPUT" lora-adapter
fi

# v2a adapter — needed for re-eval. Check it was downloaded automatically by the eval (it's loaded
# from the local path the train script wrote earlier). For v3a we rely on v2a being preserved on the
# pod from a prior session. If not present, fall back to fetching from a separate location.
echo ""
echo "=== Pipeline complete ==="
echo "Files to scp back:"
echo "  $V3A_OUTPUT/lora-adapter.tar.gz"
echo "  $EVAL_V1_FILE  (+ summary)"
echo "  $EVAL_V2A_FILE (+ summary)"
echo "  $EVAL_V3A_FILE (+ summary)"
date
