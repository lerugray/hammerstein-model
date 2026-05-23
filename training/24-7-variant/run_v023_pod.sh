#!/bin/bash
# v0.2.3 continued-LoRA on RunPod (A5000 SECURE or 4090) — voice-fix
# iteration on top of v0.2.2. Adds 90 voice-anchor pairs (40 hand +
# 50 sonnet-extended) targeting the casual-relational register Ray
# ratified via AskUserQuestion (hybrid voice + relational reciprocation).
#
# Pipeline:
#   [1/5] Repo + deps
#   [2/5] Data validation (v0.2.3 additions + v0.1 Ray-stack + v3a synthetic)
#   [3/5] Train (continued LoRA from v3a HF adapter, ~30 min)
#   [4/5] Merge adapter, convert merged HF to GGUF Q5_K_M via llama.cpp
#   [5/5] Tar artifacts for scp back to home PC
#
# Pod: RunPod A5000 SECURE (24 GB VRAM) or RTX 4090, CUDA 12.4 + PyTorch
# 2.4 template, 40 GB disk. Estimated cost: ~$0.60 ($0.34/hr × ~1.5 hr).
# Hard ceiling $20.
#
# FIRE-READY — does NOT auto-launch the pod. Run after SSH'ing in.
# Do NOT push to HuggingFace — model stays private.

set -e

REPO_DIR=/workspace/hammerstein-model
SFT_OUTPUT=training/24-7-variant/output/qwen7b-v023-continued
GGUF_OUTPUT=training/24-7-variant/output/qwen7b-v023-q5km
RESULTS_DIR=training/24-7-variant/results
RUN_DATE=$(date -u +%Y-%m-%d)
COST_CEILING_USD=20

V023_ADDITIONS=data/ray-stack-sft-v0.2.3-additions.jsonl
V01_RAY_STACK=data/ray-stack-sft-v0.1-combined.jsonl
V3A_SYNTHETIC=tools/distill/data/synthetic-v3a-2026-05-09.jsonl
V3A_ADAPTER=lerugray/hammerstein-7b-lora

cd /workspace 2>/dev/null || cd ~

echo "=== Qwen2.5-7B v0.2.3 continued-LoRA ==="
date
echo "Cost ceiling: \$$COST_CEILING_USD (stop if exceeded)"
echo ""

# --- 1. Repo + deps ---
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/5] Cloning hammerstein-model..."
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all && git checkout master && git pull

if [ ! -f /tmp/v023-deps-installed ]; then
    echo "[1/5] Installing deps (~3-5 min first time)..."
    pip install -q --upgrade pip
    pip install -q "transformers>=4.46,<4.50" trl peft datasets accelerate bitsandbytes sentencepiece
    pip uninstall -y torchao 2>/dev/null || true
    touch /tmp/v023-deps-installed
fi

echo "[1/5] GPU check..."
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
python -c "import torch; print(f'  PyTorch {torch.__version__}  CUDA: {torch.cuda.get_device_name(0)}')"

# --- 2. Data validation ---
echo ""
echo "[2/5] Validating data..."

for f in "$V023_ADDITIONS" "$V01_RAY_STACK" "$V3A_SYNTHETIC"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: Required data file missing: $f"
        echo "  v0.2.3 additions: run scripts/v023_concat_sanitize.py locally + commit."
        echo "  v0.1 combined should be committed."
        echo "  v3a synthetic should be in repo from v1 ship."
        exit 1
    fi
    count=$(wc -l < "$f")
    echo "  $f  ($count lines)"
done

mkdir -p "$SFT_OUTPUT" "$GGUF_OUTPUT" "$RESULTS_DIR"

# --- 3. Train ---
if [ ! -f "$SFT_OUTPUT/lora-adapter/adapter_config.json" ]; then
    echo ""
    echo "[3/5] Continued LoRA training (Qwen2.5-7B + v3a adapter + v0.2.3 mix)..."
    echo "      LR 2e-4, 2 epochs, eff batch 8, max_seq 2048"
    echo "      Expected: ~30 min on A5000 / RTX 4090"
    python training/24-7-variant/train_v023_continued.py \
        --v023-additions "$V023_ADDITIONS" \
        --v01-ray-stack "$V01_RAY_STACK" \
        --v3a-synthetic "$V3A_SYNTHETIC" \
        --v3a-adapter "$V3A_ADAPTER" \
        --output "$SFT_OUTPUT" \
        --execute
else
    echo "[3/5] LoRA adapter exists at $SFT_OUTPUT/lora-adapter — skipping train."
fi

# --- 4. GGUF conversion ---
MERGED_DIR="$SFT_OUTPUT/merged"

