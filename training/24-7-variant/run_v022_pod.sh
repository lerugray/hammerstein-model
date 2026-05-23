#!/bin/bash
# v0.2.2 continued-LoRA on RunPod RTX A5000.
# Inherits the cmake-via-pip + GGML_CUDA=OFF fix from v0.2.1.

set -e

REPO_DIR=/workspace/hammerstein-model
SFT_OUTPUT=training/24-7-variant/output/qwen7b-v022-continued
GGUF_OUTPUT=training/24-7-variant/output/qwen7b-v022-q5km

V022_ADDITIONS=data/ray-stack-sft-v0.2.2-additions.jsonl
V01_RAY_STACK=data/ray-stack-sft-v0.1-combined.jsonl
V3A_SYNTHETIC=tools/distill/data/synthetic-v3a-2026-05-09.jsonl
V3A_ADAPTER=lerugray/hammerstein-7b-lora

cd /workspace 2>/dev/null || cd ~

echo "=== v0.2.2 continued-LoRA on $(hostname) ==="
date
echo ""

if [ ! -d "$REPO_DIR" ]; then
    echo "[1/4] Cloning hammerstein-model..."
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all && git checkout master && git pull

if [ ! -f /tmp/v022-deps-installed ]; then
    echo "[1/4] Installing deps..."
    pip install -q --upgrade pip
    pip install -q "transformers>=4.46,<4.50" trl peft datasets accelerate bitsandbytes sentencepiece
    pip install -q cmake
    pip uninstall -y torchao 2>/dev/null || true
    touch /tmp/v022-deps-installed
fi

nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv

for f in "$V022_ADDITIONS" "$V01_RAY_STACK" "$V3A_SYNTHETIC"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: missing $f"
        exit 1
    fi
    echo "  $f  ($(wc -l < $f) lines)"
done

mkdir -p "$SFT_OUTPUT" "$GGUF_OUTPUT"

if [ ! -f "$SFT_OUTPUT/lora-adapter/adapter_config.json" ]; then
    echo ""
    echo "[2/4] Training v0.2.2 (LR 2e-4, 2 epochs, 3x oversample, +250 v3a, +tool-calls)..."
    python training/24-7-variant/train_v022_continued.py \
        --v022-additions "$V022_ADDITIONS" \
        --v01-ray-stack "$V01_RAY_STACK" \
        --v3a-synthetic "$V3A_SYNTHETIC" \
        --v3a-adapter "$V3A_ADAPTER" \
        --output "$SFT_OUTPUT" \
        --execute
else
    echo "[2/4] Adapter exists - skipping train."
fi

MERGED_DIR="$SFT_OUTPUT/merged"
GGUF_F16="$GGUF_OUTPUT/model-f16.gguf"
GGUF_Q5="$GGUF_OUTPUT/hammerstein-7b-v022-q5_k_m.gguf"

if [ ! -f "$GGUF_Q5" ]; then
    echo ""
    echo "[3/4] Converting merged model to GGUF Q5_K_M..."
    if [ ! -f "$MERGED_DIR/config.json" ]; then
        echo "ERROR: merged model missing at $MERGED_DIR"
        exit 1
    fi

    if [ ! -d /workspace/llama.cpp ]; then
        git clone --depth 1 https://github.com/ggerganov/llama.cpp.git /workspace/llama.cpp
        pip install -q -r /workspace/llama.cpp/requirements.txt 2>/dev/null || true
    fi

    if [ ! -f "$GGUF_F16" ]; then
        python /workspace/llama.cpp/convert_hf_to_gguf.py \
            "$MERGED_DIR" --outtype f16 --outfile "$GGUF_F16"
    fi

    if [ ! -f /workspace/llama.cpp/build/bin/llama-quantize ]; then
        cd /workspace/llama.cpp
        rm -rf build
        cmake -B build -DGGML_CUDA=OFF -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -3
        cmake --build build --config Release --target llama-quantize -j$(nproc) 2>&1 | tail -5
        cd "$REPO_DIR"
    fi

    /workspace/llama.cpp/build/bin/llama-quantize "$GGUF_F16" "$GGUF_Q5" Q5_K_M
    rm -f "$GGUF_F16"
    echo "Q5_K_M written: $GGUF_Q5"
else
    echo "[3/4] Q5_K_M GGUF exists - skipping."
fi

echo ""
echo "[4/4] Done."
echo "scp back: $GGUF_Q5"
echo "Then on home PC:"
echo "  ollama create hammerstein-7b-v022 -f deploy/Modelfile.v022"
echo "  python scripts/v2_eval_failure_modes.py --model hammerstein-7b-v022 --tag v022-post-train"
echo "  python scripts/v2_compare_eval_runs.py \\"
echo "    data/eval-hammerstein-7b-2026-05-22-v1-baseline-v2.json \\"
echo "    data/eval-hammerstein-7b-v022-2026-05-23-v022-post-train.json \\"
echo "    --name-a v1 --name-b v0.2.2 \\"
echo "    --out session-notes/v022-vs-v1-eval-comparison.md"
echo ""
echo "TERMINATE THE POD after scp."
