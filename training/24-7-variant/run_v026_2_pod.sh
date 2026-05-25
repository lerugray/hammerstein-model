#!/bin/bash
# v0.2.6.2 continued-LoRA on RunPod — iteration on v0.2.6.1 targeting
# meta-leakage + persistent low-signal extraction regression.
set -e

REPO_DIR=/workspace/hammerstein-model
SFT_OUTPUT=training/24-7-variant/output/qwen7b-v026-2-continued
GGUF_OUTPUT=training/24-7-variant/output/qwen7b-v026-2-q5km
RESULTS_DIR=training/24-7-variant/results
COST_CEILING_USD=20

V026_2_ADDITIONS=data/ray-stack-sft-v0.2.6.2-additions.jsonl
V01_RAY_STACK=data/ray-stack-sft-v0.1-combined.jsonl
V3A_SYNTHETIC=tools/distill/data/synthetic-v3a-2026-05-09.jsonl
V3A_ADAPTER=lerugray/hammerstein-7b-lora

cd /workspace 2>/dev/null || cd ~

echo "=== Qwen2.5-7B v0.2.6.2 continued-LoRA ==="
date
echo "Cost ceiling: \$$COST_CEILING_USD"
echo ""

if [ ! -d "$REPO_DIR" ]; then
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all && git checkout v0.2.6-retrain && git pull origin v0.2.6-retrain

if [ ! -f /tmp/v026-2-deps-installed ]; then
    echo "[1/5] Installing deps..."
    pip install -q --upgrade pip
    pip install -q "transformers>=4.46,<4.50" trl peft datasets accelerate bitsandbytes sentencepiece
    pip uninstall -y torchao 2>/dev/null || true
    touch /tmp/v026-2-deps-installed
fi

echo "[1/5] GPU check..."
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
python -c "import torch; print(f'  PyTorch {torch.__version__}  CUDA: {torch.cuda.get_device_name(0)}')"

echo ""
echo "[2/5] Validating data..."
for f in "$V026_2_ADDITIONS" "$V01_RAY_STACK" "$V3A_SYNTHETIC"; do
    if [ ! -f "$f" ]; then echo "ERROR: missing $f"; exit 1; fi
    echo "  $f  ($(wc -l < "$f") lines)"
done

mkdir -p "$SFT_OUTPUT" "$GGUF_OUTPUT" "$RESULTS_DIR"

if [ ! -f "$SFT_OUTPUT/lora-adapter/adapter_config.json" ]; then
    echo ""
    echo "[3/5] Continued LoRA training (v0.2.6.2)..."
    python training/24-7-variant/train_v026_2_continued.py \
        --v026-2-additions "$V026_2_ADDITIONS" \
        --iter-anti-meta "data/v0.2.6.2-anti-meta-leakage-additions.jsonl" \
        --iter-extraction "data/v0.2.6.2-extraction-low-signal-reinforcement.jsonl" \
        --v01-ray-stack "$V01_RAY_STACK" \
        --v3a-synthetic "$V3A_SYNTHETIC" \
        --v3a-adapter "$V3A_ADAPTER" \
        --output "$SFT_OUTPUT" \
        --execute
else
    echo "[3/5] LoRA adapter exists — skipping train."
fi

MERGED_DIR="$SFT_OUTPUT/merged"

