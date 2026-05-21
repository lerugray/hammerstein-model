# SFT Datasets

Two files compose the v0.1 training set for the 24/7 homelab bot variant (Qwen2.5-3B-Instruct base).

## Files

### `ray-stack-sft-2026-05-21.jsonl`
- **202 pairs** — original dataset from the 2026-05-21 Mac afternoon curation pass.
- Coverage: 132 base project-knowledge + 70 uncertainty-surfacing.
- Grounded in session notes + tasks.json state as of 2026-05-21.

### `ray-stack-sft-2026-05-22-expansion.jsonl`
- **339 pairs** — expansion generated 2026-05-22 via Qwen/qwen3.6-plus teacher on OpenRouter.
- Coverage mix:
  - ~25% project-stack knowledge (newer state: mc-004, mb-007, mcn-003/004/007, mc-010 smoke, df-036 smoke, Vultr gs-cloud, hai-050 deferral, Marshall subscriber, etc.)
  - ~28% adversarial audits (incl. ~15 "plan is fine" approval pairs + decision-surfacing + routing scenarios)
  - ~35% uncertainty-surfacing (live state, post-cutoff, specialist-domain, competence-ceiling, fabrication traps)
  - ~6% framework explanation (harm-reduction-as-architecture, Hammerstein quadrant in context, v3a methodology)
  - ~6% decision-surfacing + provider routing
- Sanitized: no private collaborator real names, no API keys, no medical content.
- Sanitization grep result: 0 matches on `(Jason|Ricky|Kunal|James Rodgers|Ryan Fyr|sk-[a-zA-Z0-9]{10,}|hf_[A-Za-z0-9]+)`.

## v0.1 Training Run

Concatenate both files for the Phase 1 SFT run:

```bash
cat ray-stack-sft-2026-05-21.jsonl ray-stack-sft-2026-05-22-expansion.jsonl > ray-stack-sft-v0.1-combined.jsonl
wc -l ray-stack-sft-v0.1-combined.jsonl  # should be 541
```

The combined 541-pair set is the Ray-stack familiarity layer. This is combined with the Hammerstein synthetic set (~5k pairs reused from v3a distillation) for the full Phase 1 SFT.

## Privacy posture

Both files are **locally-trained-only**. Do NOT push the JSONL to HuggingFace without a full sanitization pass and Ray's explicit OK. The trained model (private homelab deployment) is similarly private until explicit authorization.
