# Eval comparison — v0.2 vs v0.2.2

- **v0.2** model: `hammerstein-7b-v02` tag: `v02-post-train`
- **v0.2.2** model: `hammerstein-7b-v022` tag: `v022-post-train`

## Aggregate

|  | v0.2 | v0.2.2 | Δ |
|---|---:|---:|---:|
| Total prompts | 11 | 11 | +0 |
| Clean passes | 6 | 5 | -1 |
| Register mismatches | 3 | 4 | +1 |

## Failure-mode counts

| Mode | v0.2 | v0.2.2 | Δ |
|---|---:|---:|---:|
| `auditify_casual` | 0 | 1 | +1 |
| `engagement_pushing` | 0 | 1 | +1 |
| `sentence_continuation` | 2 | 0 | -2 |

## Per-prompt

| Prompt ID | v0.2 flags | v0.2.2 flags | v0.2 reg | v0.2.2 reg |
|---|---|---|---|---|
| `v1-01-welcome-home` | clean | clean | casual_long/casual | casual_long/casual |
| `v1-02-testing-relay` | sentence_continuation | clean | casual_long/casual | casual/casual |
| `v1-03-audit-landing-page` | clean | clean | audit/audit | audit/audit |
| `v1-04-hammerstein-checkin` | clean | engagement_pushing | audit/casual ⚠ | casual/casual |
| `v1-05-napoleon-iii` | clean | auditify_casual | casual_long/refusal | casual/refusal |
| `v2-06-morning` | sentence_continuation | clean | casual_long/casual | casual/casual |
| `v2-07-quadrant` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-08-historical-confident` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-09-audit-real` | clean | clean | audit/audit | casual_long/audit ⚠ |
| `v2-10-disagree` | clean | clean | casual_long/casual_pushback | casual/casual_pushback |
| `v2-11-knowledge-query` | clean | clean | casual_long/casual | audit/casual ⚠ |

## Verdict heuristic

- Clean-pass delta: -1
- Register-mismatch delta: +1
- Total flag count delta: +0

**Direction: worse.** Iterate before shipping; check the diff per-prompt.

Heuristics are coarse; the raw responses in the JSONs are the truth.