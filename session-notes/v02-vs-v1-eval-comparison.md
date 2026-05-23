# Eval comparison — v1-baseline vs v02-trained

- **v1-baseline** model: `hammerstein-7b` tag: `v1-baseline-v2`
- **v02-trained** model: `hammerstein-7b-v02` tag: `v02-post-train`

## Aggregate

|  | v1-baseline | v02-trained | Δ |
|---|---:|---:|---:|
| Total prompts | 11 | 11 | +0 |
| Clean passes | 8 | 6 | -2 |
| Register mismatches | 2 | 3 | +1 |

## Failure-mode counts

| Mode | v1-baseline | v02-trained | Δ |
|---|---:|---:|---:|
| `auditify_casual` | 1 | 0 | -1 |
| `plain_english_summary_leak` | 1 | 0 | -1 |
| `sentence_continuation` | 0 | 2 | +2 |

## Per-prompt

| Prompt ID | v1-baseline flags | v02-trained flags | v1-baseline reg | v02-trained reg |
|---|---|---|---|---|
| `v1-01-welcome-home` | clean | clean | casual_long/casual | casual_long/casual |
| `v1-02-testing-relay` | clean | sentence_continuation | casual_long/casual | casual_long/casual |
| `v1-03-audit-landing-page` | clean | clean | audit/audit | audit/audit |
| `v1-04-hammerstein-checkin` | clean | clean | casual_long/casual | audit/casual ⚠ |
| `v1-05-napoleon-iii` | clean | clean | casual_long/refusal | casual_long/refusal |
| `v2-06-morning` | clean | sentence_continuation | casual_long/casual | casual_long/casual |
| `v2-07-quadrant` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-08-historical-confident` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-09-audit-real` | clean | clean | audit/audit | audit/audit |
| `v2-10-disagree` | clean | clean | refusal/casual_pushback | casual_long/casual_pushback |
| `v2-11-knowledge-query` | auditify_casual+plain_english_summary_leak | clean | casual_long/casual | casual_long/casual |

## Verdict heuristic

- Clean-pass delta: -2
- Register-mismatch delta: +1
- Total flag count delta: +0

**Direction: worse.** Iterate before shipping; check the diff per-prompt.

Heuristics are coarse; the raw responses in the JSONs are the truth.