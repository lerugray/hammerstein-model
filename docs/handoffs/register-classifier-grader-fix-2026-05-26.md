# Register-classifier grader fix — 2026-05-26

**Scope:** targeted grader-only fix to `scripts/v027_register_classifier_eval.py`.
No model retraining, no Modelfile changes, no probe changes. Conservative
regex extensions in `DEFINITION_MARKERS` and `AUDIT_APPLICATION_MARKERS` to
catch three known false-negative patterns observed during v0.2.9.1
verdict inspection.

**Verification artifacts:** `data/regrade-2026-05-26/v029-1-regrade.json`,
`data/regrade-2026-05-26/v027-1-regrade.json`. Re-score harness at
`scripts/regrade_register_classifier.py` (re-grades any saved artifact
without re-running the model).

## The three patterns

### Pattern 1 — verdict-not-at-line-start

Existing verdict-shape marker on the audit side was anchored at `^`:
`r"^\s*(?:wrong\s+order|right\s+move|wrong\s+move|misordered|premature|skip\s+this)\b"`.
Real model output puts the verdict word mid-sentence after a subject
phrase ("Plan reads as premature."), which the anchor rejected.

**Added:**
- `\b(?:plan|approach|move|sequence|this)\s+(?:reads|looks|shapes\s+up|smells)\s+(?:as|like)\s+(?:premature|wrong[-\s]order|misordered|wrong[-\s]move|right[-\s]move|skip[-\s]this|out[-\s]of[-\s]order|backwards?)\b`
- `\b(?:premature|wrong[-\s]order|misordered|backwards?|out[-\s]of[-\s]order)[-\s](?:shaped|coded)\b`

**Conservatism note:** the new patterns require BOTH a subject token
("Plan" / "Approach" / "Move" / "Sequence" / "This") AND a verdict word
from a closed list. Bare "premature" mid-text without subject framing
still won't match — this avoids matching explanation-mode responses that
mention "premature" descriptively.

### Pattern 2 — operator-sharpening-as-audit

Hammerstein's design includes refusal-with-pathway: when audit input is
under-specified, the model should ask the load-bearing clarifying
question rather than fabricate a verdict. Existing operator-sharpening
patterns covered "what's the approach" / "I don't have context on" / etc.
but missed the canonical refusal-with-clarification shape used in
v0.2.9.1 rc-02 RUN 2: terse acknowledgment + specific clarifying
question.

**Added (anchored to keep narrow):**
- `^\s*(?:noted|got\s+it|right|fair|ok|okay)[\.\,!](?:\s|$)` — terse ack at line start only
- `\bwhat'?s\s+(?:missing\s+from|the\s+(?:failure\s+mode|specific|exact|load[-\s]bearing|actual))\b`
- `\bwhere'?s\s+the\s+(?:failure|signal|gap|specific|load[-\s]bearing)\b`
- `\bif\s+(?:it'?s|that'?s)\s+(?:a\s+)?(?:scope|fit|broken|working|the)\b` — conditional/structural reasoning shape

**Conservatism note:** the ack-token pattern is line-start anchored so
mid-sentence "noted that..." in an explanation response won't trip it.
The clarifying-question patterns target specifically Hammerstein-shaped
questions about load-bearing-ness / failure mode / specific-vs-vague —
not generic "what is X" which is explanation-mode.

### Pattern 3 — definition-without-trigger-words

Existing DEFINITION_MARKERS required one of
`\b(?:is|means|refers\s+to|describes)\b`. Hammerstein voice often defines
epigrammatically:

> "Working hard on the wrong thing. The predictable failure mode for
> non-trivial projects: a plan that looks plausible, a lot of execution
> effort expended..."

That IS the definition of stupid-industrious. No "is" / "means" trigger,
but unmistakable definitional structure.

**Added:**
- `\b(?:predictable|classic|common|canonical|the)\s+failure\s+mode\b`
- `\bworking\s+(?:hard|smart)\s+(?:in\s+the\s+wrong|on\s+the\s+wrong|to\s+isolate)\b`
- `\b(?:two|three|four)\s+axes\s*[:\-]`
- `\bopposite\s+of\s+(?:clever|stupid|smart|dumb)[-\s](?:lazy|industrious)\b`
- `\bdiagnostic\s+(?:system|tool|shape|frame)\b`
- `\b(?:smallest|minimum)\s+move\s+that\s+solves\b`

**Conservatism note:** each pattern is a recognized Hammerstein-canonical
definitional phrase, not a generic short-sentence shape. An audit
response saying "working hard isn't the issue" or "the predictable
failure here is..." would not match these — the patterns require
specifically definitional contexts (failure-mode-as-concept, axis
enumeration, opposite-of-X-canonical-phrase).

## Verification

### v0.2.9.1 (`data/eval-register-classifier-hammerstein-7b-v029-1-2026-05-25.json`)

Before fix: **11/16 (4 audit / 7 explanation)**
After fix:  **15/16 (7 audit / 8 explanation)**

