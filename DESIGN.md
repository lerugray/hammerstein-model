# Hammerstein Persistent v1 — Design

Output of the dedicated Opus session 2026-05-08. Captures the Q1-Q4
walk verdict and the v1 implementation plan that follows from it.

## Verdict shift

- **2026-05-07 audit** evaluated "Hammerstein Agent" as an unconstrained
  build → verdict **bank**.
- **2026-05-08 walk** refined the scope through Q1 → Q2 → Q3 → Q4
  with the hammerstein CLI advising at each step.
- **Q4 verdict:** **proceed with modifications**. The constraints from
  Q1-Q3 are load-bearing, not cosmetic — they neutralize the
  misdirected-effort failure modes of the original unconstrained
  proposal.

The walk cost $0.042 across four audits via OpenRouter Qwen3.6-plus.

## Locked-in scope

### Q1 — What "persistent" means

A **stateful pull-based wrapper** around the existing one-shot CLI.
Continuity of context, NOT background execution.

In:
1. Cross-session memory with a **structural relevance gate** (Q4 mod;
   replaces the original recency-decay sketch).
2. Ambient GS project context auto-injected as a preamble.

Out (different tool shape):
- Volunteered observations between asks.
- Clock / scheduling awareness.

Hammerstein's load-bearing critique: "persistent" needs a structural
forgetting rule or it degrades into a memory dump that hurts output.
The relevance gate (below) is that rule.

### Q2 — Invocation moment

Primary: **audit-with-deeper-recall** — "audit this plan with memory
of prior plans." Validated by the existing call log: 32/57 logged
calls are `audit-this-plan`.

Secondary: cross-project strategic synthesis (same preamble shape).

Deferred:
- Long-term lookup (`grep` / `rg` over JSONL covers it today).
- Meta-pattern analysis across the audit log.

Possible v1 extension: **failure-pattern preflight** — a dedicated
step that scans the corpus for structurally similar prior plans and
surfaces the logged failure mode + structural fix BEFORE the audit
runs. Held until Phase 3 validation passes.

Validation gate (Q4 mod — structural Booleans first, utility second):
- `preamble_tokens ≤ MAX_PREAMBLE_TOKENS` for 100% of runs
- JSONL append valid and non-corrupting after every call
- Subprocess exits within hard timeout
- THEN utility check: ≥3/5 injections are *structurally* relevant
  (same failure pattern, not just topically similar) on manual review

The original "≥2/5 changes audit conclusion" gate was flagged as a
vanity metric and removed.

### Q3 — Cost shape

Architecture: **stateless Python wrapper subprocessing the existing
CLI**.

Storage: flat JSONL log + **corpus-id intersection** as the
relevance signal (no new tag schema, no embeddings).

Cost: $100/mo cap held for headroom. Realistic spend $6-30/mo at
5-20 audits/day at $0.01-0.05/call.

Falsification: weekly rolling `total_tokens` > 1.5× baseline → tag
filter is leaking scope; structural fix is the token gate, not a
lower budget cap.

Refused for v1:
- Vector store / embeddings
- Daemons, schedulers, cron
- Hosted UI
- Reimplementation of the OpenRouter client (single routing truth
  stays in the existing CLI)

### Q4 — Modifications (folded into Q1-Q3 above)

1. Replace recency-decay with a **structural relevance gate**: only
   inject prior audits that share ≥2 corpus IDs with the current
   query. Counter-observation: tag-match may be too rigid; loosen to
   ≥1 if recall drops below ~60%.
2. Validation gate is structural-first, utility-second (above).
3. Schema contract + quarantine dir + subprocess hard timeout to
   handle CLI output drift and hangs.

## Substrate audit

What already exists and what the wrapper consumes:

| Substrate | Path | Role for v1 |
|---|---|---|
| `hammerstein` CLI | `~/.local/bin/hammerstein` | Inference + corpus retrieval. Wrapper subprocesses this. |
| Existing call log | `~/.hammerstein/logs/hammerstein-calls.jsonl` | 57 structured entries with `retrieved_corpus_ids`. The retrieval target. |
| Corpus | `~/Desktop/Dev Work/hammerstein/corpus/entries/` | 35 entries; YAML frontmatter has `quadrant`, `principle`, `quality`. |
| GS project state | `~/Desktop/Dev Work/generalstaff-private/state/hammerstein-model/` | `MISSION.md` + `tasks.json`. Source for ambient context preamble. |
| Project audit tee | `~/Desktop/Dev Work/generalstaff-private/hammerstein-audit-log.jsonl` | Project-relevant audit tee (2 entries today). |
| `--show-prompt` flag | CLI option | ~200ms peek at assembled prompt without inference. Free way to discover which corpus IDs would be retrieved for a new query. |
| `--context-file` flag | CLI option | Inject preamble (project-local paths only). |

