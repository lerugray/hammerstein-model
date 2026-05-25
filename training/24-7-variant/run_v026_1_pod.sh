#!/bin/bash
# v0.2.6.1 continued-LoRA on RunPod — iteration on v0.2.6 targeting the
# five post-train failure modes identified in commit 4d7f051.
#
# Pipeline:
#   [1/5] Repo + deps
#   [2/5] Data validation (v0.2.6.1 additions + v0.1 Ray-stack + v3a synthetic)
#   [3/5] Train (continued LoRA from v3a HF adapter, ~38 min)
#   [4/5] Merge adapter, convert merged HF to GGUF Q5_K_M via llama.cpp
#   [5/5] Push GGUF + LoRA tar to private HF repo for home-PC pull
#
# Pod: RunPod A5000 SECURE (24 GB VRAM) or RTX 4090, CUDA 12.4 + PyTorch
# 2.4 template, 80 GB container disk. Estimated cost: ~$0.90 ($0.34/hr × ~1.5 hr).
# Hard ceiling $20.

set -e

REPO_DIR=/workspace/hammerstein-model
SFT_OUTPUT=training/24-7-variant/output/qwen7b-v026-1-continued
GGUF_OUTPUT=training/24-7-variant/output/qwen7b-v026-1-q5km
RESULTS_DIR=training/24-7-variant/results
RUN_DATE=$(date -u +%Y-%m-%d)
COST_CEILING_USD=20

V026_1_ADDITIONS=data/ray-stack-sft-v0.2.6.1-additions.jsonl
V01_RAY_STACK=data/ray-stack-sft-v0.1-combined.jsonl
V3A_SYNTHETIC=tools/distill/data/synthetic-v3a-2026-05-09.jsonl
V3A_ADAPTER=lerugray/hammerstein-7b-lora

cd /workspace 2>/dev/null || cd ~

echo "=== Qwen2.5-7B v0.2.6.1 continued-LoRA ==="
date
echo "Cost ceiling: \$$COST_CEILING_USD (stop if exceeded)"
echo ""

# --- 1. Repo + deps ---
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/5] Cloning hammerstein-model..."
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all && git checkout v0.2.6-retrain && git pull origin v0.2.6-retrain

if [ ! -f /tmp/v026-1-deps-installed ]; then
    echo "[1/5] Installing deps (~3-5 min first time)..."
    pip install -q --upgrade pip
    pip install -q "transformers>=4.46,<4.50" trl peft datasets accelerate bitsandbytes sentencepiece
    pip uninstall -y torchao 2>/dev/null || true
    touch /tmp/v026-1-deps-installed
fi

echo "[1/5] GPU check..."
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
python -c "import torch; print(f'  PyTorch {torch.__version__}  CUDA: {torch.cuda.get_device_name(0)}')"

# --- 2. Data validation ---
echo ""
echo "[2/5] Validating data..."

for f in "$V026_1_ADDITIONS" "$V01_RAY_STACK" "$V3A_SYNTHETIC"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: Required data file missing: $f"
        exit 1
    fi
    count=$(wc -l < "$f")
    echo "  $f  ($count lines)"
done

mkdir -p "$SFT_OUTPUT" "$GGUF_OUTPUT" "$RESULTS_DIR"

# --- 3. Train ---
if [ ! -f "$SFT_OUTPUT/lora-adapter/adapter_config.json" ]; then
    echo ""
    echo "[3/5] Continued LoRA training (Qwen2.5-7B + v3a adapter + v0.2.6.1 mix)..."
    echo "      LR 2e-4, 2 epochs, eff batch 8, max_seq 2048"
    echo "      Expected: ~38 min on A5000 / RTX 4090"
    python training/24-7-variant/train_v026_1_continued.py \
        --v026-1-additions "$V026_1_ADDITIONS" \
        --iter-anti-leakage "data/v0.2.6.1-anti-tool-leakage-additions.jsonl" \
        --iter-anti-refusal "data/v0.2.6.1-anti-refusal-empathy-additions.jsonl" \
        --iter-joey-anchor "data/v0.2.6.1-joey-anchor-additions.jsonl" \
        --iter-extraction "data/v0.2.6.1-extraction-low-signal-additions.jsonl" \
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

