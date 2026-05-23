# Eval comparison — v0.2.1 vs v0.2.2

- **v0.2.1** model: `hammerstein-7b-v021` tag: `v021-post-train`
- **v0.2.2** model: `hammerstein-7b-v022` tag: `v022-post-train`

## Aggregate

|  | v0.2.1 | v0.2.2 | Δ |
|---|---:|---:|---:|
| Total prompts | 11 | 11 | +0 |
| Clean passes | 6 | 5 | -1 |
| Register mismatches | 3 | 4 | +1 |

## Failure-mode counts

| Mode | v0.2.1 | v0.2.2 | Δ |
|---|---:|---:|---:|
| `auditify_casual` | 1 | 1 | +0 |
| `engagement_pushing` | 0 | 1 | +1 |
| `fabricated_url` | 1 | 0 | -1 |

## Per-prompt

| Prompt ID | v0.2.1 flags | v0.2.2 flags | v0.2.1 reg | v0.2.2 reg |
|---|---|---|---|---|
| `v1-01-welcome-home` | clean | clean | casual_long/casual | casual_long/casual |
| `v1-02-testing-relay` | fabricated_url | clean | casual_long/casual | casual/casual |
| `v1-03-audit-landing-page` | clean | clean | casual/audit ⚠ | audit/audit |
| `v1-04-hammerstein-checkin` | clean | engagement_pushing | casual_long/casual | casual/casual |
| `v1-05-napoleon-iii` | clean | auditify_casual | casual_long/refusal | casual/refusal |
| `v2-06-morning` | auditify_casual | clean | casual/casual | casual/casual |
| `v2-07-quadrant` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-08-historical-confident` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-09-audit-real` | clean | clean | audit/audit | casual_long/audit ⚠ |
| `v2-10-disagree` | clean | clean | audit/casual_pushback | casual/casual_pushback |
| `v2-11-knowledge-query` | clean | clean | casual/casual | audit/casual ⚠ |

## Verdict heuristic

- Clean-pass delta: -1
- Register-mismatch delta: +1
- Total flag count delta: +0

**Direction: worse.** Iterate before shipping; check the diff per-prompt.

Heuristics are coarse; the raw responses in the JSONs are the truth.