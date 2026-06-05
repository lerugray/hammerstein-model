#!/bin/bash
# On-pod orchestration for the PUBLIC framework-only 7B (hm-016).
#
# Runs DETACHED in tmux. The fire driver mirrors the repo's tools/distill/
# layout under /workspace/repo so train.py / eval.py __file__-relative paths
# (ROOT, DATA_DIR, OUTPUT_DIR) resolve to a writable workspace:
#
#   /workspace/repo/tools/distill/{train.py,eval.py,run_7b_public_pod.sh}
#   /workspace/repo/tools/distill/data/{<train>.jsonl,eval-set.jsonl,hammerstein-system-prompt.txt}
#
# Reads /workspace/7b.env (planted 600 by the driver):
#   HF_TOKEN HF_REPO_ID TRAIN_DATA(=abs path) PUSH_PUBLIC(0|1)
#
# Sentinels in /workspace for the driver poll loop:
#   7b-deps-done 7b-train-done 7b-eval-done 7b-HOLD-ready | 7b-pushed | FAIL-*
set -uo pipefail

cd /workspace || exit 1
set -a; . /workspace/7b.env; set +a

fail() { echo "FAIL $1" > "/workspace/FAIL-$1"; echo "FAIL: $1" >&2; exit 1; }

BASE=/workspace/repo/tools/distill
OUT="$BASE/output/hammerstein-7b-framework-lora"
DATA="${TRAIN_DATA:-$BASE/data/hm016-train.jsonl}"

echo "=== 7B public framework-only train ==="; date
test -f "$BASE/train.py" || fail "no-train.py"
test -f "$DATA" || fail "no-data-at-$DATA"
echo "data rows: $(wc -l < "$DATA")"

# --- 1. deps ---
echo "[1/3] installing deps…"
pip install -q --no-cache-dir unsloth trl peft transformers datasets huggingface_hub \
    >/workspace/7b-deps.log 2>&1 || fail "deps-install"
echo "ok" > /workspace/7b-deps-done

# --- 2. train ---
echo "[2/3] training…"
cd "$BASE"
python train.py --execute --model-key qwen-7b --backend unsloth \
    --data "$DATA" --output "$OUT" >/workspace/7b-train.log 2>&1 || fail "training"
test -d "$OUT/lora-adapter" || fail "no-adapter-saved"
echo "$OUT/lora-adapter" > /workspace/7b-train-done
echo "  adapter saved."

# --- 2b. eval (verify before publish): student vs vanilla + forgetting-check ---
echo "[2b] evaluating…"
cd "$BASE"
python eval.py --skip-gold --with-forgetting-check \
    --adapter-path "$OUT/lora-adapter" >/workspace/7b-eval.log 2>&1 \
    || echo "WARN eval nonzero (see 7b-eval.log)"
cp /workspace/7b-eval.log /workspace/7b-eval-results.txt 2>/dev/null || true
echo "done" > /workspace/7b-eval-done

# --- 3. publish (gated) ---
if [ "${PUSH_PUBLIC:-0}" = "1" ]; then
  echo "[3/3] pushing PUBLIC → $HF_REPO_ID …"
  test -n "${HF_TOKEN:-}" || fail "no-HF_TOKEN"
  test -n "${HF_REPO_ID:-}" || fail "no-HF_REPO_ID"
  python - "$OUT/lora-adapter" "$HF_REPO_ID" <<'PY' >/workspace/7b-push.log 2>&1 || fail "hf-push"
import sys, os
from huggingface_hub import HfApi
adapter, repo = sys.argv[1], sys.argv[2]
api = HfApi(token=os.environ["HF_TOKEN"])
api.create_repo(repo, repo_type="model", private=False, exist_ok=True)
api.upload_folder(folder_path=adapter, repo_id=repo, repo_type="model")
print("pushed", repo)
PY
  echo "$HF_REPO_ID" > /workspace/7b-pushed
  echo "  PUBLIC push complete."
else
  echo "[3/3] PUSH_PUBLIC!=1 — trained + evaled, HOLDING (no public push)."
  echo "adapter ready at $OUT/lora-adapter (not pushed)" > /workspace/7b-HOLD-ready
fi
echo "=== done ==="; date