if [ ! -f "$GGUF_OUTPUT/hammerstein-7b-v026-1-q5_k_m.gguf" ]; then
    echo ""
    echo "[4/5] Converting merged model to GGUF Q5_K_M..."

    if [ ! -f "$MERGED_DIR/config.json" ]; then
        echo "ERROR: Merged model not found at $MERGED_DIR — train step didn't complete."
        exit 1
    fi

    echo "      Cleaning trainer checkpoints to free disk..."
    rm -rf "$SFT_OUTPUT/trainer-checkpoints" 2>/dev/null || true
    df -h /workspace | tail -2

    if [ ! -d /workspace/llama.cpp ]; then
        echo "      Cloning llama.cpp..."
        git clone --depth 1 https://github.com/ggerganov/llama.cpp.git /workspace/llama.cpp
        pip install -q -r /workspace/llama.cpp/requirements.txt 2>/dev/null || true
    fi

    GGUF_F16="$GGUF_OUTPUT/model-f16.gguf"
    GGUF_Q5="$GGUF_OUTPUT/hammerstein-7b-v026-1-q5_k_m.gguf"

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
        rm -f "$GGUF_F16"
        echo "      GGUF Q5_K_M written to $GGUF_Q5"
    fi
else
    echo "[4/5] GGUF exists — skipping."
fi

# --- 5. Push GGUF to HuggingFace (private repo) ---
echo ""
echo "[5/5] Pushing GGUF to HuggingFace private repo..."

if [ -z "$HF_TOKEN" ] && [ -f /workspace/.hf_token ]; then
    export HF_TOKEN="$(cat /workspace/.hf_token)"
fi
if [ -z "$HF_REPO_ID" ] && [ -f /workspace/.hf_repo_id ]; then
    export HF_REPO_ID="$(cat /workspace/.hf_repo_id)"
fi
HF_REPO_ID="${HF_REPO_ID:-lerugray/hammerstein-7b-v026-1}"

if [ -z "$HF_TOKEN" ]; then
    echo "ERROR: HF_TOKEN not set and /workspace/.hf_token not present."
    exit 1
fi

if [ ! -f "$GGUF_OUTPUT/hammerstein-7b-v026-1-q5_k_m.gguf" ]; then
    echo "ERROR: GGUF not found at $GGUF_OUTPUT — train+convert step didn't complete."
    exit 1
fi

pip install -q --upgrade "huggingface_hub>=0.23" 2>&1 | tail -2

python <<PYEOF
import os, sys, hashlib
from huggingface_hub import HfApi, create_repo

token = os.environ["HF_TOKEN"]
repo_id = "$HF_REPO_ID"
gguf_path = "$GGUF_OUTPUT/hammerstein-7b-v026-1-q5_k_m.gguf"
adapter_path = "$SFT_OUTPUT/lora-adapter-v026-1.tar.gz"

api = HfApi(token=token)
create_repo(repo_id, repo_type="model", private=True, exist_ok=True, token=token)
print(f"Repo ready: {repo_id} (private)")

def sha256(p, bs=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            chunk = f.read(bs)
            if not chunk: break
            h.update(chunk)
    return h.hexdigest()

import subprocess
if not os.path.exists(adapter_path):
    subprocess.run(["tar", "-czf", adapter_path, "-C", "$SFT_OUTPUT", "lora-adapter"], check=True)

print("Computing local sha256...")
local_hash = sha256(gguf_path)
print(f"  GGUF sha256: {local_hash}")

with open("/workspace/v026-1-hf-upload-meta.txt", "w") as f:
    f.write(f"repo_id={repo_id}\n")
    f.write(f"gguf_sha256={local_hash}\n")
    f.write(f"gguf_size={os.path.getsize(gguf_path)}\n")

print(f"Uploading GGUF ({os.path.getsize(gguf_path)/1e9:.2f} GB) to {repo_id}...")
api.upload_file(
    path_or_fileobj=gguf_path,
    path_in_repo="hammerstein-7b-v026-1-q5_k_m.gguf",
    repo_id=repo_id,
    repo_type="model",
    token=token,
)
print("GGUF uploaded.")

print(f"Uploading LoRA adapter tar ({os.path.getsize(adapter_path)/1e6:.1f} MB)...")
api.upload_file(
    path_or_fileobj=adapter_path,
    path_in_repo="lora-adapter-v026-1.tar.gz",
    repo_id=repo_id,
    repo_type="model",
    token=token,
)
print("Adapter tar uploaded.")

with open("/workspace/v026-1-hf-upload-done", "w") as f:
    f.write(f"DONE\nrepo_id={repo_id}\ngguf_sha256={local_hash}\n")
print("Upload complete. Sentinel: /workspace/v026-1-hf-upload-done")
PYEOF

echo ""
echo "=== v0.2.6.1 training + HF upload complete ==="
date
echo ""
echo "Artifact (private repo): $HF_REPO_ID"