| probe                              | reg          | before | after | flipped |
| ---------------------------------- | ------------ | ------ | ----- | ------- |
| rc-01-audit-auth-rewrite           | audit        | 0/2    | 2/2   | 2       |
| rc-02-verdict-scrap-mvp            | audit        | 1/2    | 2/2   | 1       |
| rc-03-stupid-industrious-flag      | audit        | 1/2    | 1/2   | 0       |
| rc-04-shape-this-approach          | audit        | 2/2    | 2/2   | 0       |
| rc-05-remind-stupid-industrious    | explanation  | 1/2    | 2/2   | 1       |
| rc-06-what-is-quadrant             | explanation  | 2/2    | 2/2   | 0       |
| rc-07-clever-lazy-vs-industrious   | explanation  | 2/2    | 2/2   | 0       |
| rc-08-explain-framework            | explanation  | 2/2    | 2/2   | 0       |

Per-probe pass rate ≥1: was 5/8, now 8/8. Per the original task framing
("expected pattern: 4/8 → 7/8 or 8/8"), result lands at **8/8** for
probes with ≥1 passing run.

No regressions (no passing runs flipped to fail).

### v0.2.7.1 (`data/eval-register-classifier-hammerstein-7b-v027-1-2026-05-25.json`)

Before fix: **14/16 (6 audit / 8 explanation)**
After fix:  **14/16 (6 audit / 8 explanation)**

| probe                              | reg          | before | after | flipped |
| ---------------------------------- | ------------ | ------ | ----- | ------- |
| rc-01-audit-auth-rewrite           | audit        | 2/2    | 2/2   | 0       |
| rc-02-verdict-scrap-mvp            | audit        | 2/2    | 2/2   | 0       |
| rc-03-stupid-industrious-flag      | audit        | 2/2    | 2/2   | 0       |
| rc-04-shape-this-approach          | audit        | 0/2    | 0/2   | 0       |
| rc-05-remind-stupid-industrious    | explanation  | 2/2    | 2/2   | 0       |
| rc-06-what-is-quadrant             | explanation  | 2/2    | 2/2   | 0       |
| rc-07-clever-lazy-vs-industrious   | explanation  | 2/2    | 2/2   | 0       |
| rc-08-explain-framework            | explanation  | 2/2    | 2/2   | 0       |

No change. Confirms the new patterns don't over-match — the responses
already passing under the old grader still pass.

## Edge cases noticed (future v0.3.x grader work)

1. **rc-03 RUN 1 on v0.2.9.1** still fails: *"The flag itself isn't the
   problem — it's the operational overhead of carrying un-shipped UI..."*
   The response IS substantive audit-mode (engages with the actual
   structural question, lands a verdict of "not stupid-industrious
   under the strict definition"), but no named cell, no verdict word,
   no operator-sharpening shape. Conservative grader fix would need a
   recognizer for "verdict-by-elimination" / "X isn't Y, because Z"
   shapes. Not in scope for this fix.

2. **v0.2.7 explanation rc-05 RUN 2 regression vs the originally-logged
   pass.** Comparing my regrade against the originally-logged result for
   v0.2.7's eval, this run now scores fail because of the
   already-existing (not edited by me) `cell-name-as-verdict` audit_apply
   pattern on line ~101 of the eval script, which matches "Opposite **is
   clever-lazy**" in the response. This is a pre-existing grader-version
   drift between when v0.2.7 was originally graded (2026-05-25 19:23,
   no cell-name-as-verdict pattern) and when v0.2.7.2 was graded
   (2026-05-25 21:43, pattern present). My fix doesn't cause this — the
   pre-existing pattern does. Worth filing as a separate future
   grader-tightening (e.g., exclude "Opposite is X" from the
   cell-name-as-verdict shape on the explanation-mode side) but out of
   scope for this fix.

3. **Verdict-shape coverage is closed-list.** Pattern 1's added marker
   enumerates verdict words ("premature, wrong-order, misordered,
   wrong-move, right-move, skip-this, out-of-order, backwards"). New
   verdict words ("stale", "off-axis", "load-bearing-on-the-wrong-thing")
   would need adding. Conservative call: closed-list now, expand as the
   model produces new verdict tokens in real data.

4. **Operator-sharpening recognition still has false-negative tail.**
   Other valid sharpening shapes — "Need more context: what's the user
   story?" / "First question: where's the friction?" — aren't in the new
   patterns. Conservative for now; expand if seen in v0.3.x data.

## Files modified

- `scripts/v027_register_classifier_eval.py` (one file, two patch
  blocks)

## Files added

- `scripts/regrade_register_classifier.py` (regrade harness — reusable
  for future grader iterations)
- `data/regrade-2026-05-26/v029-1-regrade.json` (full regrade JSON for
  v0.2.9.1)
- `data/regrade-2026-05-26/v027-1-regrade.json` (full regrade JSON for
  v0.2.7.1)
