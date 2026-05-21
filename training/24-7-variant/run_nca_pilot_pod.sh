#!/bin/bash
# NCA pre-pre-training pilot — A/B experiment runner (OLMo-1B, bf16 full FT).
#
# USAGE
# -----
#   bash run_nca_pilot_pod.sh nca      # Arm A: 100M NCA tokens
#   bash run_nca_pilot_pod.sh control  # Arm B: 100M C4 natural-text tokens (matched budget)
#   bash run_nca_pilot_pod.sh eval     # After BOTH arms are done: compare + write RESULTS.md
#
# INTENDED INVOCATION (two pods in parallel)
# ------------------------------------------
#   Pod 1:  bash run_nca_pilot_pod.sh nca
#   Pod 2:  bash run_nca_pilot_pod.sh control
#   Then (on either pod after both are done, or locally after scp):
#           bash run_nca_pilot_pod.sh eval
#
# Running both arms in parallel halves wall-clock time vs sequential and costs
# the same total (two concurrent RTX 4090 pods at $0.34-0.69/hr each ≈ $3-5 total).
#
# A/B DESIGN
# ----------
# Goal: validate arXiv:2603.10055's 1.6× convergence speedup + reasoning lift claim.
# The ONLY variable between arms is the training data:
#   Arm A (nca):     Emergent-NCA-Sequences-5M, high-entropy rollouts filtered
#   Arm B (control): allenai/c4 "en", matched 100M token budget
# Same base checkpoint, same hyperparameters, same eval suite.
# Why C4: the MIT paper uses C4 as its baseline, so our numbers are directly
# comparable to the paper's reported results without cross-dataset translation.
#
# WHY BF16 FULL FT (no quantization, no LoRA)
# --------------------------------------------
# Pre-pre-training must update actual model weights to instill the reasoning prior
# the paper describes. bitsandbytes 4-bit loading causes:
#   ValueError: You cannot perform fine-tuning on purely quantized models.
# A 1B model is ~2 GB in bf16 — fits a 24 GB RTX 4090 comfortably.
# Optimizer state uses 8-bit AdamW (adamw_bnb_8bit in TrainingArguments) to keep
# total memory well under 24 GB without quantizing the weights themselves.
#
# Pod: RTX 4090 (24 GB VRAM), CUDA 12.4 + PyTorch 2.4 template, 30 GB disk.
# Estimated cost per arm: ~$1.50-3 ($0.34-0.69/hr × 3-5 hrs).
# Cost ceiling: STOP if a single arm run looks like it will exceed $20.
#
# Pipeline per arm:
#   [1/4] Repo + deps
#   [2/4] Train (NCA tokens or C4 tokens depending on arm)
#   [3/4] Eval (GSM8K + HumanEval spot check on this arm's checkpoint)
#   [4/4] Package checkpoint for scp
#
# After BOTH arms complete:
#   [eval mode] Load both checkpoints, compare side-by-side, write RESULTS-NCA-pilot-<date>.md
#
# FIRE-READY — does NOT auto-launch the pod. Run on the pod after SSH.
# Do NOT push model to HuggingFace — stays local/private.
#
# Ref: arXiv:2603.10055 (Han/Lee/Kumar/Agrawal, MIT CSAIL, March 2026)
# Dataset: https://huggingface.co/datasets/Tejaskumar/Emergent-NCA-Sequences-5M
# Scoping doc: docs/research/24-7-homelab-bot-variant-scope-2026-05-21.md

set -e

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

ARM="${1:-}"
if [[ "$ARM" != "nca" && "$ARM" != "control" && "$ARM" != "eval" ]]; then
    echo "ERROR: first argument must be 'nca', 'control', or 'eval'."
    echo "Usage: bash run_nca_pilot_pod.sh [nca|control|eval]"
    exit 1
fi

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_DIR=/workspace/hammerstein-model
OUTPUT_BASE=training/24-7-variant/output
RESULTS_DIR=training/24-7-variant/results
NCA_OUTPUT="${OUTPUT_BASE}/olmo-1b-nca-pilot"
CTRL_OUTPUT="${OUTPUT_BASE}/olmo-1b-control-pilot"
RUN_DATE=$(date -u +%Y-%m-%d)
COST_CEILING_USD=20  # single-arm stop threshold

cd /workspace 2>/dev/null || cd ~

