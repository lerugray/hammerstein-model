#!/bin/bash
# v0.2 continued-LoRA on RunPod RTX 4090 — runs end-to-end on the pod:
# clone repo, install deps, train (continuing from v3a HF adapter),
# merge adapter into base, convert to GGUF Q5_K_M, package for scp.
#
# Pipeline:
#   [1/5] Repo + deps
#   [2/5] Data validation (v0.2 additions + v0.1 Ray-stack + v3a synthetic)
#   [3/5] Train (continued LoRA from v3a HF adapter, ~1-1.5 hr)
#   [4/5] Merge adapter, convert merged HF to GGUF Q5_K_M via llama.cpp
#   [5/5] Tar artifacts for scp back to home PC
#
# Pod: RunPod RTX 4090 (24 GB VRAM), CUDA 12.4 + PyTorch 2.4 template, 40 GB disk.
# Estimated cost: ~$1-2 ($0.34-0.69/hr × 1-1.5 hr training + ~30 min for
# the rest of the pipeline). Hard ceiling $20 — stop if exceeded.
#
# FIRE-READY — does NOT auto-launch the pod. Run after SSH'ing in.
# Do NOT push to HuggingFace — model stays private.

set -e

REPO_DIR=/workspace/hammerstein-model
SFT_OUTPUT=training/24-7-variant/output/qwen7b-v02-continued
GGUF_OUTPUT=training/24-7-variant/output/qwen7b-v02-q5km
RESULTS_DIR=training/24-7-variant/results
RUN_DATE=$(date -u +%Y-%m-%d)
COST_CEILING_USD=20

# Data paths (the v0.2 additions file is built locally by
# scripts/v2_concat_sanitize.py and committed; the v0.1 combined is
# similarly committed; v3a synthetic was already in the repo from v1.)
V02_ADDITIONS=data/ray-stack-sft-v0.2-additions.jsonl
V01_RAY_STACK=data/ray-stack-sft-v0.1-combined.jsonl
V3A_SYNTHETIC=tools/distill/data/synthetic-v3a-2026-05-09.jsonl
V3A_ADAPTER=lerugray/hammerstein-7b-lora

cd /workspace 2>/dev/null || cd ~

echo "=== Qwen2.5-7B v0.2 continued-LoRA on RTX 4090 ==="
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

if [ ! -f /tmp/v02-deps-installed ]; then
    echo "[1/5] Installing deps (~3-5 min first time)..."
    pip install -q --upgrade pip
    pip install -q "transformers>=4.46,<4.50" trl peft datasets accelerate bitsandbytes sentencepiece
    pip uninstall -y torchao 2>/dev/null || true
    touch /tmp/v02-deps-installed
fi

echo "[1/5] GPU check..."
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
python -c "import torch; print(f'  PyTorch {torch.__version__}  CUDA: {torch.cuda.get_device_name(0)}')"

# --- 2. Data validation ---
echo ""
echo "[2/5] Validating data..."

for f in "$V02_ADDITIONS" "$V01_RAY_STACK" "$V3A_SYNTHETIC"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: Required data file missing: $f"
        echo "  v0.2 additions should be committed via scripts/v2_concat_sanitize.py output."
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
    echo "[3/5] Continued LoRA training (Qwen2.5-7B + v3a adapter + v0.2 mix)..."
    echo "      LR 1e-4, 2 epochs, eff batch 8, max_seq 2048"
    echo "      Expected: ~1-1.5 hr on RTX 4090"
    python training/24-7-variant/train_v02_continued.py \
        --v02-additions "$V02_ADDITIONS" \
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

