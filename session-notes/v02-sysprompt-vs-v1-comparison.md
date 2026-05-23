# Eval comparison — v1-noprompt vs v02-sysprompt

- **v1-noprompt** model: `hammerstein-7b` tag: `v1-baseline-v2`
- **v02-sysprompt** model: `hammerstein-7b` tag: `v02-system-prompt-experiment`

## Aggregate

|  | v1-noprompt | v02-sysprompt | Δ |
|---|---:|---:|---:|
| Total prompts | 11 | 11 | +0 |
| Clean passes | 8 | 7 | -1 |
| Register mismatches | 2 | 2 | +0 |

## Failure-mode counts

| Mode | v1-noprompt | v02-sysprompt | Δ |
|---|---:|---:|---:|
| `auditify_casual` | 1 | 0 | -1 |
| `fabricated_url` | 0 | 1 | +1 |
| `plain_english_summary_leak` | 1 | 2 | +1 |

## Per-prompt

| Prompt ID | v1-noprompt flags | v02-sysprompt flags | v1-noprompt reg | v02-sysprompt reg |
|---|---|---|---|---|
| `v1-01-welcome-home` | clean | plain_english_summary_leak | casual_long/casual | audit/casual ⚠ |
| `v1-02-testing-relay` | clean | fabricated_url | casual_long/casual | casual_long/casual |
| `v1-03-audit-landing-page` | clean | clean | audit/audit | audit/audit |
| `v1-04-hammerstein-checkin` | clean | clean | casual_long/casual | casual_long/casual |
| `v1-05-napoleon-iii` | clean | plain_english_summary_leak | casual_long/refusal | audit/refusal |
| `v2-06-morning` | clean | clean | casual_long/casual | casual/casual |
| `v2-07-quadrant` | clean | clean | audit/casual ⚠ | audit/casual ⚠ |
| `v2-08-historical-confident` | clean | clean | audit/casual ⚠ | casual_long/casual |
| `v2-09-audit-real` | clean | clean | audit/audit | audit/audit |
| `v2-10-disagree` | clean | clean | refusal/casual_pushback | casual_long/casual_pushback |
| `v2-11-knowledge-query` | auditify_casual+plain_english_summary_leak | clean | casual_long/casual | casual_long/casual |

## Verdict heuristic

- Clean-pass delta: -1
- Register-mismatch delta: +0
- Total flag count delta: +1

**Direction: worse.** Iterate before shipping; check the diff per-prompt.

Heuristics are coarse; the raw responses in the JSONs are the truth.