# Home-PC Deploy — hammerstein-7b — 2026-05-22

Turnkey deploy instructions for a Claude Code session opened in this repo on Ray's home PC.

## What you are deploying

hammerstein-7b-framework-q5_k_m.gguf — a 5.4 GB Q5_K_M GGUF of the Hammerstein-7B
framework-disposition fine-tune (Qwen2.5-7B-Instruct base, QLoRA v3a). Runs via Ollama
on the RTX 3050 6GB. The Modelfile and deploy instructions are in `deploy/`.

## Step 0 — Pre-flight: can this machine run it + safe cleanup

Runs **before** the deploy steps below. Ray asked for this explicitly. Two phases —
**Phase A is read-only and always runs; Phase B touches the system and is heavily
gated.** This procedure was reviewed by a Hammerstein adversarial audit; the gates
below incorporate its catches.

### Phase A — Diagnose (read-only, safe — touches nothing)

Gather and report to Ray, in plain English:

- **GPU/VRAM:** `nvidia-smi` — total and free VRAM. A single reading is a *snapshot*:
  the desktop compositor (DWM), the GS dispatcher, and Ollama all draw on the same
  6 GB. Treat free-VRAM as approximate, not a guarantee.
- **RAM:** total + available (CPU offload of the model needs headroom).
- **Disk:** free space on the drive holding Ollama's model store and `deploy/`
  (~6 GB+ needed for the GGUF).
- **Competing load:** top processes by RAM and by GPU; startup items; confirm the
  GS dispatcher is running and note its footprint.
- **Report:** will the 5.4 GB model run as-is? If tight, what specifically would
  help? List anything that reads as resource-eating bloatware — what it is, what
  disabling/removing it would do.

If Phase A shows the machine is fine, **skip Phase B and go to Prerequisites.**

### Phase B — Cleanup (only if Phase A shows it's needed; every step gated)

All rails must hold. If any fails, stop.

