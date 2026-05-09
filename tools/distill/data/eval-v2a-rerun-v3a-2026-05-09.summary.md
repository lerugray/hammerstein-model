# Eval summary — 2026-05-09

## Strategic prompts (higher = more framework-correct)

| Condition | Avg structural score | n |
|---|---|---|
| student | 0.981 | 40 |
| ablation | 0.681 | 40 |
| vanilla | 0.087 | 40 |

## Forgetting-check prompts (LOWER = healthier)

| Condition | Avg framework-vocab leakage | n |
|---|---|---|
| student | 0.683 | 30 |
| ablation | 0.850 | 30 |
| vanilla | 0.000 | 30 |

## Verdicts

- **student vs ablation:** **ADAPTER WINS** (Δ=+0.300) — framework lives in weights