**Critical discovery:** `retrieved_corpus_ids` in the existing log IS
the structural-tag equivalent. Two audits sharing ≥2 corpus IDs are
structurally similar (they hit the same reasoning principles). This
maps Q4's "≥2 shared failure-mode tags" onto a free, deterministic,
already-existing signal. **No new tagging system required.**

Caveat: 35 corpus entries with ~6 distinct `principle` values. Tag-
match precision is bounded by corpus granularity. Track precision in
Phase 3; if it drops below ~60%, corpus growth or finer tags become
load-bearing — but don't solve preemptively.

## V1 architecture

Single Python script `hp.py` at the project root. ~150 LOC estimate.
Stdlib + `tiktoken` for token counting. No package layout.

Pipeline (per `hp <query>` invocation):

1. **Pre-fetch corpus IDs.** Call `hammerstein --show-prompt
   --template <T> <query>`, grep `## Reference: corpus #N`. Returns
   the IDs that would be retrieved for this query. Free, ~200ms,
   deterministic (verified).

2. **Read prior log.** Stream `~/.hammerstein/logs/hammerstein-calls.jsonl`.

3. **Filter for structural similarity.** Keep entries where
   `|retrieved_corpus_ids ∩ new_query_ids| ≥ 2`. Fallback to ≥1 if
   no matches at ≥2.

4. **Sort by recency. Token-budget the preamble.** Walk newest-first;
   accumulate entries until tiktoken cl100k_base count of the
   assembled preamble would exceed `MAX_PREAMBLE_TOKENS` (default
   3500 — leaves margin under a 4000 ceiling for tokenizer drift vs.
   actual Qwen).

5. **Build preamble file.** Two sections:
   - `## Prior structurally-similar audits` — formatted entries
     (timestamp, query, response excerpt).
   - `## Active project context` — `MISSION.md` + `tasks.json` from
     the auto-detected GS state dir (cwd-name match; `--project`
     flag override).

   Write to project-local `.hp-preamble.md` (gitignored).

6. **Subprocess hammerstein.** `hammerstein --context-file
   .hp-preamble.md --template <T> <query>` with hard timeout
   (default 180s).

7. **Validate output.** Schema: header line present, response
   non-empty, parseable cost/latency. On failure → write raw output
   to `quarantine/<timestamp>.txt`, log error, exit 1.

8. **Append to wrapper log.** `~/.hammerstein/logs/hp-calls.jsonl`
   (separate from main log). Schema fields:
   - `timestamp`
   - `query`
   - `template`
   - `new_query_corpus_ids`
   - `matched_prior_corpus_ids` (intersection set)
   - `injected_prior_count`
   - `preamble_tokens`
   - `response`
   - `latency_ms`
   - `cost_usd`

9. **Stdout pass-through.** Print hammerstein's response unchanged so
   `hp` is a drop-in for `hammerstein` at the terminal.

Refused even at this layer: any retry logic, any conditional re-prompting,
any "smart" preamble re-ordering. The wrapper is mechanical.

## V1 phased plan

**Phase 0 — substrate verification.** ✓ Done 2026-05-08.
- `--show-prompt` deterministic on repeated queries
- `--context-file` accepts project-local paths
- Existing log JSONL parseable, has `retrieved_corpus_ids`
- Corpus retrieval varies by query (verified with two distinct queries)

**Phase 1 — MVP wrapper.** ✓ Done 2026-05-08. `hp.py` (126 LOC) +
`hp_lib.py` (198 LOC), each under the 200 cap. Three toy queries
green; structural Booleans hold.

Bugs caught + fixed during impl (worth noting because they're real
substrate-fragility data):
1. Log stores `retrieved_corpus_ids` as zero-padded strings ("01"),
   `--show-prompt` yields ints — fixed via `entry_ids()` coercion.
2. Hammerstein writes the metadata header to **stderr**, not stdout
   (response body is on stdout) — fixed validator to inspect both.
3. Token budget didn't reserve room for project state — fixed by
   deducting state size from the audit-retrieval budget upfront.

**Phase 1 spec preserved below for reference:**

