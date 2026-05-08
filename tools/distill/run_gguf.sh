#!/bin/bash
# Single-paste GGUF conversion run for the RunPod pod.
#
# Bootstrap (the curl itself needs auth since the repo is private):
#   export GH_TOKEN=github_pat_xxx_or_gho_xxx
#   export HF_TOKEN=hf_xxx
#   curl -sL -H "Authorization: token $GH_TOKEN" \
#     https://raw.githubusercontent.com/lerugray/hammerstein-model/master/tools/distill/run_gguf.sh | bash
#
# What this does:
#   - Clones the private repo (PAT auth)
#   - Installs unsloth + deps
#   - Runs convert_gguf.py: merges adapter into base, exports GGUF, quantizes, pushes to HF
#   - Default quant: q4_k_m (~5 GB, runs on any 8GB+ Mac)
#
# Idempotent — safe to re-run.

set -e

REPO_DIR=/workspace/hammerstein-model

echo "============================================="
echo " Hammerstein-7B GGUF conversion"
echo "============================================="
echo ""

# 1. Auth checks
if [ -z "$HF_TOKEN" ]; then
    echo "ERROR: HF_TOKEN not set (needed to push GGUF files)."
    exit 1
fi
if [ -z "$GH_TOKEN" ]; then
    echo "ERROR: GH_TOKEN not set (needed to clone private repo)."
    exit 1
fi

REPO_URL_AUTH="https://x-access-token:${GH_TOKEN}@github.com/lerugray/hammerstein-model.git"

# 2. Get the repo
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/4] Cloning repo (PAT auth)…"
    cd /workspace
    git clone "$REPO_URL_AUTH" hammerstein-model
fi
cd "$REPO_DIR"
echo "[1/4] Pulling latest…"
git remote set-url origin "$REPO_URL_AUTH"
git fetch --all --quiet
git checkout master --quiet
git pull origin master --quiet
git remote set-url origin "https://github.com/lerugray/hammerstein-model.git"

# 3. Verify GPU
echo ""
echo "[2/4] Verifying GPU…"
nvidia-smi --query-gpu=name,memory.total --format=csv

# 4. Install deps (idempotent)
echo ""
echo "[3/4] Installing dependencies (~3-5 min first time)…"
pip install -q --upgrade pip
pip install -q unsloth transformers peft accelerate bitsandbytes huggingface_hub
# llama.cpp is pulled + built by Unsloth on first GGUF export (~3 min)

# 5. Run the conversion (Unsloth handles llama.cpp internally)
echo ""
echo "[4/4] Converting + quantizing + pushing to HF…"
echo "       (first run also compiles llama.cpp; ~10-25 min total)"
echo ""
python tools/distill/convert_gguf.py

echo ""
echo "============================================="
echo " GGUF conversion complete."
echo ""
echo " Files at: https://huggingface.co/lerugray/hammerstein-7b-lora/tree/main"
echo ""
echo " To use locally on a Mac with Ollama:"
echo "   1. brew install ollama  (if needed)"
echo "   2. huggingface-cli download lerugray/hammerstein-7b-lora --include '*.gguf' --local-dir ~/hammerstein"
echo "   3. cat > ~/hammerstein/Modelfile <<'EOF'"
echo "      FROM ./hammerstein-7b-lora.q4_k_m.gguf"
echo "      EOF"
echo "   4. ollama create hammerstein -f ~/hammerstein/Modelfile"
echo "   5. ollama run hammerstein \"Audit this plan: ship MVP Friday\""
echo ""
echo " Then STOP the pod via the API or RunPod dashboard."
echo "============================================="