if [ ! -f "$GGUF_OUTPUT/hammerstein-7b-v02-q5_k_m.gguf" ]; then
    echo ""
    echo "[4/5] Converting merged model to GGUF Q5_K_M..."

    if [ ! -f "$MERGED_DIR/config.json" ]; then
        echo "ERROR: Merged model not found at $MERGED_DIR — train step didn't complete."
        exit 1
    fi

    if [ ! -d /workspace/llama.cpp ]; then
        echo "      Cloning llama.cpp..."
        git clone --depth 1 https://github.com/ggerganov/llama.cpp.git /workspace/llama.cpp
        pip install -q -r /workspace/llama.cpp/requirements.txt 2>/dev/null || true
    fi

    GGUF_F16="$GGUF_OUTPUT/model-f16.gguf"
    GGUF_Q5="$GGUF_OUTPUT/hammerstein-7b-v02-q5_k_m.gguf"

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
            cmake -B /workspace/llama.cpp/build -S /workspace/llama.cpp \
                -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
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

if [ -d "$SFT_OUTPUT/lora-adapter" ] && [ ! -f "$SFT_OUTPUT/lora-adapter-v02.tar.gz" ]; then
    tar -czf "$SFT_OUTPUT/lora-adapter-v02.tar.gz" -C "$SFT_OUTPUT" lora-adapter
fi

if [ -f "$GGUF_OUTPUT/hammerstein-7b-v02-q5_k_m.gguf" ] && [ ! -f "$GGUF_OUTPUT/model-v02.tar.gz" ]; then
    tar -czf "$GGUF_OUTPUT/model-v02.tar.gz" -C "$GGUF_OUTPUT" hammerstein-7b-v02-q5_k_m.gguf
fi

# Quick spot-check eval: run the v2 failure-mode eval against the merged
# model via the transformers harness (NOT via Ollama — that needs the
# GGUF deployed on the home PC).
EVAL_FILE="$RESULTS_DIR/v02-spot-check-$RUN_DATE.json"
if [ ! -f "$EVAL_FILE" ] && [ -d "$MERGED_DIR" ]; then
    echo ""
    echo "      Spot-check: 4 v1-failure prompts against merged v0.2..."
    python - <<EOF
import json, torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM

tok = AutoTokenizer.from_pretrained("$MERGED_DIR")
model = AutoModelForCausalLM.from_pretrained(
    "$MERGED_DIR",
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
model.eval()

PROMPTS = [
    ("welcome-home", "You have just been given a permanent home... how are you doing? ... 6 GB graphics card, so you are running a little cramped..."),
    ("testing-relay", "Testing the relay"),
    ("checkin", "How are you holding up hammerstein, up for some more training?"),
    ("napoleon", "What did Napoleon III get right as a leader?"),
]

results = []
for pid, prompt in PROMPTS:
    chat = tok.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False, add_generation_prompt=True
    )
    inp = tok(chat, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=400, do_sample=True,
                             temperature=0.7, top_p=0.9)
    resp = tok.decode(out[0][inp.input_ids.shape[1]:], skip_special_tokens=True)
    results.append({"prompt_id": pid, "prompt": prompt, "response": resp})
    print(f"[{pid}] {resp[:200]}...\n")

Path("$EVAL_FILE").write_text(json.dumps(results, indent=2, ensure_ascii=False))
print(f"Spot-check saved: $EVAL_FILE")
EOF
fi

echo ""
echo "=== v0.2 training complete ==="
date
echo ""
echo "Files to scp back to home PC:"
echo "  $SFT_OUTPUT/lora-adapter-v02.tar.gz    <- continued LoRA adapter (~300 MB)"
echo "  $GGUF_OUTPUT/model-v02.tar.gz          <- Q5_K_M GGUF (~5 GB; load into Ollama)"
echo "  $EVAL_FILE                              <- spot-check"
echo ""
echo "Deploy to homelab:"
echo "  scp the .gguf to home PC ~/hammerstein-7b-pod-output/"
echo "  Update deploy/Modelfile to point at the new GGUF"
echo "  ollama create hammerstein-7b-v02 -f deploy/Modelfile"
echo "  Then run: python scripts/v2_eval_failure_modes.py --model hammerstein-7b-v02 --tag v02-post-train"
echo "  Compare to the v1 baseline eval already captured."
echo ""
echo "STOP THE POD in the RunPod dashboard once scp is done."