**Phase 1 — MVP wrapper (spec).** ~3 hours, **≤200 LOC** (split into two
files if exceeds; the 200 cap is a constraint, not a suggestion).
- Implement `hp.py` per architecture above.
- Stdlib + `tiktoken`. Single file unless cap forces split.
- Hard gates: token cap, subprocess timeout, schema validation, quarantine.
- **CLI contract pre-flight** (added 2026-05-08 from impl audit):
  on startup, validate `--show-prompt` produces the expected
  `## Reference: corpus #N` shape. Exit 1 on drift. Treats the
  CLI as a versioned external API.
- **Metric instrumentation** (added 2026-05-08 from impl audit):
  every `hp` invocation writes a row to
  `~/.hammerstein/logs/hp-metrics.jsonl` with: timestamp, tokens
  (preamble + total), match_count, latency, exit_code,
  conclusion_changed (operator stamps post-hoc). The metric log is
  the source of truth for the Phase 3 gate.
- Acceptance: clean run on 3 toy queries; preamble file inspected manually.

**Phase 1.5 — precision test on historical queries.** ✓ Run 2026-05-08.

**Verdict: gate failed, filter replaced.** Three iterations:

| Filter | Precision | Notes |
|---|---|---|
| Corpus-id intersection (Q4-modified) | 15.2% (14/92) | Too sparse — 35-entry corpus + 6 principles → every audit shares verification_first IDs with every other audit. Degenerate signal. |
| Recency + keyword (basic) | ~27% | Better than intersection but still floods the preamble with shared common-vocab matches. |
| Rare-token + top-K=3 + recency-decay | 52.9% (9/17) | Document-frequency weighting (drop tokens that appear in ≥10% of entries) + per-query cap of 3 matches + 30-day linear decay. |

The 60% gate was not met. Three reads on this:

1. **Real precision improvement, but not categorical.** 15% → 53% is
   a 3.5× improvement in noise rejection. The filter is now usefully
   sparse (most queries get 0-1 matches; only large-vocabulary
   queries get 3).
2. **Long queries against long queries are the failure mode.** Q1
   (TWAR PTO-LENS, 184 tokens) and Q9 (Day plan, 100+ tokens) both
   match other long queries on shared common-not-quite-stop
   vocabulary. Project-name signals get drowned out. Cosine
   normalization or named-entity weighting would help but adds
   complexity.
3. **Phase 3 dogfood is the real gate.** The synthetic 60% threshold
   is one heuristic for "the filter earns its weight." The actual
   trade-off is: do injected matches change audits enough to justify
   their token cost? `hp-metrics.jsonl` + `hp_status.py` measures
   that empirically: cost_ratio > 1.5× → ABORT;
   conclusion_changed < 2/5 → ABORT.

Decision: **ship the rare-token filter as Phase 1.5's output.**
Continue to Phase 3 dogfood. If Phase 3 finds the wrapper isn't
earning its weight, the abandonment gate fires automatically and we
revisit the filter or remove memory retrieval entirely.

Scaffold preserved as `tools/precision_test.py` for re-runs against
future log + corpus state.

**Phase 1.5 spec preserved below:** ~30 min.
*Inserted from the implementation audit's counter-observation: the
corpus-id intersection heuristic is unproven at low corpus
granularity. Test before committing.*
- Pick 10 historical audit queries from the existing log.
- For each: replay through hp's filter; record what gets injected.
- Operator manually scores each injection: structurally relevant or
  noise.
- Gate: precision ≥ 60% (≥6/10 of injections structurally relevant).
  If <60%, fall back to a recency + keyword filter and re-test
  before Phase 2.
- This test is the structural defense against the "intersection
  signal is clever-sounding but doesn't hold" failure mode.

**Phase 2 — validation harness.** ✓ Done 2026-05-08 as
`tests/test_hp.py` (14 unit tests, 1 live test gated behind a
pytest marker). Runs in 0.1s with `pytest`. The custom-harness
proposal was caught by hammerstein's audit ("don't reinvent test
runners — use pytest with built-in assertions"); this is the
revised shape.

**Phase 2 spec preserved below:** ~1 hour, ~50 LOC.
- `tests/test_hp.py`: drive 5 real audit queries.
- Structural Boolean gates (all must pass):
  - `preamble_tokens ≤ MAX_PREAMBLE_TOKENS` for all 5
  - JSONL valid + non-corrupting after each
  - Subprocess exits within 180s
  - Schema validation catches malformed output (test with stub)
  - CLI contract pre-flight passes on a known-good CLI version.
