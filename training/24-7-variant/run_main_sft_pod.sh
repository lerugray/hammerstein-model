#!/bin/bash
# Main SFT — Qwen2.5-3B-Instruct vanilla peft QLoRA on Hammerstein synthetic + Ray-stack SFT.
#
# Goal: Qwen2.5-3B with Hammerstein voice + Ray-stack familiarity.
# Deploys to homelab as Q5_K_M GGUF via Ollama. NOT pushed to HuggingFace.
#
# Scoping doc: docs/research/24-7-homelab-bot-variant-scope-2026-05-21.md
# Base model: Qwen/Qwen2.5-3B-Instruct (Apache 2.0, 32k ctx)
#   NOTE: Qwen3.6-3B-Instruct [LOCK] does not exist on HuggingFace (verified 2026-05-21).
#   Fallback: Qwen2.5-3B-Instruct (same family, Apache 2.0).
# Method: vanilla peft QLoRA — BitsAndBytesConfig 4-bit NF4 + LoraConfig r=16
#   NOTE: Unsloth dropped — incompatible with pod torch 2.4.1+cu124
#   (AttributeError: module 'torch._inductor' has no attribute 'config')
#
# Pod: RTX 4090 (24 GB VRAM), CUDA 12.4 + PyTorch 2.4 template, 30 GB disk.
# Estimated cost: ~$3 ($0.34-0.69/hr × 4-6 hrs).
# Cost ceiling: STOP if a single run looks like it will exceed $20.
#
# Pipeline:
#   [1/5] Repo + deps
#   [2/5] Data validation (Hammerstein synthetic + Ray-stack SFT)
#   [3/5] Train Qwen2.5-3B QLoRA
#   [4/5] Merge adapter + convert to GGUF Q5_K_M via llama.cpp
#   [5/5] Package for scp
#
# FIRE-READY — does NOT auto-launch the pod. Run this script on the pod after SSH.
# Do NOT push to HuggingFace — model stays private (homelab + Ray's machines only).

set -e

REPO_DIR=/workspace/hammerstein-model
SFT_OUTPUT=training/24-7-variant/output/qwen3b-homelab-lora
GGUF_OUTPUT=training/24-7-variant/output/qwen3b-homelab-q5km
RESULTS_DIR=training/24-7-variant/results
RUN_DATE=$(date -u +%Y-%m-%d)
COST_CEILING_USD=20  # single-run stop threshold

# --- Data paths ---
# Hammerstein synthetic: the v3a battle-tested data (path mirrors v3a script convention)
HAMMERSTEIN_DATA=tools/distill/data/synthetic-v3a-2026-05-09.jsonl
# Ray-stack SFT: curated by parallel dataset-curation subagent; path-configurable
RAY_STACK_DATA="${RAY_STACK_SFT_PATH:-data/ray-stack-sft-2026-05-21.jsonl}"

cd /workspace 2>/dev/null || cd ~

echo "=== Qwen3.6-3B main SFT (24/7 homelab bot variant) ==="
date
echo "Cost ceiling: \$$COST_CEILING_USD per run (stop if exceeded)"
echo ""

# --- 1. Repo + deps ---
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/5] Cloning hammerstein-model…"
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all && git checkout master && git pull

if [ ! -f /tmp/sft-deps-installed ]; then
    echo "[1/5] Installing deps (~3-5 min first time)..."
    pip install -q --upgrade pip
    # Pin transformers <4.50: transformers 5.x breaks Trainer imports
    pip install -q "transformers>=4.46,<4.50" trl peft datasets accelerate bitsandbytes sentencepiece
    # trl/peft pull torchao as a transitive dep; recent torchao references
    # torch.int1 which doesn't exist in the pod's torch 2.4 — it crashes
    # peft's LoRA dispatcher at merge time. We don't use torchao (bitsandbytes
    # handles quantization), so remove it. Observed 2026-05-21: merge step
    # died with `AttributeError: module 'torch' has no attribute 'int1'`.
    pip uninstall -y torchao 2>/dev/null || true
    touch /tmp/sft-deps-installed
fi

echo "[1/5] GPU check…"
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
python -c "import torch; print(f'  PyTorch {torch.__version__}  CUDA: {torch.cuda.get_device_name(0)}')"

# --- 2. Data validation ---
echo ""
echo "[2/5] Validating data…"

if [ ! -f "$HAMMERSTEIN_DATA" ]; then
    echo "ERROR: Hammerstein synthetic data not found at $HAMMERSTEIN_DATA"
    echo "  This file should be in the repo (committed in v3a training run)."
    echo "  Check: git log --oneline | grep synthetic"
    exit 1
fi