echo "=== NCA pilot A/B experiment — arm=${ARM} ==="
date
echo "Cost ceiling: \$$COST_CEILING_USD per arm"
echo ""

# ---------------------------------------------------------------------------
# [1/4] Repo + deps
# ---------------------------------------------------------------------------

if [ ! -d "$REPO_DIR" ]; then
    echo "[1/4] Cloning hammerstein-model…"
    git clone https://github.com/lerugray/hammerstein-model.git
fi
cd "$REPO_DIR"
git fetch --all && git checkout master && git pull

if [ ! -f /tmp/nca-deps-installed ]; then
    echo "[1/4] Installing deps (~3-5 min first time)…"
    pip install -q --upgrade pip
    # Full FT of 1B bf16 model — no quantized model loading, so bitsandbytes is only
    # needed for 8-bit AdamW optimizer (not for model quantization).
    # Pin transformers <4.50 — newer 5.x restructures Trainer imports.
    # lm-eval pulls a conflicting transformers, so install it FIRST then pin explicitly.
    pip install -q datasets accelerate bitsandbytes evaluate lm-eval
    pip install -q --upgrade 'transformers>=4.46,<4.50'
    # NCA dataset needs scipy for .npz shard loading; pandas for CSV metadata
    pip install -q scipy scikit-learn pandas
    touch /tmp/nca-deps-installed
    echo "[1/4] Deps installed."
fi

echo "[1/4] GPU check…"
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
python -c "import torch; print(f'  PyTorch {torch.__version__}  CUDA: {torch.cuda.get_device_name(0)}')"

mkdir -p "$OUTPUT_BASE"
mkdir -p "$RESULTS_DIR"

# ---------------------------------------------------------------------------
# [2/4] Train (skipped for eval mode)
# ---------------------------------------------------------------------------

if [[ "$ARM" == "nca" || "$ARM" == "control" ]]; then
    OUTPUT_DIR="${OUTPUT_BASE}/olmo-1b-${ARM}-pilot"

    if [ ! -f "$OUTPUT_DIR/training_complete.flag" ]; then
        echo ""
        echo "[2/4] Training OLMo-1B — arm=${ARM}…"
        if [[ "$ARM" == "nca" ]]; then
            echo "      Dataset: Emergent-NCA-Sequences-5M (100M tokens, high-entropy filter)"
        else
            echo "      Dataset: allenai/c4 'en' (100M tokens, streaming — matched control)"
        fi
        echo "      Model:   allenai/OLMo-1B-hf  bf16 full FT  (no quantization)"
        echo "      Optim:   adamw_bnb_8bit  (8-bit AdamW — keeps optimizer memory ≤2 GB)"
        echo "      Expected: 3-5 hrs on RTX 4090"
        python training/24-7-variant/train_nca_pilot.py \
            --arm "$ARM" \
            --output-base "$OUTPUT_BASE" \
            --results-dir "$RESULTS_DIR" \
            --execute
    else
        echo "[2/4] Checkpoint exists for arm=${ARM} — skipping train."
    fi
fi

# ---------------------------------------------------------------------------
# [3/4] Single-arm spot eval
# ---------------------------------------------------------------------------

if [[ "$ARM" == "nca" || "$ARM" == "control" ]]; then
    OUTPUT_DIR="${OUTPUT_BASE}/olmo-1b-${ARM}-pilot"
    SPOT_EVAL_FILE="$RESULTS_DIR/spot_eval_${ARM}_${RUN_DATE}.jsonl"

    if [ ! -f "$SPOT_EVAL_FILE" ] && [ -f "$OUTPUT_DIR/training_complete.flag" ]; then
        echo ""
        echo "[3/4] Spot eval on arm=${ARM} checkpoint…"
        python -c "
import json, torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM

checkpoint = Path('$OUTPUT_DIR')
print(f'Loading checkpoint: {checkpoint}')
tok = AutoTokenizer.from_pretrained(str(checkpoint), trust_remote_code=True)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token
model = AutoModelForCausalLM.from_pretrained(
    str(checkpoint),
    torch_dtype=torch.bfloat16,
    device_map='auto',
    trust_remote_code=True,
)
model.eval()

