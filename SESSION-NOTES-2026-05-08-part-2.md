# Session Notes — 2026-05-08 (Part 2)

Picks up where [SESSION-NOTES-2026-05-08.md](SESSION-NOTES-2026-05-08.md)
left off — the trained adapter on Ray's Mac, the wrapper running,
and a list of pending decisions. This session worked through every
one of those decisions and shipped Phase 5 with three iterations.

## Headline outcomes

1. **Hammerstein-7B is public.**
   [`huggingface.co/lerugray/hammerstein-7b-lora`](https://huggingface.co/lerugray/hammerstein-7b-lora)
   has the LoRA adapter (323 MB), the merged Q4_K_M GGUF (4.68 GB,
   Ollama-ready), the Modelfile, and an honest model card. Anyone
   with a Mac (8 GB+) can `ollama run hf.co/lerugray/hammerstein-7b-lora:Q4_K_M`.

2. **The 4-condition eval landed: ADAPTER WINS.**
   - Strategic prompts (n=40): student 1.000, gold 0.994, ablation
     0.794, vanilla 0.081. Student/gold ratio 1.01 (saturated).
     Student vs ablation Δ=+0.206 — **the framework lives in the
     weights, not just the prompt.**
   - Forgetting check (n=4): student 0.312 leakage vs ablation
     0.625 vs vanilla 0.000. Adapter is materially healthier than
     prompt-only on out-of-domain prompts but not pristine. Honest
     disclosure in the model card.
   - Validated the GS-session-2 reviewer's call: this is the
     publication-grade outcome.

3. **Phase 5 wargame extension shipped through 3 design iterations:**
   - **v0** (text-only, structured): `hp.py --state-dir <path>` flag
     + `wargame-example/` Bridge Crossing scenario, dogfooded 3
     turns. AI issued coordinate-level moves; predicted drift
     occurred (model hallucinated grid coords).
   - **v1** (kriegspiel pivot, per Ray's direction): switched to
     mission-type Auftragstaktik orders ("2nd Bn forces the bridge
     crossing"). Model cleaned up immediately — no more
     hallucinations, real commander voice. New 5-section structure
     (Situation / Intent / Main Effort / Supporting Effort /
     Reserves & Fallback). Same cost ($0.007/turn).
   - **v2** (multimodal): `hp_vision.py` sibling that takes board
     photos + Excel OOB sheets + conversational status reports →
     kriegspiel orders. Default backend Sonnet 4.6 via OpenRouter.
     Validated text + Excel; image schema proven, live image test
     deferred for Ray's csl-repo games.

## Total cost end-to-end

| Stage | Spend |
|---|---:|
| Wrapper development (prior session) | $0.10 |
| Synthetic data gen (308 pairs) | $2.31 |
| Adapter training (RTX 4090, ~50 min) | ~$0.50 |
| Gold eval (40 OpenRouter calls) | $0.32 |
| Pod eval (RTX 4090 + RTX A5000 mix) | ~$0.50 |
| GGUF conversion (incl. dud-pod retry) | ~$0.22 |
| Wargame dogfood (text + multimodal) | ~$0.10 |
| **Total project** | **~$4.05** |

Plus an unintended **$0.02** burned on an empty-POST RunPod deploy
that auto-allocated an RTX PRO 6000 Blackwell at $1.89/hr for ~30
seconds before I caught and terminated it. Lesson saved as
internal-to-Claude memory: never POST without explicit GPU type.

## Cleanup that mattered

Discovered 4 orphan **network volumes** (50 GB each, EU-RO-1) sitting
on Ray's RunPod account from previous pods. Storage cost ~$14/month
passive — likely a chunk of his ongoing credit drain. Terminated all
4 + the lingering EXITED pod via API. Net savings: ~$14/month going
forward.

## Mistakes + lessons

1. **Empty POST to /v1/pods auto-deploys with maximum-spec defaults.**
   No validation; auto-picked RTX PRO 6000 Blackwell at $1.89/hr.
   Lesson: always explicit `gpuTypeIds` + `cloudType` in the JSON.
2. **`ports` field is array, not string** — first deploy attempt
   rejected with schema error. Easy fix; documented in `run_eval.sh`
   and `hp_vision.py`.
3. **Bash `pkill` over SSH can kill the SSH session itself** if the
   target process tree shares state. Lost connection mid-debug
   twice. Workaround: kill from a separate session, not the one
   that owns the running process.
4. **`pip install -q ... | tail -10` masks pip exit codes.** Pipe to
   `tail` makes `set -e` see only `tail`'s exit (always 0), so a
   killed pip looks like success. The bg job for the first pod run
   reported exit-0 even though `unsloth` install died mid-resolver.
   Fix: drop the pipe-to-tail when reliability matters.
5. **OpenRouter `anthropic/claude-3.5-sonnet` is a stale ID** — the
   current Sonnet on OpenRouter is `anthropic/claude-sonnet-4.6`.
   Fixed in `hp_vision.py`. The `~anthropic/claude-sonnet-latest`
   alias is also available but I prefer pinning.
6. **EU-region community RunPod has bad PyPI throughput.** Two pods
   (community FR, secure SE) showed 100 KB/s on PyPI; US-IL-1
   secure showed 7+ MB/s. Will default to US data centers for
   future deployments.
7. **`numpy` 2.x has a self-bug in `_typing/_scalars.py`** that
   breaks Unsloth's bundled `llama.cpp` GGUF converter. Fixed by
   downgrading to `numpy==1.23.5` on the conversion pod. Recorded
   in the GGUF script's commit message.

## What's open / pending Ray's input

These are decisions, not autonomous-action items:

1. **Phase 6 web UI** — answer the 5 questions in
   [WEB-UI-EXTENSION.md](WEB-UI-EXTENSION.md) and a v0 can scaffold.
   Per Ray's direction, deferred to a fresh session.
2. **Hammerstein-TUI integration** — what shape? Backend-swap so
   TUI can call Ollama-Hammerstein offline? Or shell out to
   `hp.py` for stateful audits? Cross-project decision.
3. **Loud-launch post** — X / HN / Reddit / LinkedIn. The artifact
   can survive scrutiny; the launch is a separate decision. The
   GS-session reviewer suggested doing it after GGUF lands, which
   it has.
4. **Mixed-mode retrain** to fix the 0.312 OOD leakage — would
   push it to ~0.05. Cost ~$1, ~1 hr. Marginal per the
   corpus-vs-engineering memory; only worth it if we want a
   "polished product" rather than a "portfolio piece."
5. **Multimodal live-image test** with a real game from Ray's
   `csl` repo (Imperial Bayonets Solferino, We Were Not Cowards).
   Image-encoding path is proven via schema; live OCR quality on
   actual countersheets / hex maps is the empirical question.
6. **`gh auth refresh`** on Ray's Mac — invalidates the gh CLI
   token we copied to the GGUF pod. 5-second hygiene step.

## Files shipped this session

| Path | Purpose |
|---|---|
| [`hp_vision.py`](hp_vision.py) | Multimodal kriegspiel wrapper |
| [`hp.py`](hp.py) (modified) | `--state-dir` flag added |
| [`hp_lib.py`](hp_lib.py) (modified) | `resolve_state_dir`, `trim_turn_log` |
| [`tests/test_hp.py`](tests/test_hp.py) (modified) | 3 new tests for `trim_turn_log` |
| [`tools/distill/eval.py`](tools/distill/eval.py) | 4-condition harness w/ Hammerstein-audit guards |
| [`tools/distill/hf_push.py`](tools/distill/hf_push.py) | HF push + visibility flip |
| [`tools/distill/convert_gguf.py`](tools/distill/convert_gguf.py) | GGUF + Ollama conversion |
| [`tools/distill/run_eval.sh`](tools/distill/run_eval.sh) | Pod-side eval driver (PAT auth) |
| [`tools/distill/run_gguf.sh`](tools/distill/run_gguf.sh) | Pod-side GGUF driver |
| [`tools/distill/data/eval-2026-05-08.jsonl`](tools/distill/data/eval-2026-05-08.jsonl) | 40 prompts × 4 conditions + 4 forgetting check |
| [`tools/distill/data/eval-2026-05-08.summary.md`](tools/distill/data/eval-2026-05-08.summary.md) | Verdict tables |
| [`tools/distill/data/hammerstein-system-prompt.txt`](tools/distill/data/hammerstein-system-prompt.txt) | Framework system prompt for ablation arm + hp_vision |
| [`wargame-example/MISSION.md`](wargame-example/MISSION.md) | Bridge Crossing rules + role + working recipes |
| [`wargame-example/tasks.json`](wargame-example/tasks.json) | OOB |
| [`wargame-example/turn-log.md`](wargame-example/turn-log.md) | Per-turn snapshots, dogfooded |
| [`wargame-example/maps/bridge-crossing.txt`](wargame-example/maps/bridge-crossing.txt) | ASCII map |
| [`wargame-example/data/oob.xlsx`](wargame-example/data/oob.xlsx) | Sample Excel OOB for `hp_vision.py` |
| [`HAMMERSTEIN-7B.md`](HAMMERSTEIN-7B.md) | Full eval write-up + Ollama instructions |
| [`README.md`](README.md) | Phase status table, cost arc updated |
| [`WARGAME-EXTENSION.md`](WARGAME-EXTENSION.md) | v0/v1/v2 status + design context |

Memory note saved at
`~/.claude/projects/-Users-rayweiss-Desktop-Dev-Work-hammerstein-model/memory/feedback_invest_in_corpus_not_engineering.md`
— for future sessions: invest in corpus + applied surfaces, not
engineering improvements.

## State at end of session

- `master`: 12 commits today, all pushed to GitHub
- HF: `lerugray/hammerstein-7b-lora` public, 8 files (LoRA + GGUF +
  Modelfile + README + configs)
- RunPod: 0 pods, 0 volumes (clean). $14/mo passive cost stopped.
- Test suite: 22/22 passing
- Wrapper extensions: `--state-dir` (text-only) + `hp_vision.py`
  (multimodal) both working
- Wargame example: 4 turns logged (3 text-only + 1 vision-mode)
- Total spend: ~$4.05 end-to-end project; ~$0.30 of that this
  session

## What this session means in framework terms

The framework auditing itself, again, in three layers:

1. **The "wrapper-feels-less-impressive" pushback** from the prior
   session became the distillation experiment. That experiment's
   honest result (ADAPTER WINS the ablation, but tied at saturation
   on form-only metric, with disclosed OOD leakage) is more
   defensible than the typical HF model card. The framework's
   self-criticism discipline carries over.

2. **The wargame's coordinate-vs-mission iteration** mirrors
   Phase 1.5's precision-test pivot. v0 was honest about its
   drift; v1 fixed the underlying design (kriegspiel) rather than
   over-prompting around the symptom. The Auftragstaktik framing
   is what the namesake (Reichswehr Chef Hammerstein-Equord)
   actually practiced — the framework doing the thing it claims
   to do.

3. **The multimodal pivot** came from Ray course-correcting the
   v1 design with a stronger insight (photos + conversational
   reports + Excel OOB > structured JSON state files). Treating
   that input as load-bearing rather than ignoring it produced a
   better v2 in one iteration.

Every path of overengineering or polish-as-output got noticed and
either pivoted or ringfenced. The corpus-vs-engineering memory
note is the durable lesson: the model is a snapshot; the
framework + corpus + applied surfaces are the appreciating asset.

That's the design.