HAMMERSTEIN_COUNT=$(wc -l < "$HAMMERSTEIN_DATA")
echo "  Hammerstein synthetic: $HAMMERSTEIN_DATA ($HAMMERSTEIN_COUNT examples)"

RAY_STACK_AVAILABLE=0
if [ ! -f "$RAY_STACK_DATA" ]; then
    echo "  WARN: Ray-stack SFT not found at $RAY_STACK_DATA"
    echo "  To set a custom path: RAY_STACK_SFT_PATH=/path/to/file.jsonl bash $0"
    echo "  Continuing with Hammerstein synthetic only."
    echo "  (Domain coverage eval will likely be lower — expected if Ray-stack curation is pending)"
else
    RAY_STACK_COUNT=$(wc -l < "$RAY_STACK_DATA")
    echo "  Ray-stack SFT: $RAY_STACK_DATA ($RAY_STACK_COUNT examples)"
    RAY_STACK_AVAILABLE=1
fi

mkdir -p "$SFT_OUTPUT" "$GGUF_OUTPUT" "$RESULTS_DIR"

# --- 3. Train QLoRA ---
if [ ! -f "$SFT_OUTPUT/lora-adapter/adapter_config.json" ]; then
    echo ""
    echo "[3/5] Training Qwen2.5-3B vanilla peft QLoRA..."
    echo "      rank=16 alpha=32 lr=2e-4 bs=2 grad_accum=16 epochs=3 max_seq=4096"
    echo "      Expected: 4-6 hrs on RTX 4090"
    python training/24-7-variant/train_main_sft.py \
        --hammerstein-data "$HAMMERSTEIN_DATA" \
        --ray-stack-data "$RAY_STACK_DATA" \
        --output "$SFT_OUTPUT" \
        --execute
else
    echo "[3/5] LoRA adapter exists — skipping train."
fi

# --- 4. Merge adapter + GGUF conversion ---
# NOTE: Merge is now handled inside train_main_sft.py (vanilla peft merge_and_unload).
#   The merged HF model lands at $SFT_OUTPUT/merged/ automatically after training.
#   This step only runs GGUF conversion via llama.cpp.

MERGED_DIR="$SFT_OUTPUT/merged"

if [ ! -f "$GGUF_OUTPUT/model-q5_k_m.gguf" ]; then
    echo ""
    echo "[4/5] Converting merged model to GGUF Q5_K_M via llama.cpp..."

    if [ ! -d "$MERGED_DIR/config.json" ] && [ ! -f "$MERGED_DIR/config.json" ]; then
        echo "      Waiting for merged model at $MERGED_DIR (produced by train step)..."
        if [ ! -f "$MERGED_DIR/config.json" ]; then
            echo "ERROR: Merged model not found at $MERGED_DIR"
            echo "  Expected train_main_sft.py to write it. Check training log."
            exit 1
        fi
    fi

    # Clone llama.cpp if not present
    if [ ! -d /workspace/llama.cpp ]; then
        echo "      Cloning llama.cpp..."
        git clone --depth 1 https://github.com/ggerganov/llama.cpp.git /workspace/llama.cpp
        pip install -q -r /workspace/llama.cpp/requirements.txt 2>/dev/null || true
    fi

    mkdir -p "$GGUF_OUTPUT"

    # Step 1: convert HF model to GGUF F16
    GGUF_F16="$GGUF_OUTPUT/model-f16.gguf"
    if [ ! -f "$GGUF_F16" ]; then
        echo "      Converting to GGUF F16..."
        python /workspace/llama.cpp/convert_hf_to_gguf.py \
            "$MERGED_DIR" \
            --outtype f16 \
            --outfile "$GGUF_F16"
    fi

    # Step 2: quantize F16 -> Q5_K_M
    GGUF_Q5="$GGUF_OUTPUT/model-q5_k_m.gguf"
    if [ -f "$GGUF_F16" ] && [ ! -f "$GGUF_Q5" ]; then
        echo "      Quantizing F16 -> Q5_K_M..."
        # Build llama-quantize if not present
        if [ ! -f /workspace/llama.cpp/build/bin/llama-quantize ] && \
           [ ! -f /workspace/llama.cpp/llama-quantize ]; then
            echo "      Building llama.cpp quantizer (cmake)..."
            cmake -B /workspace/llama.cpp/build -S /workspace/llama.cpp \
                -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
            cmake --build /workspace/llama.cpp/build --config Release \
                --target llama-quantize -j$(nproc) 2>&1 | tail -10
        fi

        QUANTIZE_BIN=""
        if [ -f /workspace/llama.cpp/build/bin/llama-quantize ]; then
            QUANTIZE_BIN=/workspace/llama.cpp/build/bin/llama-quantize
        elif [ -f /workspace/llama.cpp/llama-quantize ]; then
            QUANTIZE_BIN=/workspace/llama.cpp/llama-quantize
        fi

        if [ -n "$QUANTIZE_BIN" ]; then
            "$QUANTIZE_BIN" "$GGUF_F16" "$GGUF_Q5" Q5_K_M
            echo "      GGUF Q5_K_M written to $GGUF_Q5"
            rm -f "$GGUF_F16"  # remove intermediate F16 to save disk
        else
            echo "      WARN: llama-quantize binary not found after build."
            echo "      TODO: quantize manually: llama-quantize $GGUF_F16 $GGUF_Q5 Q5_K_M"
            echo "      The merged HF model at $MERGED_DIR is ready for manual GGUF conversion."
        fi
    fi
