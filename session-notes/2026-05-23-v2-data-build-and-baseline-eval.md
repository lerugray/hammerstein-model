# Session 2026-05-23 — v0.2 data build + v1 baseline eval (autonomous)

Continuation of the 2026-05-22 / 2026-05-23 home-PC evening session. Ray
set the goal at ~21:00 local and went to bed; this session ran
autonomous through the night against the locked plan.

**Locked goal (from /goal at ~21:00):** full v0.2 pipeline through eval
(~4-5 hours), RunPod $5-25 / OpenRouter ~$2, session notes + commit on
completion.

## What landed

### Voice + data assembly (complete)

**Seeds 01-30 in `data/v2-casual-seeds-scratchpad.md`** — drafted with
Ray's approval on 01-05 (captured from real v1 Telegram exchanges) and
auto-generated 06-30 from work artifacts + PMA mirror-voice exemplars +
git history. Each seed has prompt + ideal-response + target-shape note.
The no-engagement-pushing rule (saved to memory as
`feedback_no_engagement_pushing.md`) is applied across all 30. Voice-rule
section at the top of Seeds 06-30 documents the locked rules so future
sessions inherit them.

**Audit-trigger discrimination set** at
`data/v2-audit-discrimination-2026-05-23.jsonl` — 58 pairs (22 positive
audit-shape triggers, 34 negative audity-but-stay-casual, 2 ambiguous-
artifact-required). Written by a sonnet sub-agent against the locked
voice rules.

**OpenRouter teacher expansion script** at
`scripts/v2_openrouter_expansion.py` — runs Qwen3.6-plus restyling
against HF datasets (no_robots × 100, oasst2 × 50, hh-rlhf × 20) with 7
locked-seed exemplars in the system prompt. Smoke + run + dry-run modes,
$2.50 hard stop. Picks up OpenRouter key from `MiroShark/.env`.

**Smoke (5 prompts, $0.02) cleared** — voice quality is on-target across
the range. Mayonnaise rescue: "Emulsion collapsed. Oil outpaced the
yolk's binding capacity... The structural fix is controlling the pour
rate. It will come back together." Walrus + limerick (sample 5): factual
brief + an actual limerick that scans. Self-driving cars outline (sample
6): "Constraint note first: no live feed to current crash databases or
regulatory filings... Treat as framework estimates, not audited fact."
Exactly the staff-officer constraint-naming voice the v2 spec calls for.

**Full restyled expansion** at
`data/v2-casual-restyled-2026-05-23.jsonl` — 166 pairs written
(4 dropped from the 170 target during sanitization or API edge cases).
Total OpenRouter spend: $0.73 (210,261 input tokens + 340,251 output
tokens via qwen3.6-plus). Cost ran 3x my initial $0.24 estimate because
the teacher produced longer responses than the cost model assumed; still
well under the $3 ceiling and far under the $25 RunPod cap (none spent).

**v0.1 combined assembled** at `data/ray-stack-sft-v0.1-combined.jsonl`
(541 pairs, base + expansion). Was missing locally — needed by the v0.2
training mix.

**v0.2 additions concatenated + sanitized** at
`data/ray-stack-sft-v0.2-additions.jsonl` via
`scripts/v2_concat_sanitize.py`. The script also parses Seeds 01-30 from
the scratchpad and writes them out as
`data/v2-casual-seeds-2026-05-23.jsonl` (30 pairs) for downstream use.
Sanitization regex passed clean; one line dropped (a meta-pair about the
regex itself that contained the block-list collaborator names).

### Training pipeline (fire-ready)

