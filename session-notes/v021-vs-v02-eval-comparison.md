# Eval comparison — v0.2 vs v0.2.1

- **v0.2** model: `hammerstein-7b-v02` tag: `v02-post-train`
- **v0.2.1** model: `hammerstein-7b-v021` tag: `v021-post-train`

## Aggregate

|  | v0.2 | v0.2.1 | Δ |
|---|---:|---:|---:|
| Total prompts | 11 | 11 | +0 |
| Clean passes | 6 | 6 | +0 |
| Register mismatches | 3 | 3 | +0 |

## Failure-mode counts

| Mode | v0.2 | v0.2.1 | Δ |
|---|---:|---:|---:|
| `auditify_casual` | 0 | 1 | +1 |
| `fabricated_url` | 0 | 1 | +1 |
| `sentence_continuation` | 2 | 0 | -2 |

## Per-prompt

| Prompt ID | v0.2 flags | v0.2.1 flags | v0.2 reg | v0.2.1 reg |
|---|---|---|---|---|
| `v1-01-welcome-home` | clean | clean | casual_long/casual | casual_long/casual |
| `v1-02-testing-relay` | sentence_continuation | fabricated_url | casual_long/casual | casual_long/casual |
| `v1-03-audit-landing-page` | clean | clean | audit/audit | casual/audit ⚠ |
| `v1-04-hammerstein-checkin` | clean | clean | audit/casual ⚠ | casual_long/casual |
| `v1-05-napoleon-iii` | clean | clean | casual_long/refusal | casual_long/refusal |
| `v2-06-morning` | sentence_continuation | auditify_casual | casual_long/casual | casual/casual |
| `v2-07-quadrant` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-08-historical-confident` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-09-audit-real` | clean | clean | audit/audit | audit/audit |
| `v2-10-disagree` | clean | clean | casual_long/casual_pushback | audit/casual_pushback |
| `v2-11-knowledge-query` | clean | clean | casual_long/casual | casual/casual |

## Verdict heuristic

- Clean-pass delta: +0
- Register-mismatch delta: +0
- Total flag count delta: +0

**Direction: mixed or neutral.** Manual read on the raw responses.

Heuristics are coarse; the raw responses in the JSONs are the truth.