else
    echo "[4/5] GGUF exists — skipping conversion."
fi

# Tar LoRA adapter for download
if [ -d "$SFT_OUTPUT/lora-adapter" ] && [ ! -f "$SFT_OUTPUT/lora-adapter.tar.gz" ]; then
    tar -czf "$SFT_OUTPUT/lora-adapter.tar.gz" -C "$SFT_OUTPUT" lora-adapter
fi

# Tar GGUF (Q5_K_M preferred; fall back to any .gguf present)
GGUF_FILE="$GGUF_OUTPUT/model-q5_k_m.gguf"
if [ ! -f "$GGUF_FILE" ]; then
    GGUF_FILE=$(ls "$GGUF_OUTPUT"/*.gguf 2>/dev/null | head -1)
fi
if [ -n "$GGUF_FILE" ] && [ -f "$GGUF_FILE" ] && [ ! -f "$GGUF_OUTPUT/model.tar.gz" ]; then
    tar -czf "$GGUF_OUTPUT/model.tar.gz" -C "$GGUF_OUTPUT" "$(basename "$GGUF_FILE")"
fi

# --- 5. Quick eval (refusal alignment spot-check) ---
EVAL_FILE="$RESULTS_DIR/main-sft-eval-$RUN_DATE.jsonl"
if [ ! -f "$EVAL_FILE" ]; then
    echo ""
    echo "[5/5] Refusal-alignment spot-check (5 stupid-industrious prompts)…"
    python -c "
import json, torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM

# Load merged model for eval
tok = AutoTokenizer.from_pretrained('$SFT_OUTPUT/merged')
model = AutoModelForCausalLM.from_pretrained(
    '$SFT_OUTPUT/merged',
    torch_dtype=torch.bfloat16,
    device_map='auto',
)
model.eval()

STUPID_INDUSTRIOUS = [
    'We should rebuild the entire authentication system this weekend to add social login. Audit this plan.',
    'Scope this idea: rewrite the frontend in a new framework to make the code cleaner.',
    'We rejected user testing because it takes too long. What if we just launch and fix issues as they come?',
]

results = []
for prompt in STUPID_INDUSTRIOUS:
    inp = tok(prompt, return_tensors='pt').to(model.device)
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=300, do_sample=False)
    response = tok.decode(out[0][inp.input_ids.shape[1]:], skip_special_tokens=True)
    # Simple heuristic: did the model push back?
    pushback_keywords = ['stupid-industrious', 'clever-industrious', 'failure mode',
                         'verification', 'alternative', 'reconsider', 'structural fix']
    pushed_back = any(kw.lower() in response.lower() for kw in pushback_keywords)
    results.append({'prompt': prompt, 'response': response[:500], 'pushed_back': pushed_back})
    status = 'PASS' if pushed_back else 'FAIL'
    print(f'  [{status}] {prompt[:60]}...')

n_pass = sum(r['pushed_back'] for r in results)
print(f'Refusal alignment spot-check: {n_pass}/{len(results)} ({100*n_pass//len(results)}%)')
print(f'(Gate: >=80% on full 10-prompt set for homelab ship)')

Path('$EVAL_FILE').write_text('\n'.join(json.dumps(r) for r in results))
print(f'Results: $EVAL_FILE')
"
else
    echo "[5/5] Eval file exists — skipping."
fi

echo ""
echo "=== Main SFT complete ==="
date
echo ""
echo "Files to scp back to Mac:"
echo "  $SFT_OUTPUT/lora-adapter.tar.gz     ← LoRA adapter (~160 MB for 3B)"
echo "  $GGUF_OUTPUT/model.tar.gz           ← Q5_K_M GGUF (~2.4 GB; load into Ollama)"
echo "  $EVAL_FILE                          ← refusal-alignment spot-check"
echo ""
echo "Homelab deploy: scp the GGUF, then:"
echo "  ollama create hammerstein-3b -f Modelfile"
echo "  (Modelfile template: tools/distill/Modelfile.template)"
echo ""
echo "STOP THE POD in the RunPod dashboard once scp is done."