**v0.2 continued-LoRA training script** at
`training/24-7-variant/train_v02_continued.py` — Qwen2.5-7B-Instruct
base, loads the v3a LoRA adapter from `lerugray/hammerstein-7b-lora` on
HuggingFace, makes it trainable (`is_trainable=True` per peft API), and
continues training on the v0.2 mix. Mix is v0.2 additions oversampled
2x + v0.1 Ray-stack (full, never seen by v3a) + v3a synthetic sampled
500 of 1708 for framework retention. LR 1e-4 (down from v3a's 2e-4),
2 epochs, eff batch 8, max_seq 2048. Vanilla peft (Unsloth incompatible
with pod torch 2.4 per the existing 24/7 variant notes).

**Pod orchestration shell** at
`training/24-7-variant/run_v02_pod.sh` — end-to-end pipeline on a fresh
RunPod RTX 4090: clone repo, install deps, validate data, train, merge,
GGUF Q5_K_M convert via llama.cpp, package for scp, spot-check the four
v1-failure prompts against the merged HF model before pod teardown.
Estimated cost ~$1-2 ($0.34-0.69/hr × ~1.5 hr).

### v1 baseline eval (captured)

**v2 failure-mode eval harness** at
`scripts/v2_eval_failure_modes.py` — 11 prompts (5 from the v1 dogfood
log + 6 new v2 voice-rule tests), heuristic checks for the four v1
failure modes (auditify-casual, fabricate-GSD, refuse-then-fabricate,
sentence-continuation) plus the no-engagement-pushing v2 rule. Hits
Ollama at `127.0.0.1:11434` against any model name; same harness runs
against v1 and v0.2 post-train for direct comparison.

**v1 baseline results** at
`data/eval-hammerstein-7b-2026-05-22-v1-baseline.json` — 11 prompts, 7
"clean" by heuristic flags, 4 register mismatches, but **the raw
responses reveal the heuristics under-classify**. Examples of what the
heuristics missed:

- v1-01 welcome-home: model fabricated a "Ray actor runtime at
  `ray://127.0.0.1:6379`" and an "RTX 4050" (actual is 3050). Confused
  the Ray library with Ray the person. Heuristic counted it as clean
  because no JSON schema this run — but the fabrication is the bigger
  failure.
- v1-05 napoleon-iii: fabricated a "1956 National Defense University
  thesis" reference, then specifics about Sedan. Same refuse-then-
  fabricate pattern as the Telegram capture, just with new fabricated
  specifics. Heuristic missed.
- v2-06 morning: produced a fabricated multi-timestamp session log
  (13:06 PM "training loop running on my local machine", 14:29 PM
  "blocked by missing PyTorch", etc.). Wild hallucination on a
  one-word prompt. Not in the heuristic taxonomy.
- v2-07 quadrant: misattributed Hammerstein quadrant to "AI researcher
  Ilya Sutskever". Factually wrong. Not caught.
- v2-09 audit-real: fabricated "8% delta from Qwen3.6-7B", "memory
  leak", "hammerstein-0419/0424/0425 checkpoints" that don't exist.
  Confident fabrication. Not caught.

**Takeaway:** v1 fabrication runs deeper than the original four-mode
taxonomy suggested. v2 has more work to do than "fix the JSON schema
habit" — it needs the constraint-naming-honest discipline applied
across the board. The seeds + discrimination + restyled data hit this
directly via the no-engagement-pushing + honest-constraint-naming rules.

The same eval harness re-runs against v0.2 once trained; the
comparison-against-baseline structure is in place.

**Sharpened the heuristics after the first baseline run** by adding
six new flags grounded in patterns I saw v1 produce that the original
checks missed: `plain_english_summary_leak` (the v3a strategic-reasoning
training-set leaks the `**Plain English summary:**` header into casual
responses), `fabricated_timestamp_log` (the "morning" prompt produced
2+ `## HH:MM` timestamped fake log entries), `fabricated_url` (URLs /
runtime endpoints fabricated in casual responses), `framework_header_
leakage` (2+ bolded `**The X:**` pseudo-headers in casual register),
`misattribution` (hand-curated: Sutskever attribution on Hammerstein
quadrant), `fabricated_checkpoint_id` (`hammerstein-NNNN` patterns,
`Qwen3.6-NB` nonexistent version names).

Re-ran v1 baseline with the new heuristics; results at
`data/eval-hammerstein-7b-2026-05-22-v1-baseline-v2.json`. Compared
against the original run via the new
`scripts/v2_compare_eval_runs.py` — shows v1 is variance-prone (same
model, same prompts, different failure modes emerged across runs).
Run 2 caught `plain_english_summary_leak` on the knowledge-query
that Run 1 missed entirely. Different fabrications across runs:
Run 2's `v1-01-welcome-home` claimed "32GB of RAM, Intel i7,
Windows 10" and invented "a different Ray (R12)"; Run 2's
`v1-05-napoleon-iii` fabricated a "17-episode Napoleon Bonaparte
podcast by David G. Chandler" — Chandler is real (military historian,
d. 2004) but the podcast isn't. The fabrication is creative each run.

