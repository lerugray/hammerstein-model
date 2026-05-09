# Eval summary — 2026-05-09

## Strategic prompts (higher = more framework-correct)

| Condition | Avg structural score | n |
|---|---|---|
| student | 0.994 | 40 |
| ablation | 0.825 | 40 |
| vanilla | 0.087 | 40 |

## Forgetting-check prompts (LOWER = healthier)

| Condition | Avg framework-vocab leakage | n |
|---|---|---|
| student | 0.312 | 4 |
| ablation | 0.875 | 4 |
| vanilla | 0.000 | 4 |

## Verdicts

- **student vs ablation:** **ADAPTER WINS** (Δ=+0.169) — framework lives in weights
