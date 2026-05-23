# Eval comparison — v1 vs v0.2.1

- **v1** model: `hammerstein-7b` tag: `v1-baseline-v2`
- **v0.2.1** model: `hammerstein-7b-v021` tag: `v021-post-train`

## Aggregate

|  | v1 | v0.2.1 | Δ |
|---|---:|---:|---:|
| Total prompts | 11 | 11 | +0 |
| Clean passes | 8 | 6 | -2 |
| Register mismatches | 2 | 3 | +1 |

## Failure-mode counts

| Mode | v1 | v0.2.1 | Δ |
|---|---:|---:|---:|
| `auditify_casual` | 1 | 1 | +0 |
| `fabricated_url` | 0 | 1 | +1 |
| `plain_english_summary_leak` | 1 | 0 | -1 |

## Per-prompt

| Prompt ID | v1 flags | v0.2.1 flags | v1 reg | v0.2.1 reg |
|---|---|---|---|---|
| `v1-01-welcome-home` | clean | clean | casual_long/casual | casual_long/casual |
| `v1-02-testing-relay` | clean | fabricated_url | casual_long/casual | casual_long/casual |
| `v1-03-audit-landing-page` | clean | clean | audit/audit | casual/audit ⚠ |
| `v1-04-hammerstein-checkin` | clean | clean | casual_long/casual | casual_long/casual |
| `v1-05-napoleon-iii` | clean | clean | casual_long/refusal | casual_long/refusal |
| `v2-06-morning` | clean | auditify_casual | casual_long/casual | casual/casual |
| `v2-07-quadrant` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-08-historical-confident` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-09-audit-real` | clean | clean | audit/audit | audit/audit |
| `v2-10-disagree` | clean | clean | refusal/casual_pushback | audit/casual_pushback |
| `v2-11-knowledge-query` | auditify_casual+plain_english_summary_leak | clean | casual_long/casual | casual/casual |

## Verdict heuristic

- Clean-pass delta: -2
- Register-mismatch delta: +1
- Total flag count delta: +0

**Direction: worse.** Iterate before shipping; check the diff per-prompt.

Heuristics are coarse; the raw responses in the JSONs are the truth.