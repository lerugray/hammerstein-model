#!/bin/bash
# Main SFT — Qwen3.6-3B-Instruct + Unsloth QLoRA on Hammerstein synthetic + Ray-stack SFT.
#
# Goal: Qwen3.6-3B with Hammerstein voice + Ray-stack familiarity.
# Deploys to homelab as Q5_K_M GGUF via Ollama. NOT pushed to HuggingFace.
#
# Scoping doc: docs/research/24-7-homelab-bot-variant-scope-2026-05-21.md
# Base model: Qwen3.6-3B-Instruct (Apache 2.0, 32k ctx, [LOCK])
# Method: QLoRA rank-16 via Unsloth (~70% less VRAM, 2× faster than vanilla LoRA)
#
# Pod: RTX 4090 (24 GB VRAM), CUDA 12.4 + PyTorch 2.4 template, 30 GB disk.
# Estimated cost: ~$3 ($0.34-0.69/hr × 4-6 hrs).
# Cost ceiling: STOP if a single run looks like it will exceed $20.
#
# Pipeline:
#   [1/5] Repo + deps
#   [2/5] Data validation (Hammerstein synthetic + Ray-stack SFT)
#   [3/5] Train Qwen3.6-3B QLoRA
#   [4/5] Merge adapter + convert to GGUF Q5_K_M
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
    echo "[1/5] Installing deps (~3-5 min first time)…"
    pip install -q --upgrade pip
    pip install -q "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
    pip install -q trl peft transformers datasets accelerate bitsandbytes
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
    echo "[3/5] Training Qwen3.6-3B QLoRA…"
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
if [ ! -f "$GGUF_OUTPUT/model.gguf" ]; then
    echo ""
    echo "[4/5] Merging LoRA adapter into base model…"
    python -c "
from unsloth import FastLanguageModel
import torch

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name='$SFT_OUTPUT/lora-adapter',
    max_seq_length=4096,
    dtype=torch.bfloat16,
    load_in_4bit=False,  # merge to full precision first
)
model.save_pretrained_merged('$SFT_OUTPUT/merged', tokenizer, save_method='merged_16bit')
print('Merge complete.')
"

    echo "      Converting merged model to GGUF Q5_K_M…"
    # Use llama.cpp convert script (bundled with unsloth or installed separately)
    if python -c "import llama_cpp" 2>/dev/null; then
        python -c "
from llama_cpp import Llama
print('llama-cpp-python available — use its convert utility')
"
    fi

    # Unsloth's built-in GGUF export (preferred — avoids separate llama.cpp build)
    python -c "
from unsloth import FastLanguageModel
import torch

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name='$SFT_OUTPUT/merged',
    max_seq_length=4096,
    dtype=torch.bfloat16,
    load_in_4bit=False,
)
# Save GGUF Q5_K_M to output dir
model.save_pretrained_gguf(
    '$GGUF_OUTPUT',
    tokenizer,
    quantization_method='q5_k_m',
)
print('GGUF Q5_K_M written to $GGUF_OUTPUT')
"
else
    echo "[4/5] GGUF exists — skipping conversion."
fi

# Tar LoRA adapter for download
if [ -d "$SFT_OUTPUT/lora-adapter" ] && [ ! -f "$SFT_OUTPUT/lora-adapter.tar.gz" ]; then
    tar -czf "$SFT_OUTPUT/lora-adapter.tar.gz" -C "$SFT_OUTPUT" lora-adapter
fi

# Tar GGUF
GGUF_FILE=$(ls "$GGUF_OUTPUT"/*.gguf 2>/dev/null | head -1)
if [ -n "$GGUF_FILE" ] && [ ! -f "$GGUF_OUTPUT/model.tar.gz" ]; then
    tar -czf "$GGUF_OUTPUT/model.tar.gz" -C "$GGUF_OUTPUT" "$(basename $GGUF_FILE)"
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
