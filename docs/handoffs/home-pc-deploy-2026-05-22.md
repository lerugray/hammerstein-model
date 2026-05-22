# Home-PC Deploy — hammerstein-7b — 2026-05-22

Turnkey deploy instructions for a Claude Code session opened in this repo on Ray's home PC.

## What you are deploying

hammerstein-7b-framework-q5_k_m.gguf — a 5.4 GB Q5_K_M GGUF of the Hammerstein-7B
framework-disposition fine-tune (Qwen2.5-7B-Instruct base, QLoRA v3a). Runs via Ollama
on the RTX 3050 6GB. The Modelfile and deploy instructions are in `deploy/`.

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