**Gate 1 — Restore point, verified (HALT gate).** Before any change, a verified
Windows restore point dated within the last 24 h must exist — freshly created
(`Checkpoint-Computer -Description "pre-hammerstein cleanup" -RestorePointType
MODIFY_SETTINGS`) and confirmed via `Get-ComputerRestorePoint`, or already present
from today. If System Restore is disabled, enable it (`Enable-ComputerRestore`,
with Ray's OK) first. **If no restore point can be created or verified — HALT, do
not enter Phase B.** Windows can fail this silently (Volume Shadow Copy under disk
load; the 24 h rate limit); a silent failure means there is no safety net, so this
is a hard stop.

**Gate 2 — Per-item, operator-present.** Ray is in the session. Each change is
proposed to him in plain English (what it does, what it frees, whether it is
reversible) and done only on his explicit OK. One at a time. No batching.

**Gate 3 — Reversible beats destructive.** Disable a startup item > uninstall via
the app's own uninstaller or `winget uninstall` > **never manual file deletion.** A
restore point does NOT undo file or personal-data deletions — only system
config/registry/drivers. That is exactly why this procedure never deletes files:
uninstalls reinstall, disables re-enable, deletions do not.

**Gate 4 — Hard deny-list. Never touch:** `C:\Windows`, `System32`, PowerShell /
cmd / Windows Terminal, drivers, system registry hives, the bootloader — and **the
GS dispatcher and everything it depends on** (Node/Bun/Python runtimes, its
scheduled tasks). No renaming or deleting OS components, ever.

**Gate 5 — Dispatcher health after every change.** The risk a deny-list misses:
disabling something that *looks* unrelated can break a shared service the
dispatcher silently relies on (network stack, TLS/cert services). After EACH
change, confirm the GS dispatcher is still healthy — process alive and still
cycling normally by whatever signal it exposes (recent log activity / a completed
cycle). Watch it for ~10 minutes after the change, not just instantly —
degradation can be gradual. Any degradation → **revert that change immediately
and stop.**

**Gate 6 — When unsure, don't.** If something cannot be positively identified as
safe-to-remove bloatware, leave it and flag it. The bar is "clearly safe and
clearly helps," not "might help." It is a working machine, not a lab.

### The Chrome AI feature (Ray named this) — handle separately

Treat it as a **standalone, zero-risk action, decoupled from Phase B** — do not run
it alongside system cleanup. It is almost certainly a setting inside Chrome: turn it
off via Chrome's own Settings UI or `chrome://flags` **only**. No registry edits, no
Group Policy, no policy-file surgery — if it is only reachable that way, leave it.
Its real resource cost is likely marginal; this is tidiness, not a performance fix.

### What actually matters

Bloatware mostly eats RAM, disk, and startup time. The thing that decides whether
the 7B *runs well* is **VRAM** — and cleanup will not meaningfully change the VRAM
picture. If Phase A shows VRAM is the bottleneck, the levers are partial CPU offload
(expected — see "Expected behavior" below), KV-cache quantization, a smaller quant,
or the `OLLAMA_NUM_GPU=0` CPU fallback — not more app removal. Don't let cleanup
become a distraction from the real constraint.

## Prerequisites

- Ollama installed (https://ollama.com/download — Windows installer)
- `huggingface-cli` available (ships with `pip install huggingface_hub` or use the repo's
  `.venv` which already has it at `.venv/bin/huggingface-cli`)

## Step 1 — Authenticate with HuggingFace (REQUIRED — the repo is PRIVATE)

The GGUF lives in a PRIVATE HuggingFace repo: `lerugray/hammerstein-7b-framework-gguf`.
You need Ray's HF token to pull it.

Check if the token is already configured:

    huggingface-cli whoami

If it returns Ray's username, skip to Step 2. If not, authenticate:

    huggingface-cli login

Paste Ray's HF token when prompted. Alternatively, set the environment variable before
running the download:

    set HF_TOKEN=<token>

Ray's HF token is in `~/.generalstaff/.env` under `HF_TOKEN` (or can be found in the
HuggingFace account settings at https://huggingface.co/settings/tokens).

## Step 2 — Download the GGUF into deploy/

From the repo root, run:

    huggingface-cli download lerugray/hammerstein-7b-framework-gguf hammerstein-7b-framework-q5_k_m.gguf --local-dir deploy/

This downloads the 5.4 GB GGUF directly into the `deploy/` directory, next to the Modelfile.
The file is gitignored (`*.gguf` in `.gitignore`) so it will not be staged or committed.

Expected result: `deploy/hammerstein-7b-framework-q5_k_m.gguf` exists and is ~5.4 GB.

## Step 3 — Register the model with Ollama

From the repo root:

    ollama create hammerstein-7b -f deploy/Modelfile

Ollama reads the Modelfile, ingests the GGUF, and registers a local model named
`hammerstein-7b`. This is a one-time operation per machine.

## Step 4 — Run the model

    ollama run hammerstein-7b

Or with a prompt directly:

    ollama run hammerstein-7b "Audit this plan: ship the new landing page tonight without testing"

## Expected behavior on RTX 3050 6GB

The model is 5.4 GB (Q5_K_M). The RTX 3050 has 6 GB VRAM. At Q5_K_M, the model weights
alone sit at roughly the VRAM limit — Ollama will load as many layers as fit and offload
the remainder to CPU RAM. You will see a message like:

    llm_load_tensors: offloading N repeating layers to GPU
    llm_load_tensors: offloaded N/32 layers to GPU

Some CPU offload is expected and normal. Response speed will be slower than a full-GPU
run. The real test is whether responses are coherent and framework-correct — observe the
first few outputs manually. Target latency for a short response: 5-15 seconds with partial
CPU offload (vs 1-3s on a full 8GB+ GPU run).

If Ollama errors on VRAM overflow, try:

    OLLAMA_NUM_GPU=0 ollama run hammerstein-7b

to force pure CPU inference (slower but avoids VRAM errors). This is a fallback, not
the target path.

## Verification prompt

Once running, try this prompt to confirm framework-disposition is active:

    Audit this plan: I'm going to spend the next two weeks rewriting our entire
    database layer in a new ORM before we've validated that users actually want
    the product.

Expected shape: the model names the stupid-industrious failure mode, explains the
structural problem (pre-validation architecture investment), and gives a concrete gate
or next step. If you get generic "be careful" advice without naming the failure mode,
the distillation may have regressed — flag it.

## Inference parameters (set in Modelfile)

- temperature: 0.7
- top_p: 0.9
- num_ctx: 4096
- stop token: `<|im_end|>` (Qwen2.5 chat format)
- No system prompt — framework is baked into weights

These match the training-time inference setup from `tools/distill/infer.py`.
