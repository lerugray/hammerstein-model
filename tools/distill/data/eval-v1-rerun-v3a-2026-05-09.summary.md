# Eval summary — 2026-05-09

## Strategic prompts (higher = more framework-correct)

| Condition | Avg structural score | n |
|---|---|---|
| student | 1.000 | 40 |
| ablation | 0.794 | 40 |
| vanilla | 0.081 | 40 |

## Forgetting-check prompts (LOWER = healthier)

| Condition | Avg framework-vocab leakage | n |
|---|---|---|
| student | 0.500 | 30 |
| ablation | 0.800 | 30 |
| vanilla | 0.000 | 30 |

## Verdicts

- **student vs ablation:** **ADAPTER WINS** (Δ=+0.206) — framework lives in weights