problems = [
    ('Janet sells 16 dozen eggs per week. How many eggs in 4 weeks?', '768'),
    ('3 times apples as oranges; 48 total. How many oranges?', '12'),
]
results = []
for q, expected in problems:
    prompt = f'### Problem\n{q}\n\n### Solution\n'
    inputs = tok(prompt, return_tensors='pt').to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=150, do_sample=False,
                              pad_token_id=tok.pad_token_id)
    answer = tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    results.append({'arm': '$ARM', 'question': q, 'expected': expected, 'answer': answer.strip()[:200]})
    print(f'  Q: {q}')
    print(f'  A: {answer[:100]}')

Path('$SPOT_EVAL_FILE').write_text('\n'.join(json.dumps(r) for r in results))
print(f'Spot eval written to $SPOT_EVAL_FILE')
"
    else
        echo "[3/4] Spot eval exists or checkpoint not ready — skipping."
    fi
fi

# ---------------------------------------------------------------------------
# [3b/4] Full A/B comparison eval (eval mode only — runs after BOTH arms done)
# ---------------------------------------------------------------------------

if [[ "$ARM" == "eval" ]]; then
    echo ""
    echo "[3/4] Running full A/B comparison eval…"
    echo "      Requires both arm checkpoints to be present."
    echo "      Writes RESULTS-NCA-pilot-${RUN_DATE}.md"
    python -c "
import sys
sys.argv = ['train_nca_pilot.py', '--arm', 'nca']  # placeholder; eval mode doesn't use arm
from pathlib import Path
import importlib.util, types

# Load the training module directly and call run_eval
spec = importlib.util.spec_from_file_location(
    'train_nca_pilot',
    'training/24-7-variant/train_nca_pilot.py'
)
mod = importlib.util.load_from_spec(spec)  # type: ignore
spec.loader.exec_module(mod)
mod.run_eval(
    Path('$RESULTS_DIR'),
    Path('$OUTPUT_BASE'),
)
"
    # Fallback if import trick fails — call as subprocess
    if [ $? -ne 0 ]; then
        echo "  (module import failed — running via subprocess)"
        python - <<'PYEOF'
import sys
sys.path.insert(0, "training/24-7-variant")
from pathlib import Path
# Inline the eval call since module import path may vary on the pod
exec(open("training/24-7-variant/train_nca_pilot.py").read())
run_eval(Path("training/24-7-variant/results"), Path("training/24-7-variant/output"))
PYEOF
    fi
fi

# ---------------------------------------------------------------------------
# [4/4] Package checkpoint for scp
# ---------------------------------------------------------------------------

if [[ "$ARM" == "nca" || "$ARM" == "control" ]]; then
    OUTPUT_DIR="${OUTPUT_BASE}/olmo-1b-${ARM}-pilot"
    TAR_OUT="${OUTPUT_DIR}/checkpoint_${ARM}.tar.gz"

    if [ -d "$OUTPUT_DIR" ] && [ ! -f "$TAR_OUT" ] && [ -f "$OUTPUT_DIR/training_complete.flag" ]; then
        echo ""
        echo "[4/4] Packaging checkpoint for download (arm=${ARM})…"
        tar -czf "$TAR_OUT" -C "$(dirname $OUTPUT_DIR)" "$(basename $OUTPUT_DIR)" \
            --exclude="$(basename $OUTPUT_DIR)/checkpoint_${ARM}.tar.gz"
        echo "  Packaged: $TAR_OUT"
    fi
fi

echo ""
echo "=== arm=${ARM} complete ==="
date
echo ""
if [[ "$ARM" == "nca" || "$ARM" == "control" ]]; then
    OUTPUT_DIR="${OUTPUT_BASE}/olmo-1b-${ARM}-pilot"
    echo "Files to scp back:"
    echo "  ${OUTPUT_DIR}/checkpoint_${ARM}.tar.gz    ← trained checkpoint"
    echo "  ${RESULTS_DIR}/loss_curve_${ARM}.jsonl    ← per-step loss curve"
    echo "  ${RESULTS_DIR}/spot_eval_${ARM}_${RUN_DATE}.jsonl  ← spot eval"
    echo ""
    echo "NEXT: When BOTH pods are done, run:"
    echo "  bash run_nca_pilot_pod.sh eval"
    echo "to generate the side-by-side RESULTS-NCA-pilot-${RUN_DATE}.md."
fi
if [[ "$ARM" == "eval" ]]; then
    echo "Results at: ${RESULTS_DIR}/RESULTS-NCA-pilot-${RUN_DATE}.md"
fi
echo ""
echo "STOP THE POD in the RunPod dashboard once scp is done."