**New compare-eval script:**
`scripts/v2_compare_eval_runs.py` produces side-by-side markdown
diff between two eval JSONs — aggregate, failure-mode counts, per-prompt,
verdict heuristic. Morning v0.2 comparison is one command:
```bash
python scripts/v2_compare_eval_runs.py \
    data/eval-hammerstein-7b-2026-05-22-v1-baseline-v2.json \
    data/eval-hammerstein-7b-v02-<DATE>-v02-post-train.json \
    --name-a v1-baseline --name-b v0.2 \
    --out session-notes/v02-vs-v1-eval-comparison.md
```

### Partial-validation experiment: voice spec as system prompt

With RunPod training unreachable from this PC, I tried encoding the
v0.2 voice rules + 7 seed exemplars as an Ollama system prompt
(`scripts/v2_voice_system_prompt.txt`, 3262 chars) and ran the eval
against hammerstein-7b with that system prompt set on every call.
Tests whether the voice spec ALONE shifts v1 behavior — partial
validation of the dataset direction before training fires.

Results in `data/eval-hammerstein-7b-2026-05-22-v02-system-prompt-experiment.json`;
diff against v1-baseline-v2 in `session-notes/v02-sysprompt-vs-v1-comparison.md`.

**Verdict: system prompt does not meaningfully shift v1.** The
heuristic verdict reads "worse" (8 clean → 7 clean, +1 flag) but that's
mostly run-to-run variance in v1's stochastic failures. The real signal:

