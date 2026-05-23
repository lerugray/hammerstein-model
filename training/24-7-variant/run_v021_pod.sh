#!/bin/bash
# v0.2.1 continued-LoRA on RunPod (RTX A5000 or RTX 4090).
# Picks up where run_v02_pod.sh left off but with the v0.2.1 hypotheses
# baked in (LR 2e-4, 3 epochs, 3x oversample, no v3a synthetic retention,
# +60 new pairs). Also bakes in the cmake-via-pip fix that v0.2 needed.

set -e

REPO_DIR=/workspace/hammerstein-model
SFT_OUTPUT=training/24-7-variant/output/qwen7b-v021-continued
GGUF_OUTPUT=training/24-7-variant/output/qwen7b-v021-q5km
RESULTS_DIR=training/24-7-variant/results
RUN_DATE=$(date -u +%Y-%m-%d)

V021_ADDITIONS=data/ray-stack-sft-v0.2.1-additions.jsonl
V01_RAY_STACK=data/ray-stack-sft-v0.1-combined.jsonl
V3A_ADAPTER=lerugray/hammerstein-7b-lora

cd /workspace 2>/dev/null || cd ~

echo "=== v0.2.1 continued-LoRA on $(hostname) ==="
date
echo ""

if [ ! -d "$REPO_DIR" ]; then
    echo "[1/4] Cloning hammerstein-model..."
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all && git checkout master && git pull

if [ ! -f /tmp/v021-deps-installed ]; then
    echo "[1/4] Installing deps..."
    pip install -q --upgrade pip
    pip install -q "transformers>=4.46,<4.50" trl peft datasets accelerate bitsandbytes sentencepiece
    # cmake fix learned from v0.2 run - apt repo doesn't have cmake
    pip install -q cmake
    pip uninstall -y torchao 2>/dev/null || true
    touch /tmp/v021-deps-installed
fi

nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv

# --- 2. Validate data ---
for f in "$V021_ADDITIONS" "$V01_RAY_STACK"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: missing $f"
        exit 1
    fi
    echo "  $f  ($(wc -l < $f) lines)"
done

mkdir -p "$SFT_OUTPUT" "$GGUF_OUTPUT" "$RESULTS_DIR"

# --- 3. Train ---
if [ ! -f "$SFT_OUTPUT/lora-adapter/adapter_config.json" ]; then
    echo ""
    echo "[2/4] Training (LR 2e-4, 3 epochs, 3x oversample, no v3a synthetic)..."
    python training/24-7-variant/train_v021_continued.py \
        --v021-additions "$V021_ADDITIONS" \
        --v01-ray-stack "$V01_RAY_STACK" \
        --v3a-adapter "$V3A_ADAPTER" \
        --output "$SFT_OUTPUT" \
        --execute
else
    echo "[2/4] Adapter exists - skipping train."
fi

# --- 4. GGUF conversion (with the cmake/GGML_CUDA=OFF fix from v0.2) ---
MERGED_DIR="$SFT_OUTPUT/merged"
GGUF_F16="$GGUF_OUTPUT/model-f16.gguf"
GGUF_Q5="$GGUF_OUTPUT/hammerstein-7b-v021-q5_k_m.gguf"

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

    # Build CPU-only quantize (CUDA not needed for quantization, avoids nvcc-not-found)
    if [ ! -f /workspace/llama.cpp/build/bin/llama-quantize ]; then
        cd /workspace/llama.cpp
        rm -rf build
        cmake -B build -DGGML_CUDA=OFF -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -3
        cmake --build build --config Release --target llama-quantize -j$(nproc) 2>&1 | tail -5
        cd "$REPO_DIR"
    fi

    /workspace/llama.cpp/build/bin/llama-quantize "$GGUF_F16" "$GGUF_Q5" Q5_K_M
    rm -f "$GGUF_F16"
    echo "Q5_K_M written: $GGUF_Q5 ($(ls -lh $GGUF_Q5 | awk '{print $5}'))"
else
    echo "[3/4] Q5_K_M GGUF exists - skipping."
fi

# --- 5. Package ---
echo ""
echo "[4/4] Done."
echo ""
echo "scp back: $GGUF_Q5"
echo "Then on home: ollama create hammerstein-7b-v021 -f deploy/Modelfile.v021"
echo "Eval:    python scripts/v2_eval_failure_modes.py --model hammerstein-7b-v021 --tag v021-post-train"
echo "Compare: python scripts/v2_compare_eval_runs.py \\"
echo "          data/eval-hammerstein-7b-2026-05-22-v1-baseline-v2.json \\"
echo "          data/eval-hammerstein-7b-v021-2026-05-23-v021-post-train.json \\"
echo "          --name-a v1 --name-b v0.2.1 \\"
echo "          --out session-notes/v021-vs-v1-eval-comparison.md"
echo ""
echo "TERMINATE THE POD after scp."