if [ ! -f "$GGUF_OUTPUT/hammerstein-7b-v023-q5_k_m.gguf" ]; then
    echo ""
    echo "[4/5] Converting merged model to GGUF Q5_K_M..."

    if [ ! -f "$MERGED_DIR/config.json" ]; then
        echo "ERROR: Merged model not found at $MERGED_DIR — train step didn't complete."
        exit 1
    fi

    # Disk-cleanup pass before GGUF conversion. The merged model + F16 GGUF
    # + base model + llama.cpp + trainer checkpoints together can blow past
    # a 40GB container disk. Drop the trainer-checkpoints we no longer
    # need (the saved LoRA adapter is the artifact, not the checkpoints).
    echo "      Cleaning trainer checkpoints to free disk..."
    rm -rf "$SFT_OUTPUT/trainer-checkpoints" 2>/dev/null || true
    df -h /workspace | tail -2

    if [ ! -d /workspace/llama.cpp ]; then
        echo "      Cloning llama.cpp..."
        git clone --depth 1 https://github.com/ggerganov/llama.cpp.git /workspace/llama.cpp
        pip install -q -r /workspace/llama.cpp/requirements.txt 2>/dev/null || true
    fi

    GGUF_F16="$GGUF_OUTPUT/model-f16.gguf"
    GGUF_Q5="$GGUF_OUTPUT/hammerstein-7b-v023-q5_k_m.gguf"

    if [ ! -f "$GGUF_F16" ] && [ ! -f "$GGUF_Q5" ]; then
        echo "      HF -> GGUF F16..."
        python /workspace/llama.cpp/convert_hf_to_gguf.py \
            "$MERGED_DIR" \
            --outtype f16 \
            --outfile "$GGUF_F16"
    fi

    if [ -f "$GGUF_F16" ] && [ ! -f "$GGUF_Q5" ]; then
        echo "      F16 -> Q5_K_M..."
        QUANTIZE_BIN=""
        for cand in /workspace/llama.cpp/build/bin/llama-quantize /workspace/llama.cpp/llama-quantize; do
            [ -f "$cand" ] && QUANTIZE_BIN="$cand" && break
        done

        if [ -z "$QUANTIZE_BIN" ]; then
            echo "      Building llama-quantize via cmake..."
            apt-get install -y cmake 2>/dev/null || pip install -q cmake
            cmake -B /workspace/llama.cpp/build -S /workspace/llama.cpp \
                -DGGML_CUDA=OFF -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
            cmake --build /workspace/llama.cpp/build --config Release \
                --target llama-quantize -j$(nproc) 2>&1 | tail -10
            QUANTIZE_BIN=/workspace/llama.cpp/build/bin/llama-quantize
        fi

        "$QUANTIZE_BIN" "$GGUF_F16" "$GGUF_Q5" Q5_K_M
        rm -f "$GGUF_F16"  # save disk
        echo "      GGUF Q5_K_M written to $GGUF_Q5"
    fi
else
    echo "[4/5] GGUF exists — skipping."
fi

# --- 5. Package ---
echo ""
echo "[5/5] Packaging artifacts for scp..."

if [ -d "$SFT_OUTPUT/lora-adapter" ] && [ ! -f "$SFT_OUTPUT/lora-adapter-v023.tar.gz" ]; then
    tar -czf "$SFT_OUTPUT/lora-adapter-v023.tar.gz" -C "$SFT_OUTPUT" lora-adapter
fi

if [ -f "$GGUF_OUTPUT/hammerstein-7b-v023-q5_k_m.gguf" ] && [ ! -f "$GGUF_OUTPUT/model-v023.tar.gz" ]; then
    tar -czf "$GGUF_OUTPUT/model-v023.tar.gz" -C "$GGUF_OUTPUT" hammerstein-7b-v023-q5_k_m.gguf
fi

echo ""
echo "=== v0.2.3 training complete ==="
date
echo ""
echo "Files to scp back to home PC:"
echo "  $SFT_OUTPUT/lora-adapter-v023.tar.gz   <- continued LoRA adapter (~300 MB)"
echo "  $GGUF_OUTPUT/model-v023.tar.gz         <- Q5_K_M GGUF (~5 GB; load into Ollama)"
echo ""
echo "Deploy to homelab:"
echo "  scp the .gguf to D:\\hammerstein-store\\models\\v0.2.3\\"
echo "  Update deploy/Modelfile.v023 to point at the new GGUF"
echo "  ollama create hammerstein-7b-v023 -f deploy/Modelfile.v023"
echo "  Run: python scripts/v023_self_state_probe.py --model hammerstein-7b-v023 --tag v023-post-train"
echo "  Run: python scripts/v2_eval_failure_modes.py --model hammerstein-7b-v023 --tag v023-post-train"
echo "  Compare to v0.2.2 baselines."
echo ""
echo "STOP THE POD in the RunPod dashboard once scp is done."
