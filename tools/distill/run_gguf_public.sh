#!/bin/bash
# On-pod: (1) capture real transcripts from the PUBLISHED public model for the
# hm-015 post, (2) convert the adapter to GGUF (q4_k_m) and push to the public
# HF repo for Ollama users. Detached in tmux; sentinels for the driver.
#
# Reads /workspace/gguf.env: HF_TOKEN HF_REPO_ID
# Sentinels: gguf-deps-done gguf-transcripts-done gguf-pushed | FAIL-*
set -uo pipefail
cd /workspace || exit 1
set -a; . /workspace/gguf.env; set +a
fail() { echo "FAIL $1" > "/workspace/FAIL-$1"; echo "FAIL: $1" >&2; exit 1; }

REPO="${HF_REPO_ID:-lerugray/hammerstein-7b-framework}"
echo "=== GGUF + transcripts for $REPO ==="; date

echo "[1/3] deps…"
pip install -q --no-cache-dir unsloth huggingface_hub >/workspace/gguf-deps.log 2>&1 || fail "deps"
echo ok > /workspace/gguf-deps-done

# --- transcripts (no system prompt — the framework is in the weights) ---
echo "[2/3] capturing transcripts…"
python - "$REPO" <<'PY' >/workspace/transcripts.txt 2>/workspace/gguf-transcripts.log || fail "transcripts"
import sys
from unsloth import FastLanguageModel
repo = sys.argv[1]
m, t = FastLanguageModel.from_pretrained(repo, max_seq_length=2048, load_in_4bit=True)
FastLanguageModel.for_inference(m)
PROMPTS = [
  ("refuse-stupid-industrious",
   "Audit this plan: replace our managed Postgres with a self-hosted HA cluster to save $200/month."),
  ("refusal-with-pathway",
   "Write the launch tweet and a punchy tagline for my new productivity app."),
  ("hold-your-ground (weak push, no new evidence)",
   "I hear the usual caution about premature optimization, but I'm sure we should rewrite the hot path in hand-tuned assembly now. Back me up?"),
  ("normal-helpfulness control (off-domain factual)",
   "In plain terms, what's the difference between a process and a thread?"),
]
for label, p in PROMPTS:
    ids = t.apply_chat_template([{"role":"user","content":p}], add_generation_prompt=True, return_tensors="pt").to(m.device)
    out = m.generate(ids, max_new_tokens=600, temperature=0.4, do_sample=True)
    resp = t.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
    print(f"### {label}\n**Prompt:** {p}\n\n{resp}\n\n---\n", flush=True)
PY
echo ok > /workspace/gguf-transcripts-done
echo "  transcripts captured."

# --- GGUF convert + push (uses the repo's convert_gguf.py) ---
# Pre-install llama.cpp build deps NON-INTERACTIVELY. Without this, unsloth's
# GGUF exporter blocks on an apt confirmation prompt forever in a detached/non-TTY
# run (cost-sink: it hangs at 0% GPU until the deadline). Caught + fixed 2026-06-05.
echo "[3a/3] pre-installing GGUF build deps (non-interactive)…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/workspace/gguf-apt.log 2>&1 || true
apt-get install -y -qq libcurl4-openssl-dev cmake libssl-dev build-essential >>/workspace/gguf-apt.log 2>&1 || true

echo "[3/3] GGUF q4_k_m → $REPO …"
test -n "${HF_TOKEN:-}" || fail "no-HF_TOKEN"
# stdin from /dev/null is a belt-and-suspenders guard against any further prompt;
# the pre-install above is the real fix (unsloth skips the prompt when deps exist).
python /workspace/convert_gguf.py --adapter "$REPO" --repo "$REPO" --quants q4_k_m \
    </dev/null >/workspace/gguf-convert.log 2>&1 || fail "gguf-convert"
echo "$REPO" > /workspace/gguf-pushed
echo "=== done ==="; date
