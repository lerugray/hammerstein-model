# Cloud Training Walkthrough — RunPod & Kaggle

Once `gen_data.py --execute` finishes (you'll have
`tools/distill/data/synthetic-2026-05-08.jsonl`), this is the
end-to-end recipe to train and download the Hammerstein-7B LoRA
adapter.

**Path A: RunPod** (recommended — cleanest workflow, ~$1.50-3)
**Path B: Kaggle Notebooks** (free, slightly more friction)

Both use the same `train.py`. Pick one.

---

## Path A — RunPod RTX 4090 (~$1.50-3)

### 1. Sign up + add credit (one-time, 5 min)

- [runpod.io](https://www.runpod.io) → sign up
- Add **$10 credit** (covers this experiment + buffer)
- (Optional) Generate an SSH key pair locally if you don't have one

### 2. Spin up a pod (5 min)

- Pods → Deploy → Community Cloud
- GPU: **RTX 4090** ($0.34/hr)
- Template: **Pytorch 2.4** or **CUDA 12.4 + Ubuntu 22.04**
- Storage: **30 GB** (the base model is ~5GB, training scratch ~10GB)
- Click Deploy → wait ~60s for boot

### 3. SSH in + setup (5 min)

```bash
# RunPod gives you an SSH command in the dashboard. Use it.
ssh root@<pod-ip> -p <port> -i ~/.ssh/hammersteinkey

# Once connected, run the one-line setup:
bash <(curl -s https://raw.githubusercontent.com/lerugray/hammerstein-model/master/tools/distill/setup_pod.sh)
```

The setup script clones the repo, installs deps, and verifies CUDA.
~3-5 min for the pip install on first run.

### 4. Copy the synthetic data over (1 min)

From your Mac, in a separate terminal:

```bash
cd "/Users/rayweiss/Desktop/Dev Work/hammerstein-model"
scp -P <port> tools/distill/data/synthetic-2026-05-08.jsonl \
    root@<pod-ip>:/workspace/hammerstein-model/tools/distill/data/
```

### 5. Train (~50 min on RTX 4090, ~$0.30)

Back on the pod:

```bash
python tools/distill/train.py \
    --data tools/distill/data/synthetic-2026-05-08.jsonl \
    --model-key qwen-7b \
    --backend unsloth \
    --execute
```

Watch the logs. ~750 training steps over ~50 min. If you see OOM,
drop `--model-key` to `llama-3b` (smaller base, fits easier).

### 6. Download the adapter (1 min)

From your Mac:

```bash
scp -P <port> -r \
    root@<pod-ip>:/workspace/hammerstein-model/tools/distill/output/qwen-7b-hammerstein-lora \
    tools/distill/output/
```

### 7. Stop the pod

In the RunPod dashboard: **Stop** the pod (don't terminate; you can
restart if needed). Or terminate to stop billing entirely. Total
spend: ~$0.30-3 depending on how long training took.

### 8. Convert to GGUF (optional, on Mac)

```bash
pip install llama-cpp-python
python -m llama_cpp.convert_hf_to_gguf \
    tools/distill/output/qwen-7b-hammerstein-lora \
    --outfile hammerstein-7b.gguf --outtype q4_k_m
```

Then `ollama create hammerstein -f Modelfile` to register locally.

---

## Path B — Kaggle Notebooks (free, ~30 hr/week T4 limit)

### 1. Sign up at [kaggle.com](https://www.kaggle.com) (free)

Phone-verify your account to unlock GPU access.

### 2. Create a new notebook

- Code → New Notebook
- Settings → Accelerator → **GPU T4 ×1** (or P100 if available)
- Settings → Internet → **Enabled** (needed for pip install)

### 3. Upload synthetic data as a dataset

- Datasets → New Dataset → Upload `synthetic-2026-05-08.jsonl`
- Title: "hammerstein-distill-data"
- Then in the notebook: **+ Add data** → your dataset

### 4. Notebook cells

```python
# Cell 1: install
!pip install -q unsloth trl peft transformers datasets

# Cell 2: fetch this repo's training script
!git clone https://github.com/lerugray/hammerstein-model.git
%cd hammerstein-model

# Cell 3: link the uploaded data
!ln -sf /kaggle/input/hammerstein-distill-data/synthetic-2026-05-08.jsonl \
    tools/distill/data/synthetic-2026-05-08.jsonl

# Cell 4: train
!python tools/distill/train.py \
    --data tools/distill/data/synthetic-2026-05-08.jsonl \
    --model-key qwen-7b \
    --backend kaggle \
    --execute
```

### 5. Download the adapter

After training, in a final cell:

```python
import shutil
shutil.make_archive("/kaggle/working/lora-adapter", "zip",
                    "tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter")
```

The `.zip` shows up in the right sidebar's Output panel — download to
your Mac.

### Notes for Kaggle

- T4 has 16GB VRAM, plenty for 7B QLoRA
- ~30 hr/week free GPU time — one training run is ~1 hr, well under
- If session times out (12 hr limit), training can resume from the
  last checkpoint via `--resume_from_checkpoint`

---

## Verification after training (either path)

Run the eval harness against the new adapter:

```bash
python tools/distill/eval.py \
    --student-path tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter \
    --vanilla-path unsloth/Qwen2.5-7B-Instruct-bnb-4bit
```

This compares: vanilla base / fine-tuned student / gold (Qwen3.6 +
framework wrapper). Output shows the structural-score ratio and a
PASS/FAIL verdict per the 80% threshold.

---

## If anything fails

- **OOM during training**: drop `--model-key qwen-7b` → `llama-3b`
- **Pod won't start**: try a different region or RTX 3090 ($0.29/hr)
- **Connection drops during data transfer**: use `rsync` instead of `scp`
- **Training hangs**: check `nvidia-smi` on the pod; if no GPU usage,
  check that `unsloth` imported (it auto-detects CUDA on import)

For the eval to make sense, you also need OPENROUTER_API_KEY in env
(it calls Qwen3.6 for the gold-standard comparison).
