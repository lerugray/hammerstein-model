#!/bin/bash
# Single-paste eval run for the RunPod pod.
#
# Bootstrap (the curl itself needs auth since the repo is private):
#   export GH_TOKEN=github_pat_xxxxxxxx       # fine-grained PAT, read-only on this repo
#   export HF_TOKEN=hf_xxxxxxxx               # to download the private adapter
#   curl -sL -H "Authorization: token $GH_TOKEN" \
#     https://raw.githubusercontent.com/lerugray/hammerstein-model/master/tools/distill/run_eval.sh | bash
#
# Or in JupyterLab's terminal: same thing, the `bash <(curl ...)` form works too.
#
# Prereqs (Ray):
#   1. GH_TOKEN env var: fine-grained PAT, read-only on this repo
#      Create at https://github.com/settings/personal-access-tokens/new
#      Repository access: only hammerstein-model
#      Repository permissions: Contents → Read-only (everything else "no access")
#   2. HF_TOKEN env var: any token with read access to
#      lerugray/hammerstein-7b-lora (the existing write token is fine)
#
# Idempotent — safe to re-run.

set -e

REPO_DIR=/workspace/hammerstein-model

echo "============================================="
echo " Hammerstein-7B 4-condition eval run"
echo "============================================="
echo ""

# 1. Auth checks
if [ -z "$HF_TOKEN" ]; then
    echo "ERROR: HF_TOKEN not set (needed to download private adapter)."
    echo "  Run: export HF_TOKEN=hf_xxxxxxxx"
    exit 1
fi
if [ -z "$GH_TOKEN" ]; then
    echo "ERROR: GH_TOKEN not set (needed to clone the private repo)."
    echo "  Create a fine-grained PAT at:"
    echo "    https://github.com/settings/personal-access-tokens/new"
    echo "  Scope: lerugray/hammerstein-model only, Contents: read-only."
    echo "  Then: export GH_TOKEN=github_pat_xxxxxxxx"
    exit 1
fi

# Use the PAT for the clone. x-access-token is GitHub's documented username
# for token auth via HTTPS. The token sits in the URL only briefly during
# the clone; we drop the embed once the repo is cloned and rely on the
# credential helper that git stores in the working tree's .git/config.
REPO_URL_AUTH="https://x-access-token:${GH_TOKEN}@github.com/lerugray/hammerstein-model.git"

# 2. Get the repo
if [ ! -d "$REPO_DIR" ]; then
    echo "[1/5] Cloning repo (with PAT auth)…"
    cd /workspace
    git clone "$REPO_URL_AUTH" hammerstein-model
fi
cd "$REPO_DIR"
echo "[1/5] Pulling latest…"
# Re-write the remote URL each run so a previously-stored token doesn't
# bind us to a stale value. Set + use, then unset to keep the token out
# of any persistent config we might commit by accident.
git remote set-url origin "$REPO_URL_AUTH"
git fetch --all --quiet
git checkout master --quiet
git pull origin master --quiet
# Scrub the embedded token from the persisted remote URL.
git remote set-url origin "https://github.com/lerugray/hammerstein-model.git"

# 3. Verify GPU
echo ""
echo "[2/5] Verifying GPU…"
nvidia-smi --query-gpu=name,memory.total --format=csv

# 4. Install deps (idempotent)
echo ""
echo "[3/5] Installing dependencies (~3-5 min first time, instant after)…"
pip install -q --upgrade pip
pip install -q unsloth trl peft transformers datasets accelerate bitsandbytes huggingface_hub

# 5. HF login (so Unsloth can fetch the private adapter)
echo ""
echo "[4/5] Authenticating to HuggingFace…"
python -c "from huggingface_hub import login; import os; login(token=os.environ['HF_TOKEN'], add_to_git_credential=False); print('  HF login OK')"

# 6. Run the eval
echo ""
echo "[5/5] Running 4-condition eval (vanilla / ablation / student) + forgetting check…"
echo "      ~40 prompts × 3 local conditions + 4 forgetting prompts × 3 conditions"
echo "      ~50-70 min on RTX 4090"
echo ""
python tools/distill/eval.py \
    --skip-gold \
    --with-forgetting-check

echo ""
echo "============================================="
echo " Eval complete."
echo ""
echo " Results:"
echo "   $REPO_DIR/tools/distill/data/eval-$(date -u +%Y-%m-%d).jsonl"
echo "   $REPO_DIR/tools/distill/data/eval-$(date -u +%Y-%m-%d).summary.md"
echo ""
echo " To pull results back to your Mac, from your Mac terminal:"
echo "   POD=<pod-ip-or-host>"
echo "   scp -i ~/.ssh/your-pod-key root@\$POD:$REPO_DIR/tools/distill/data/eval-*.jsonl \\"
echo "     '/Users/rayweiss/Desktop/Dev Work/hammerstein-model/tools/distill/data/'"
echo "   scp -i ~/.ssh/your-pod-key root@\$POD:$REPO_DIR/tools/distill/data/eval-*.summary.md \\"
echo "     '/Users/rayweiss/Desktop/Dev Work/hammerstein-model/tools/distill/data/'"
echo ""
echo " Then STOP the pod in the RunPod dashboard."
echo "============================================="
