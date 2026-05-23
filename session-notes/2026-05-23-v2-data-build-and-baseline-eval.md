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