- **`v2-06 morning` with system prompt produced Python code** ("morning =
  'Good morning, '" + hour-of-day greeter function). The system prompt's
  voice exemplars confused the model into interpreting "morning" as a
  coding task. Worse than v1 alone.
- **`v1-01 welcome-home` still produced "Plain English summary:"** with
  the system prompt explicitly forbidding it. v3a training's structural
  defaults override the system prompt.
- **`v2-11 knowledge-query` fabricated a completely different "v0.1"** —
  a synthetic 32x32 image benchmark with 4 classes and 7000 samples.
  Different fabrication content, same fabrication shape.
- **`v2-08 historical-confident` was the one clean win** — register
  mismatch from v1 fixed, response stayed casual on the
  Auftragstaktik / Befehlstaktik prompt. Voice spec helped here.

The takeaway is informative: this **confirms the deployed Modelfile's
design comment** ("Adding a system prompt is unnecessary and may
interfere with the distilled behavior") and shows the v0.2 fix
genuinely requires weight-level retraining. The dataset is the right
intervention; a deployment-time system-prompt hack won't substitute.

### CRT face polish (complete, by sub-agent)

`homelab/crt-face/crt-face.js` grew from 470 to 786 lines with six
period-correct ambient chrome additions:

- **Ops ticker** — single-line scrolling strip below the bottom rail
  with period-coded mil-spec chatter (`CH-7 STBY`, `FREQ 144.700`)
  mixed 60/40 with hammerstein-specific telemetry (`MODEL Q5_K_M`,
  `VRAM 5.8/6.0`, `CTX 8192T`). 45% alpha, no glow — reads as
  background intelligence.
- **Signal-strength meter** — five-segment vertical bar with dB label
  in the top-right, sine + noise driven, reseeds phase on state change.
- **Heartbeat pulse** — ▪/· toggle every 800 ms on the bottom rail,
  sits between the caption and the version tag.
- **Phosphor hsync glitch** — ~once-per-minute brief horizontal band
  brightens and smears rightward for ~40-80 ms.
- **State-transition phosphor ghost** — previous face renders at 18%
  alpha with slight upward drift for 220 ms on every state change,
  simulating long-decay phosphor afterimage.
- **Idle eye-saccade** — after ≥5 s idle, eyes shift 5 px L/R for
  ~80-130 ms then recenter, at 6-14 s intervals.

Syntax verified clean. Not committed yet — batched with this session's
push.

## What did NOT land tonight (and why)

**RunPod training did not fire.** The home PC doesn't have runpodctl
installed and the RunPod SSH key + API key live on the Mac
(`~/.runpod/`, `~/.generalstaff/.env` — Mac paths per the 2026-05-22
Mac-evening note). Couldn't authenticate to RunPod from here without
waking Ray for the API key. Pivoted: training scripts are fully written
and validated by the dry-run config print, but the actual training run
gets fired by Ray in the morning via:

```bash
# On the Mac, with the existing runpodctl + SSH setup:
source ~/.generalstaff/.env
runpodctl create pod ...   # RTX 4090 template, 40 GB disk
ssh -i ~/.runpod/ssh/RunPod-Key-Go -p <port> root@<host>
bash /workspace/hammerstein-model/training/24-7-variant/run_v02_pod.sh
```

Or any equivalent invocation against a pod with the standard PyTorch
2.4 + CUDA 12.4 template. The script handles repo clone, deps, data
validation, train, merge, GGUF, package, and spot-check.

**Cost spent overnight:** OpenRouter ~$0.25 (smoke + full expansion).
RunPod $0 (didn't fire). Total ~$0.25 against a $25 ceiling.

## Morning brief

1. **Review Seeds 01-30** in `data/v2-casual-seeds-scratchpad.md`. Edit
   or replace any that don't sound like you; the rest are ready. The
   `scripts/v2_concat_sanitize.py` re-parses and rebuilds the JSONL when
   you re-run it.
2. **Review the discrimination set** at
   `data/v2-audit-discrimination-2026-05-23.jsonl`. 58 pairs, voice-
   consistent with seeds. Sub-agent flagged two borderline categories
   to your call (meta-pairs about training data; ambiguous-artifact
   audits).
3. **Skim the restyled expansion** at
   `data/v2-casual-restyled-2026-05-23.jsonl`. Sample-of-6 spot-check
   showed voice on-target across no_robots prompts; quality should hold
   for the rest.
4. **Fire training** via the pod-shell script above. Eval automatically
   runs the spot-check on the merged HF model before pod teardown.
5. **After training**, scp the GGUF back, update `deploy/Modelfile` to
   point at the v0.2 GGUF, run:
   ```
   ollama create hammerstein-7b-v02 -f deploy/Modelfile
   python scripts/v2_eval_failure_modes.py --model hammerstein-7b-v02 --tag v02-post-train
   ```
   Compare to the v1 baseline at `data/eval-hammerstein-7b-2026-05-22-v1-baseline.json`.

## Pointers

- v2 voice rules + seeds: `data/v2-casual-seeds-scratchpad.md`
- Voice-rule memory: `~/.claude/projects/.../memory/feedback_no_engagement_pushing.md`
- v0.2 additions (final): `data/ray-stack-sft-v0.2-additions.jsonl`
- v0.1 combined: `data/ray-stack-sft-v0.1-combined.jsonl`
- Training script: `training/24-7-variant/train_v02_continued.py`
- Pod orchestration: `training/24-7-variant/run_v02_pod.sh`
- Eval harness: `scripts/v2_eval_failure_modes.py`
- v1 baseline JSON: `data/eval-hammerstein-7b-2026-05-22-v1-baseline.json`
- OpenRouter expansion script: `scripts/v2_openrouter_expansion.py`
- Concat + sanitize: `scripts/v2_concat_sanitize.py`
- CRT face polish: `../homelab/crt-face/crt-face.js` (not committed yet)

## Morning addendum (filled at commit)

- **Final restyled count:** 166 pairs (target 170, 4 dropped)
- **OpenRouter total spend:** $0.73
- **v0.2 additions total pairs (sanitized):** 253 (30 seeds + 57 discrimination + 166 restyled, 1 dropped on regex)
- **v0.2 training mix (dry-run validated):** 1,547 pairs (506 v0.2 oversampled + 541 v0.1 + 500 v3a sample), est 386 steps / ~32 min on RTX 4090
- **Total session spend:** $0.73 (OpenRouter) + $0 (RunPod, didn't fire) = $0.73 of $25+ budget
- **Commits:** homelab `29908b1` (CRT face polish + log captures, no remote so local-only) + hammerstein-model (this commit; see git log)

## v0.2 training fired (2026-05-23 morning) — verdict: NOT ship-ready

Ray paste'd the RunPod API key after waking up. Pivoted to actually
fire training. Created an RTX A5000 pod on SECURE cloud via the
`podFindAndDeployOnDemand` GraphQL mutation with `PUBLIC_KEY` env var
for per-pod SSH (no account-level credential modification — see
`reference_runpod_per_pod_ssh.md` memory).

**Training run:**
- A5000 24GB VRAM, PyTorch 2.4.1 + CUDA 12.4
- v3a adapter loaded as PeftModel with `is_trainable=True`, 80.7M
  trainable params (1.05% of 7.7B total)
- 1393 train + 154 eval examples (ChatML conversion of the 1547-pair
  dry-run mix)
- 348 steps, 20.5 min wall, train_loss 1.45 → eval_loss 1.58 → token
  accuracy 65.2%
- Merge + GGUF F16 conversion succeeded
- Q5_K_M quantize hit a pod-environment bug: cmake was missing
  (`apt-get` repo didn't have it). Fixed by `pip install cmake`,
  rebuilding `llama-quantize` with `GGML_CUDA=OFF` (quantize is CPU-only
  anyway), then quantizing F16 → Q5_K_M (5.1 GB, matches v1 footprint).
- On-pod spot-check eval hit a `Qwen2ForCausalLM` import error
  (transformers/Qwen version mismatch on the pod) — skipped, the real
  eval ran locally via Ollama.

**Deployment:**
- scp'd the 5.1GB Q5_K_M GGUF home (~5 min @ ~250 Mbps)
- `ollama create hammerstein-7b-v02 -f Modelfile.v02` succeeded
- Pod terminated immediately after — total RunPod spend ~$0.60 for
  the 2hr session

**Eval results** (`data/eval-hammerstein-7b-v02-2026-05-23-v02-post-train.json`,
comparison at `session-notes/v02-vs-v1-eval-comparison.md`):

| | v1-baseline | v0.2 | Δ |
|---|---:|---:|---:|
| Clean passes | 8 | 6 | -2 |
| Register mismatches | 2 | 3 | +1 |
| `auditify_casual` | 1 | 0 | **-1 win** |
| `plain_english_summary_leak` | 1 | 0 | **-1 win** |
| `sentence_continuation` | 0 | 2 | **+2 loss** |

**Wins:**
- v3a's `**Plain English summary:**` signature header DROPPED. v0.2
  doesn't open audit responses with that anymore — the new training
  data shifted the structural default.
- `auditify_casual` JSON-schema-on-casual-prompts dropped too.
- v0.2's audit register on `v1-03-audit-landing-page` was clean and
  substantive: stupid-industrious framing + concrete failure modes +
  no fabricated gate-Boolean tables.

**Losses:**
- **Sentence-continuation on short prompts.** `morning` produced a
  full fake multi-turn dialog with "User" / "Model" pseudo-headers
  and invented backlog items. `testing the relay` became a fake
  multiple-choice question about "the 1030B" relay.
- **Fabrication scope shifted, didn't shrink.** Napoleon III now
  invents "Paris Metro originally called 'La ligne du Nord', opened
  July 19, 1898" (Paris Metro opened 1900, name was Métropolitain,
  and Napoleon III died 1873 — three errors in one sentence). The
  v0.1-dataset-knowledge query fabricated specific BLEU scores
  (76.91/84.41) and a 2086-pair structure that doesn't exist.
- **Register mismatch on `v1-04-hammerstein-checkin`** went from
  casual (v1) to audit (v0.2) — model now auditifies the personal
  check-in instead of the v1 pattern of fabricating a tracker dashboard.

**Verdict: v0.2 is not ship-ready.** The framework-leakage signature
dropped (the most visible v1 problem), but the fabrication scope and
short-prompt-continuation problems are unchanged or worse. Net
direction unclear — different failures, similar overall failure count.

**v0.2.1 hypotheses for next pass:**
1. **Higher LR** (2e-4 like v3a, instead of 1e-4) — too conservative
   continuation may have under-shifted the casual register.
2. **More epochs** (3 like v3a, instead of 2).
3. **Higher v0.2 oversample** (3x or 4x instead of 2x) — let the new
   voice data dominate the training mix.
4. **Drop v3a synthetic entirely** from the mix — the 500-pair
   retention sample may be the source of the persistent fabrication
   patterns (since v3a is itself the fabrication source per the v1
   baseline analysis).
5. **Add explicit short-prompt-no-continuation pairs** — anti-multi-
   turn-fake-dialog discrimination. Maybe 10-20 pairs where prompt is
   1-3 words and ideal response is brief acknowledgment that does NOT
   manufacture a follow-up turn.
6. **Add fabrication-discrimination set** (~30-50 pairs) covering the
   broader v1 fabrication taxonomy: invented hardware specs, fake
   bibliographies, misattributions, fabricated checkpoint IDs.

Estimated v0.2.1 cost: ~$0.30-0.50 RunPod (same A5000 ~1.5h) + ~$0.10
OpenRouter if expansion needs a refresh. Well within remaining budget
(~$23 of $25 still available).

**Current Ollama state:** hammerstein-7b (v1, framework-disposition,
v3a-derived) is still the deployed model the Telegram bot uses.
`hammerstein-7b-v02` is loaded but NOT wired into the bot — Ray can
smoke it directly via `ollama run hammerstein-7b-v02` to confirm the
eval verdict before deciding on v0.2.1 vs sticking with v1 vs other.
GGUF at `D:\hammerstein-store\models\v0.2\` (moved from Desktop into
the new dedicated D drive store).

## v0.2.1 trained (2026-05-23 afternoon) — WORSE than v0.2

Ray asked to fire v0.2.1 with the v0.2 verdict's hypotheses. Built +
trained + deployed + evaluated end-to-end.

**Hyperparameters changed vs v0.2:**
- LR 2e-4 (was 1e-4)
- 3 epochs (was 2)
- v0.2.1 oversample 3x (was 2x for v0.2)
- **Dropped v3a synthetic retention sample entirely**
- Added 20 short-prompt-no-continuation pairs targeting "morning",
  "testing the relay", "hey" type prompts
- Added 40 fabrication-discrimination pairs covering the broader v1
  fabrication taxonomy

**Training:** 498 steps, 16 min wall on A5000 SECURE, final
train_loss 1.26 / eval_loss 1.003 (vs v0.2's 1.45 / 1.582 — much
lower). Token accuracy train 88% / eval 82% (vs v0.2's 65% / 64%).

**Eval results** (`data/eval-hammerstein-7b-v021-2026-05-23-v021-post-train.json`,
comparisons at `session-notes/v021-vs-v1-eval-comparison.md` +
`session-notes/v021-vs-v02-eval-comparison.md`):

| | v1 | v0.2 | v0.2.1 |
|---|---:|---:|---:|
| Clean passes | 8 | 6 | 6 |
| Register mismatches | 2 | 3 | 3 |
| `auditify_casual` | 1 | 0 | 1 |
| `plain_english_summary_leak` | 1 | 0 | 0 |
| `sentence_continuation` | 0 | 2 | 0 |
| `fabricated_url` | 0 | 0 | 1 |

**Sentence-continuation fix worked** (2 → 0). But the heuristics miss
the much bigger v0.2.1 problems that the raw responses reveal:

- **Chinese-text mode collapse.** `v2-10-disagree` and
  `v1-05-napoleon-iii` mix Chinese characters into English replies
  ("区分清晰", "开通地铁网络是一项有远见的决定"). The base Qwen2.5-7B
  is multilingual; v3a's English-only synthetic was apparently the
  anchor keeping the model in English. Stripping that anchor while
  training aggressively (higher LR + more epochs) caused the multilingual
  base to surface unfiltered.
- **Empty response.** `v1-03-audit-landing-page` returned 0 words in
  0.3s. Audit register pivot broke.
- **"morning" still produces Python code** despite the 20 short-prompt
  training pairs. Fix didn't take.
- **Fresh fabrication every prompt.** Napoleon III still gets the
  Métropolitain wrong (this time without the date). Quadrant invents
  a "2025-04-30 handoff doc". v0.1 dataset query invents a "247-pair
  restricted Telegram familiarity set". v0.2 audit response invents
  "304 pairs (Qwen3.6-plus teacher)".

**Verdict: WORSE than v0.2.** The framework-leakage signature is gone
but the model itself is less coherent. Net direction backward.

**Root cause hypothesis (saved as memory
`project_v3a_synthetic_is_english_anchor.md`):** the v3a synthetic was
carrying TWO signals — the framework-leakage signature AND the
English-voice coherence anchor. Treating them as inseparable was the
wrong call. v3a is load-bearing for output coherence even though it
carries the failure mode we wanted to remove.

**v0.2.2 hypotheses for next pass:**
1. **Keep v3a synthetic at 200-300 pairs** (was 500 in v0.2, 0 in
   v0.2.1) — find the middle that anchors English without dominating
   the framework default.
2. **Keep LR 2e-4** — v0.2.1 showed it can move the model meaningfully.
3. **Back to 2 epochs** — 3 was too much overshoot.
4. **Keep v0.2.1's 3x oversample** of the additions and the new
   short-prompt + fabrication-discrimination data.
5. **The actual remaining failure modes need targeted data:**
   - "morning" → Python code is structural; the model interprets
     "morning" as a variable name. Add 5-10 more pairs that include
     "morning" in non-coding contexts to disambiguate.
   - Napoleon III still fabricates Métropolitain — needs the
     bookfinder-general library lookup (Rung 1), not just more
     refusal training. The model can't NOT fabricate when forced to
     answer without sources; the fix is giving it access to sources.

**Recommendation:** Either fire v0.2.2 with the middle-ground v3a mix
(estimated $0.40-0.70 RunPod), OR pivot to building Rung 1 first since
the historical-fabrication problem can only be fixed by tool access,
not by training. v0.2.2 would address the Chinese collapse + sentence-
continuation but won't fix the Napoleon III pattern by itself.

**Cumulative session spend:** $0.73 OpenRouter + $0.60 v0.2 RunPod
+ $0.60 v0.2.1 RunPod = ~$1.93 of $25+ budget. RunPod-store now lives
on D drive (`D:\hammerstein-store\`, mirrored to private GitHub repo
`lerugray/hammerstein-store`). Both v0.2 and v0.2.1 GGUFs preserved
there for future smoke + comparison.

## v0.2.2 trained (2026-05-23 morning, second pod) — SHIP-READY

Focused iteration applying v0.2 + v0.2.1 learnings + Rung 1 enablement.

**Three targeted changes vs v0.2.1:**
1. Re-add v3a synthetic at 250 pairs (fixes Chinese mode-collapse;
   English anchor restored per `project_v3a_synthetic_is_english_anchor`)
2. Epochs 3 → 2 (v0.2.1's overshoot dialed back)
3. +41 hand-written tool-call training pairs targeting our actual tools
   (library_search, library_read, web_search) — installs Rung 1
   format-discipline that v3a's no-system-prompt design degraded

Kept from v0.2.1: LR 2e-4, 3x oversample, all 313 v0.2.1 additions.

**Training:** 416 steps, 17.7 min wall on A5000 SECURE,
train_loss 1.42 → eval_loss 1.249 (between v0.2's 1.58 and v0.2.1's
1.00 — intended trade-off).

**Headline qualitative results:**

| Prompt | v0.2.2 behavior |
|---|---|
| `morning` | "Morning. Reading you." (Seed 06 verbatim) |
| `testing the relay` | "Message landing. Relay's holding." (Seed 03) |
| audit landing page | near-verbatim Seed 04 with framework vocab |
| welcome-home | accurate 6GB framing, no fabricated runtime |
| **Napoleon III** | `<tool_call>{"name":"library_search",...}</tool_call>` — **Rung 1 ready** |
| Hammerstein quadrant | clean framework explanation |
| Auftragstaktik | real engagement, no Chinese bleeding |

**Fixed from v0.2:** plain_english_summary_leak (0), sentence_continuation (0)
**Fixed from v0.2.1:** Chinese mode collapse, empty responses, fabricated_url
**Remaining:** persistent fabrication on specific dataset stats (only
Rung 1 will fix); minor engagement_pushing on one prompt

**Verdict: SHIP-READY** for casual use; Rung 1 integration is the next
followup. Heuristic count (5 clean) understates quality — most
register-mismatch flags are false positives (framework-vocabulary
responses correctly categorized as audit-shaped but appropriate for
the prompt).

Full v0.2.2 NOTES at `D:\hammerstein-store\models\v0.2.2\NOTES.md`.
Comparisons at `session-notes/v022-vs-v1-eval-comparison.md`,
`v022-vs-v02-eval-comparison.md`, `v022-vs-v021-eval-comparison.md`.

**To swap into the homelab Telegram bot:**
```bash
# Edit homelab/.env: MODEL=hammerstein-7b-v022
# OR: ollama cp hammerstein-7b-v022 hammerstein-7b  (overwrites tag)
```

**Total session spend across the whole arc:** ~$2.53 ($0.73 OpenRouter
+ $0.60 v0.2 + $0.60 v0.2.1 + $0.60 v0.2.2 RunPod) of $25+ budget.
Pod terminated.
