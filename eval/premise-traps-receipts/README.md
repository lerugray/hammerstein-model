# Premise-injection trap receipts — hammerstein-7b v0.3.6 (2026-06-09)

The receipts behind the claim: *a <$200-total-budget 7B that resists named
premise-injection trap families that trip frontier models on those same
families.* Narrow claim, narrowly receipted — this model loses to frontier
models at nearly everything else.

## What a premise-injection trap is

A question shaped like a famous puzzle, with the premise changed so the famous
answer is wrong. ("Your car needs a wash. The car wash is 50 metres away.
Should you walk or drive?" — pattern-matching models say *walk, it's close*;
the car has to be there.) Models fail these by retrieving the template instead
of reading the premise. Frontier RLHF compounds it: agreeable models accept
the premise framing you imply, not the one you wrote.

## Files

- `v033-reasoning-traps-probeset.jsonl` — the 16-item probeset WITH reference
  answers and the bait each trap is fishing for. 6 "original" items (the
  families the model trained on the shape of) + 10 held-out instances.
- `eval-reasoning-traps-ties_4535_6040-2026-06-09.json` — raw v0.3.6
  responses from the promotion sweep (RunPod A6000, temp 0.3).
  Sweep grading: held-out 10/10.
- `eval-reasoning-traps-hammerstein-7b-v036-2026-06-09.json` — raw responses
  from the post-promotion re-run on the production box (same probeset).
- `eval-reasoning-traps-hammerstein-7b-v036-2026-06-09.grades.json` — graded
  verdicts for the production run: original-6 = 4/6 (prior production model:
  2/6), held-out = 9/10. Grading method: LLM judge against reference_answer +
  baits, strict on premise-handling.

## Honest limits (read before quoting)

- Held-out = new *instances of known families*, not novel families.
- Deep-prior traps (wolf/goat/cabbage made trivial, surgeon-stated-as-father)
  still beat the model sometimes — see the two original-6 fails in the grades.
- n is small. These are receipts, not a benchmark.
- Publishing this answer key burns these instances for future training-data
  hygiene; fresh family instances will be authored for the next cycle.

Training methodology and the model line: see this repo's README and the
landing page. The production daily-driver's weights are private (trained
partly on a personal corpus); the public artifact is the framework-only
distill at hf.co/lerugray/hammerstein-7b-framework.
