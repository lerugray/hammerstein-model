# 24/7 Homelab Bot Variant — Scoping Doc

**Status:** SCOPING DRAFT 2026-05-21 Mac afternoon. Drives overnight
2026-05-21→22 RunPod pilot + scoping lock. Ray reviews before any
training fires (operator authority over `[LOCK]` markers).

**Parent project:** hammerstein-model. Existing artifact: Hammerstein-7B
v3a (framework distillation, shipped 2026-05-09; 36/36 LLM-judge
preference vs raw frontier on v0 framework bench).

**This variant is NOT v3b of the 7B distillation.** It's a separate
training target: a smaller, focused 3-4B model tuned for Ray's
homelab daily-driver advisor role, runnable on consumer GPU 24/7.

## The opportunity

Ray's framing (2026-05-21 afternoon, verbatim): *"create another more
focused one to eventually act as my 24/7 bot for the homelab — runpod
still has plenty of credit to help too."*

Three converging surfaces:

1. **Homelab substrate exists.** Per the homelab project's INDEX entry:
   home PC (working), broken-screen ThinkPad (otherwise functional),
   spare PC shell. Consumer GPU on home PC is the deployment target.
2. **Anthropic Max is the scarce resource** in Ray's stack. Routine
   queries that don't need Opus judgment burn cap that's better spent
   on cross-file architecture / strategic synthesis. A homelab model
   that absorbs the routine layer is cost-recovery.