if [ ! -f "$GGUF_OUTPUT/hammerstein-7b-v026-2-q5_k_m.gguf" ]; then
    echo ""
    echo "[4/5] Converting merged model to GGUF Q5_K_M..."
    if [ ! -f "$MERGED_DIR/config.json" ]; then echo "ERROR: merged missing"; exit 1; fi

    echo "      Cleaning trainer checkpoints..."
    rm -rf "$SFT_OUTPUT/trainer-checkpoints" 2>/dev/null || true
    df -h /workspace | tail -2

    if [ ! -d /workspace/llama.cpp ]; then
        git clone --depth 1 https://github.com/ggerganov/llama.cpp.git /workspace/llama.cpp
        pip install -q -r /workspace/llama.cpp/requirements.txt 2>/dev/null || true
    fi

    GGUF_F16="$GGUF_OUTPUT/model-f16.gguf"
    GGUF_Q5="$GGUF_OUTPUT/hammerstein-7b-v026-2-q5_k_m.gguf"

    if [ ! -f "$GGUF_F16" ] && [ ! -f "$GGUF_Q5" ]; then
        python /workspace/llama.cpp/convert_hf_to_gguf.py "$MERGED_DIR" --outtype f16 --outfile "$GGUF_F16"
    fi

    if [ -f "$GGUF_F16" ] && [ ! -f "$GGUF_Q5" ]; then
        QUANTIZE_BIN=""
        for cand in /workspace/llama.cpp/build/bin/llama-quantize /workspace/llama.cpp/llama-quantize; do
            [ -f "$cand" ] && QUANTIZE_BIN="$cand" && break
        done

        if [ -z "$QUANTIZE_BIN" ]; then
            apt-get install -y cmake 2>/dev/null || pip install -q cmake
            cmake -B /workspace/llama.cpp/build -S /workspace/llama.cpp -DGGML_CUDA=OFF -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
            cmake --build /workspace/llama.cpp/build --config Release --target llama-quantize -j$(nproc) 2>&1 | tail -10
            QUANTIZE_BIN=/workspace/llama.cpp/build/bin/llama-quantize
        fi

        "$QUANTIZE_BIN" "$GGUF_F16" "$GGUF_Q5" Q5_K_M
        rm -f "$GGUF_F16"
    fi
fi

echo ""
echo "[5/5] Pushing GGUF to HF private repo..."

if [ -z "$HF_TOKEN" ] && [ -f /workspace/.hf_token ]; then export HF_TOKEN="$(cat /workspace/.hf_token)"; fi
if [ -z "$HF_REPO_ID" ] && [ -f /workspace/.hf_repo_id ]; then export HF_REPO_ID="$(cat /workspace/.hf_repo_id)"; fi
HF_REPO_ID="${HF_REPO_ID:-lerugray/hammerstein-7b-v026-2}"

if [ -z "$HF_TOKEN" ]; then echo "ERROR: HF_TOKEN not set"; exit 1; fi
if [ ! -f "$GGUF_OUTPUT/hammerstein-7b-v026-2-q5_k_m.gguf" ]; then echo "ERROR: GGUF missing"; exit 1; fi

pip install -q --upgrade "huggingface_hub>=0.23" 2>&1 | tail -2

python <<PYEOF
import os, hashlib
from huggingface_hub import HfApi, create_repo

token = os.environ["HF_TOKEN"]
repo_id = "$HF_REPO_ID"
gguf_path = "$GGUF_OUTPUT/hammerstein-7b-v026-2-q5_k_m.gguf"
adapter_path = "$SFT_OUTPUT/lora-adapter-v026-2.tar.gz"

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

with open("/workspace/v026-2-hf-upload-meta.txt", "w") as f:
    f.write(f"repo_id={repo_id}\n")
    f.write(f"gguf_sha256={local_hash}\n")

print(f"Uploading GGUF ({os.path.getsize(gguf_path)/1e9:.2f} GB)...")
api.upload_file(path_or_fileobj=gguf_path, path_in_repo="hammerstein-7b-v026-2-q5_k_m.gguf",
                repo_id=repo_id, repo_type="model", token=token)
print("GGUF uploaded.")

print(f"Uploading LoRA adapter tar...")
api.upload_file(path_or_fileobj=adapter_path, path_in_repo="lora-adapter-v026-2.tar.gz",
                repo_id=repo_id, repo_type="model", token=token)
print("Adapter uploaded.")

with open("/workspace/v026-2-hf-upload-done", "w") as f:
    f.write(f"DONE\nrepo_id={repo_id}\ngguf_sha256={local_hash}\n")
print("Sentinel: /workspace/v026-2-hf-upload-done")
PYEOF

echo ""
echo "=== v0.2.6.2 training + HF upload complete ==="
date