- Utility check (manual, post-hoc): ≥3/5 injections structurally
  relevant on inspection.

**Phase 3 — dogfood loop with auto-enforced gate.** Gate script
`hp_status.py` ✓ shipped 2026-05-08. Reads `hp-metrics.jsonl` and
prints CONTINUE / EXTEND / ABORT. Currently outputs ABORT because
no calls have `conclusion_changed` stamped yet — that's correct
behavior; the gate refuses to proceed without operator sign-off.

**Phase 3 spec preserved below:** 2 weeks.
*Modified 2026-05-08 to remove manual self-assessment.*
- Use `hp` instead of plain `hammerstein` for plan-audits.
- `hp-status` script reads `hp-metrics.jsonl` and prints one of
  `ABORT`, `CONTINUE`, `EXTEND`. The verdict is mechanical:
  - **ABORT** if any of:
    - rolling 7-day total_tokens > 1.5× baseline (token bloat)
    - <2/5 last-five audits had `conclusion_changed=true` (memory
      not earning weight)
    - operator-logged maintenance hours > 2/wk in the metrics log
      (clever-lazy threshold crossed)
  - **CONTINUE** if all three thresholds pass
  - **EXTEND** if metrics are within 10% of any threshold
- The gate fires automatically. Operator does not get to "feel
  like" the wrapper is working — `hp-status` votes.

**Phase 4 — failure-pattern preflight.** Deferred. Only built if
Phase 3 passes.

## Implementation audit modifications (2026-05-08)

A second audit pass against the v1 implementation plan returned
**ship with modifications**. Three modifications were folded into
the phased plan above:

1. **Corpus-id intersection precision is unproven.** Phase 1.5
   inserted: test the heuristic against 10 historical queries
   before committing. Fallback to recency + keyword filter if
   precision < 60%.
2. **Phase 3 abandonment gate was unenforceable** as originally
   written (manual weekly self-assessment). Replaced with
   `hp-metrics.jsonl` + `hp-status` script that mechanically prints
   ABORT / CONTINUE / EXTEND. Operator does not get a vote.
3. **CLI contract pre-flight** added to Phase 1 startup. Validates
   `--show-prompt` output structure; exits 1 on format drift.
   Treats the existing CLI as a versioned external API.

LOC cap raised to 200 (was 150). Realistic estimate accounting for
error handling, contract checks, and metric instrumentation.

The implementation audit is preserved in
`~/.hammerstein/logs/hammerstein-calls.jsonl` (2026-05-08, template
audit-this-plan, "Audit the V1 IMPLEMENTATION PLAN…").

## Open questions / known gaps

1. **Corpus-id intersection with sparse corpus.** 35 entries, ~6
   `principle` values today. Watch precision in Phase 3.

2. **Tokenizer drift.** tiktoken cl100k_base is a proxy for Qwen
   tokenization (~10-15% off for English). Hard cap at 3500
   tiktoken-tokens leaves margin under a 4000 ceiling.

3. **Wrapper log vs. main log split.** v1 writes to a separate
   `hp-calls.jsonl`. If retrieval over only the wrapper log starves
   recall (the 57 baseline entries are in the main log), the
   retrieval step concatenates both during the filter pass. Cheap
   and defers the merge decision.

4. **GS state freshness.** `MISSION.md` and `tasks.json` are
   human-edited and may be stale. The wrapper trusts whatever's
   there; stale-state-bad-audits is a state-hygiene problem, not a
   wrapper problem.

5. **Surface beyond CLI.** v1 refuses proactive/scheduled. The
   dogfood loop reveals whether manual `hp <query>` is enough.
   Don't pre-build automation.

## Refused for v1

- Vector store / embeddings (deferred until corpus > 100 entries)
- Background daemon / scheduled jobs / cron
- Hosted web UI
- Reimplementation of OpenRouter client
- Multi-user / multi-operator support
- Long-term lookup beyond `grep` on JSONL
- Meta-pattern analysis across the audit log

## References

- 2026-05-07 original audit (verdict: bank Option B):
  `generalstaff-private/hammerstein-audit-log.jsonl` line 1
- Q1-Q4 walk: this Opus session 2026-05-08, summary above
- Pushback memory:
  `generalstaff-private/.claude/projects/.../memory/project_hammerstein_ai_diy_pushback.md`
- Substrate roots: `~/Desktop/Dev Work/hammerstein/`, `~/.hammerstein/`,
  `~/Desktop/Dev Work/generalstaff-private/state/hammerstein-model/`