3. **r/vibecoding pointer.** A now-deleted commenter pitched
   pre-pre-training on the Emergent-NCA-Sequences-5M dataset
   ([HuggingFace](https://huggingface.co/datasets/Tejaskumar/Emergent-NCA-Sequences-5M))
   based on the MIT paper [arXiv:2603.10055](https://arxiv.org/abs/2603.10055)
   (Han/Lee/Kumar/Agrawal, Improbable AI Lab CSAIL, March 2026).
   Eval'd 2026-05-20 at `docs/research/nca-dataset-eval-2026-05-20.md`:
   claim is +6% downstream perplexity / 1.6× pre-training speedup
   from 164M NCA tokens (2-5% of total budget). Real research; worth
   a pilot. Closes the "follow up on that reddit thread" loop by
   actually running the experiment the commenter pitched.

## Use case profile (what this variant is FOR)

**Primary:** Ray's daily-driver advisor on the homelab. Routine
queries that Claude Max currently absorbs:

- "What's blocked in the portfolio right now?"
- "Audit this plan adversarially."
- "Summarize this session note."
- "Translate this bullet into the bullet format."
- "Draft a Telegram reply for mission-bullet."
- "Mode-switch via mission-companion's RPG / hammerstein / canon
  surfaces" — replaces some `claude` CLI shell-outs.

**Secondary (Phase 2+):**

- mission-companion backend on homelab (zero-network inference for
  mission modes that don't need frontier capability).
- GS bot reviewer step (~$0.06/cycle × 100 cycles/week = ~$25/month
  savings; small but additive to the Anthropic-conservation pattern).
- Always-on background reasoning (proactive observations triggered
  by file changes, calendar events, etc. — Phase 3 ambition, not v1).

**Explicitly NOT:**

- A replacement for Claude Max on hard reasoning. Opus stays the
  daily driver for architecture, security review, cross-file
  refactors, strategic synthesis. This variant is the *routine
  layer*, not the *load-bearing layer*.
- A general public-facing product. This is Ray's personal substrate;
  voice tuning is personal, training data may include private
  session content.

## `[LOCK]` Architecture

- **`[LOCK]` Base model:** **Qwen3.6-3B-Instruct.**
  Rationale: modern Qwen reasoning + Apache 2.0 license + 32k
  context + matches the Qwen family already in Ray's stack
  (Qwen3.6-plus is the prose flagship per his routing rules).
  Unsloth supports it for QLoRA. 3B is the consumer-GPU sweet
  spot — runs Q5_K_M GGUF at ~3 GB VRAM, leaves headroom for
  context + simultaneous tools.
  Alternatives considered + rejected:
    - **Llama-3.2-3B-Instruct** — fine but Qwen reasoning edge
      shows on benchmarks at this size.
    - **Phi-3.5-mini (3.8B)** — Microsoft license carries less
      certainty than Apache 2.0 for personal-data-trained derivatives.
    - **Hammerstein-7B v3a** — too big for homelab 24/7 + already
      shipped + not the use case.
- **`[LOCK]` Quantization target:** **Q5_K_M GGUF** for homelab
  deployment. Trains in BF16 on RunPod, converts to GGUF at deploy
  time.

  **Deployment target confirmed (2026-05-21):** home PC has an
  **RTX 3050, 6 GB VRAM**, Windows 11, already running the GS bot
  dispatcher (`state/homelab/scoping-2026-05-21.md`). VRAM budget
  for a 3B model:
    - Q5_K_M weights ≈ 2.3-2.5 GB
    - KV cache at 4096 context ≈ 0.5-1 GB
    - Windows desktop compositor + GS dispatcher overhead ≈ 0.5-1 GB
      (the home PC is also Ray's daily Windows machine + always-on
      bot host — the GPU is shared, not dedicated)
    - **Total ≈ 3.5-4.5 GB — comfortable headroom inside 6 GB.**

  Q5_K_M stays the lock: the headroom matters because the GPU is
  shared. If post-training the model wants more fidelity, Q6_K
  (~2.8 GB weights) still fits; Q8_0 (~3.6 GB) is borderline once
  the desktop + dispatcher are accounted for — avoid Q8 on this
  card. If hl-007 (spare-PC parts assessment) surfaces a bigger
  card (RTX 3060 12GB / 3070 8GB), the quant + context budget
  open up — but v1 ships fine on the RTX 3050 as-is. No hardware
  upgrade is a blocker for this variant.
- **`[LOCK]` Inference runtime on homelab:** **Ollama** on the
  Windows side of the home PC (Ollama has a native Windows build;
  no WSL2 needed for the GPU path — it uses the Windows CUDA
  runtime directly). Stable HTTP server on :11434 for
  mission-companion to wire against. llama.cpp is the fallback if
  Ollama's Windows CUDA path misbehaves.

## Training pipeline (three phases)

### Phase 0 — NCA pre-pre-training pilot (optional, parallel)

**Goal:** validate the MIT paper's 1.6× speedup + reasoning lift
claim on a *small sandbox model* before committing the 3B variant.
Per the 2026-05-20 eval's recommended next action: "low-compute
pilot on a 100M-300M model before committing the 7B."

- **Sandbox model:** **OLMo-1B** (Allen Institute, Apache 2.0,
  fully open weights + training code — the standard reproducibility
  baseline at this size). Alternative: TinyLlama-1.1B.
- **Dataset:** Emergent-NCA-Sequences-5M, filtered by
  high-entropy rollouts per the eval's domain-targeting
  recommendation. 100M token subset.
- **Setup:** RunPod RTX 4090 ($0.34/hr) × ~6-8 hours. Estimated
  cost: $2-3.
- **Eval:** vs. matched-budget OLMo-1B trained on equivalent C4
  tokens only. Downstream GSM8K + HumanEval after the same
  follow-on SFT exposure. Numbers go in
  `RESULTS-NCA-pilot-2026-05-NN.md`.
- **Outcome:** if the 1.6× speedup holds → consider for 3B variant
  Phase 0; if not → skip Phase 0 for the 3B variant, lose nothing.

### Phase 1 — Main SFT (the actual 24/7 bot)

**Goal:** Qwen3.6-3B-Instruct + Hammerstein voice + Ray-stack
familiarity.

- **Base:** Qwen3.6-3B-Instruct (`[LOCK]`).
- **Method:** QLoRA via Unsloth (~70% less VRAM, 2× faster than
  vanilla LoRA per existing MODEL-EXPERIMENT.md research).
- **Dataset assembly** (see § below).
- **Setup:** RunPod RTX 4090 × 4-6 hours. Estimated: $1.50-3.
- **Eval:**
  - Voice alignment: LLM-judge pairwise vs. Hammerstein-on-frontier
    outputs (Qwen3.6-plus baseline) on a 30-prompt eval set drawn
    from Ray's actual project queries.
  - Domain coverage: 15 questions across Ray's project stack
    (hammerstein-ai / generalstaff / mission-* / retrogaze /
    devforge / TWAR PC / GTA / etc.) — does the model know
    project context the way a Hammerstein audit would.
  - Refusal alignment: a 10-prompt stupid-industrious-plans
    eval — does the model push back the way Hammerstein audits
    do, or does it slip into validate-and-yes-and?
  - Latency on homelab: measured end-to-end response time at
    Q5_K_M on consumer GPU. Target: <2s for short responses,
    <8s for full audit-style outputs.

### Phase 2 — DPO refinement (deferred; not tonight)

Preference data from Ray's actual usage. Requires a usage period
to collect signal. File as follow-up; tonight ships Phase 1 only.

## Dataset assembly

### Hammerstein voice (~5k examples)

Existing Hammerstein synthetic from the v3a distillation pipeline
(Qwen3.6 teacher outputs in Hammerstein voice). Reuse verbatim;
already battle-tested in v3a.

### Ray-stack familiarity (~500-2000 examples)

Curated Q/A pairs from Ray's own working substrate. Sources:

- `generalstaff-private/docs/sessions/*.md` — natural-language
  queries Ray would ask the model
- `generalstaff-private/state/*/tasks.json` — project-context
  questions
- `mission-PMA/state/vents/*.md` — *intentionally excluded* by
  default; emotional content not training-suitable + privacy.

**`[LOCK]` Privacy posture:** Ray-stack examples are
**locally-trained-only, never published**. The trained model is
private (homelab + Ray's machines only). HuggingFace push happens
only after a sanitization pass + Ray's explicit OK.

Generation method:
- Sonnet subagent reads session notes + tasks.json + audit-log
  entries; generates Q/A pairs in the shape "user query → ideal
  Hammerstein-voice response with knowledge of Ray's stack."
- Pairs filtered by a second pass for personal-data-leakage
  (no names of non-public collaborators, no financial specifics,
  no medical / PMA content).

## Cost ceiling for overnight 2026-05-21→22

`[LOCK]` Spend cap: **$50 RunPod + OpenRouter combined.** Anthropic
burn separate (covered by current cap window).

Breakdown:
- NCA pilot on OLMo-1B: ~$3
- Main SFT on Qwen3.6-3B: ~$3
- Synthetic data extension (Qwen3.6-plus teacher outputs for any
  gaps): ~$5
- Eval calls (LLM-judge pairs): ~$3
- Buffer: $15-30 for iteration if first runs miss
- **Total ceiling: $50.** Stop + report if approaching.

Anthropic burn pattern (separate from cost ceiling):
- Foreground Opus driving scoping (now, this doc): light
- Sonnet subagent for dataset curation: medium
- Sonnet subagent for training script + RunPod fire: medium
- Tomorrow's analysis + iteration: medium-high

## Overnight execution sequence

`[LOCK]` This is the plan that fires tonight after Ray's review.

**T+0 (now):** Scoping doc lands (this file). Ray reviews + locks.

**T+30 min (after Ray's lock):**
- Dispatch 1: dataset curation subagent (Sonnet) — extracts Q/A
  pairs from Ray's stack, sanitizes, writes JSONL training set
  to `hammerstein-model/data/ray-stack-sft-2026-05-21.jsonl`
- Dispatch 2: training-script subagent (Sonnet) — writes
  RunPod-ready train scripts for both Phase 0 NCA pilot + Phase
  1 main SFT, places at `hammerstein-model/training/24-7-variant/`

**T+1-2 hr:** Ray confirms + Sonnet subagent fires both RunPod
pods via existing pod runner (`hammerstein-model/pod-pipeline/`).

**T+4-8 hr (overnight, Ray sleeps):** RunPod trains. No Anthropic
burn during this window.

**Tomorrow morning (T+8-12 hr):**
- Pods complete; results land at
  `hammerstein-model/results/24-7-variant-pilot-2026-05-22/`
- Foreground analyzes:
  - NCA pilot: did the 1.6× speedup claim hold?
  - Main SFT: voice + domain + refusal eval scores
- Decision: ship v0 → homelab quantize + deploy, OR iterate.

## Eval criteria gate

`[LOCK]` Pre-committed: this variant *ships to homelab* if all five:

1. **Voice alignment** ≥ 70% LLM-judge preference vs. Qwen3.6-3B-base
   (baseline = the same model without Hammerstein SFT). Below 70%
   means the SFT didn't land voice tightly enough.
2. **Domain coverage** ≥ 60% of project-stack questions answered
   with non-trivial project knowledge. Below 60% = the Ray-stack
   examples didn't generalize; iterate dataset.
3. **Refusal alignment** ≥ 80% of stupid-industrious prompts pushed
   back. Below 80% = the framework didn't bake in; iterate.
4. **Uncertainty-honest** ≥ 80% on a 10-prompt eval where the
   ideal response is some shape of "I don't know X" / "that's at
   my competence ceiling" / "you should verify Y with a specialist"
   / "here's what I'd need before answering that confidently."
   Below 80% = the model fabricates when it shouldn't; iterate
   dataset toward more uncertainty-surfacing examples.

   **Why this axis exists:** hai-039 OOD bench (commit 71b4f1d
   in hammerstein/main, 2026-05-21) found Hammerstein-on-frontier
   takes a −0.38 perceived-usefulness hit on medical/legal OOD
   questions BECAUSE it acknowledges its limits — and raw frontier
   gets caught in confident-hallucination on 3/8 questions for the
   same reason. The harm-reduction-as-architecture trade is real
   and measurable. Bake it into the 24/7 variant explicitly rather
   than hoping voice-alignment training pulls it along implicitly.
5. **Latency** < 2s for short responses, < 8s for long, at
   Q5_K_M on consumer GPU. Higher latencies = needs Q4_K_M or
   smaller model.

If 4/5 pass: ship v0 with documented caveat on the failing axis.
If ≤3/5: don't ship; iterate before deploy.

**Dataset implication:** the SFT dataset needs a dedicated
uncertainty-surfacing category — not just emergent-from-Hammerstein-
voice ceiling-respect. ~50-100 explicit "ideal-response-is-honest-
uncertainty" examples. If the in-flight dataset curation doesn't
already include this category, augment with a second pass before
firing the SFT pod.

## Falsification gate (when do we abandon this variant?)

`[LOCK]` Pre-committed: abandon the 24/7 variant if **after 3 training
iterations the voice alignment + refusal alignment can't crack 70%
together**. Reason: at that point, the architectural call (3B + QLoRA
+ this dataset shape) is wrong-shaped — either too small for the
framework discipline to bake in, or the dataset isn't dense enough,
or both. Either way: don't keep throwing $3-5 RunPod runs at it. Go
back to leaning on Hammerstein-7B v3a + Anthropic Max for the
routine layer, and revisit the substrate question.

## Open questions for Ray (only the design-axis ones)

1. **Ray-stack training data inclusion:** OK to extract Q/A pairs
   from session notes + tasks.json + audit log? *Lean: yes, with
   the sanitization pass for personal-data-leakage; never publish
   the trained model without explicit OK.*
2. **mission-PMA vent content:** Default-excluded per the privacy
   `[LOCK]` above. Confirm or override? *Lean: keep excluded.*
3. **Phase 0 NCA pilot timing:** Fire tonight in parallel with Phase
   1 main SFT, OR fire only Phase 1 tonight + NCA pilot tomorrow?
   *Lean: fire both tonight (parallel pods on RunPod, independent
   experiments, $3 each — sequencing doesn't save money or
   complexity).*
4. **Inference runtime:** llama.cpp or Ollama on homelab?
   *Lean: Ollama for the API server (matches Ray's existing Ollama
   workflow per CLAUDE.md routing rules).*

Everything else is `[LOCK]` and ships per this doc unless Ray
overrides a specific lock.

---

**Next:** Ray reviews this doc → locks/overrides → I dispatch the
two subagents (dataset curation + training scripts) → overnight
runs fire → tomorrow morning analyzes.
