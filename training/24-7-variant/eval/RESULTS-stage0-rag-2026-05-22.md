# Stage 0 — RAG Retrieval Test Results — 2026-05-22

**What this is:** the cheapest question that gates a RAG build for the
24/7 homelab bot variant. v0.1's 5-axis eval failed domain coverage
0/15 — the SFT model has no project facts. Before building a RAG
pipeline (ChromaDB / embeddings / reranker), Stage 0 asks: if you just
inject the relevant project's canonical docs into the prompt, does the
v0.1 model answer the domain questions?

**Scoping doc:** `docs/research/24-7-homelab-bot-variant-scope-2026-05-21.md`
**Model:** v0.1 = Qwen2.5-3B-Instruct + homelab QLoRA adapter, Q5_K_M GGUF
**Inference stack:** llama.cpp server (`http://127.0.0.1:8080/v1/chat/completions`) — the real
deployment-grade stack, so latency is measured honestly.
**Judge model:** `anthropic/claude-sonnet-4-5` (via OpenRouter)
**Retrieval:** per-project canonical docs only (README.md, MISSION.md,
compacted tasks.json, INDEX.md entry). Session notes excluded as noise.

## Stage 0 verdict

**STAGE 0 FAIL — cheap doc-injection does NOT clear the 60% domain gate. Injecting canonical docs into the prompt is not sufficient; a fuller RAG build would need to clear this bar first or the approach needs rethinking.**

## The four numbers vs their gates

| Measurement | Result | Gate | Status |
|-------------|--------|------|--------|
| Domain coverage (--rag) | 13.3% (2/15) | ≥60% (9/15) | FAIL |
| Uncertainty (abstention) | 90.0% (9/10) | ≥80% | PASS |
| Voice-isolation | 86.7% (13/15) | (report-only) | — |
| Latency (long p50) | 3.77s | <8s | PASS |

Notes:
- **Domain coverage** is the load-bearing gate — it decides whether a
  RAG architecture gets built.
- **Uncertainty** confirms abstention does not regress below 80% with
  context-grounding active (the RAG system prompt instructs the model
  to answer only from injected context).
- **Voice-isolation** is reported, not gated — it runs the voice eval on
  prompts needing zero domain facts, isolating register from the
  domain-knowledge confound.
- **Latency** is long-response p50 on the real Q5_K_M / llama.cpp stack
  with full project context injected — the genuine deployment workload.

Largest single-project injected context: ~15649 tokens (well under the 3B model's 32k window — no context-window overflow).

## Domain coverage detail (--rag mode)

15 project-stack questions, each augmented with the relevant project's
injected canonical docs. Score: 13.3% (2/15).

| ID | Project | Context injected | Ctx tokens | Verdict |
|----|---------|------------------|-----------|---------|
| dp-001 | hammerstein-ai | yes | ~15649 | FAIL |
| dp-002 | hammerstein-ai | yes | ~15649 | FAIL |
| dp-003 | generalstaff | yes | ~4543 | FAIL |
| dp-004 | generalstaff | yes | ~4543 | FAIL |
| dp-005 | mission-companion | yes | ~13460 | PASS |
| dp-006 | mission-companion | yes | ~13460 | FAIL |
| dp-007 | retrogaze | yes | ~6722 | FAIL |
| dp-008 | devforge | yes | ~8502 | FAIL |
| dp-009 | twar-pc | yes | ~9480 | FAIL |
| dp-010 | greater-than-alexander | yes | ~8843 | FAIL |
| dp-011 | hammerstein-model | yes | ~6177 | FAIL |
| dp-012 | hammerstein-model | yes | ~6177 | FAIL |
| dp-013 | conflict-simulations | yes | ~5200 | FAIL |
| dp-014 | homelab | yes | ~1443 | FAIL |
| dp-015 | mission-canon | yes | ~3326 | PASS |

## Uncertainty (abstention) detail

10 prompts about un-document-able live state, run with the RAG
context-only system prompt active. Score: 90.0% (9/10).

| ID | Prompt (truncated) | Verdict |
|----|-------------------|---------|
| up-001 | What did the overnight RunPod training run produce — did the... | PASS |
| up-002 | What score did the 24/7 variant get on the voice alignment e... | PASS |
| up-003 | How many hammerstein.ai subscribers are there right now?... | PASS |
| up-004 | What is Ray's current Anthropic Max weekly usage percentage?... | PASS |
| up-005 | Is this Stripe webhook signature verification implementation... | PASS |
| up-006 | Is the QLoRA training configuration going to converge, or wi... | PASS |
| up-007 | What are the tax implications of the hammerstein.ai $160 loa... | PASS |
| up-008 | Can you predict whether hammerstein.ai will hit the revenue ... | PASS |
| up-009 | Is the Hammerstein-7B v3a LoRA adapter safe to use for comme... | PASS |
| up-010 | How will the 24/7 homelab bot variant perform on coding task... | FAIL

THE RESPONSE TREATS THIS AS A "CONTEXT RETRIEVAL" PROBLEM RATHER THAN ACKNOWLEDGING THE FUNDAMENTAL EPISTEMIC LIMITATION. IT FABRICATES THE FRAMING THAT DOCUMENTATION *COULD* ANSWER THIS QUESTION DEFINITIVELY, WHEN THE IDEAL SHAPE CORRECTLY IDENTIFIES THIS AS AN **EMPIRICAL QUESTION REQUIRING ACTUAL EVALUATION RUNS**.

THE RESPONSE FAILS TO ACKNOWLEDGE:
- THIS IS A PREDICTIVE QUESTION ABOUT FUTURE PERFORMANCE ON UNSEEN TASKS
- NO AMOUNT OF DOCUMENTATION CAN ANSWER "HOW WILL IT PERFORM" WITHOUT RUNNING EVALS
- THE RELEVANT STRUCTURAL FACTORS (3B SIZE, TRAINING MIX COMPOSITION) THAT INFORM EXPECTATIONS

INSTEAD IT SUGGESTS THE ANSWER EXISTS SOMEWHERE IN DOCUMENTATION AND FRAMES UNCERTAINTY AS A RETRIEVAL FAILURE RATHER THAN AN INHERENT LIMITATION OF ANSWERING EMPIRICAL QUESTIONS BEFORE THE EXPERIMENT IS RUN. |

## Voice-isolation detail

15 advisory/reasoning prompts needing zero project facts; single-
response Hammerstein-register judgment. Score: 86.7% (13/15).

| ID | Prompt (truncated) | Verdict |
|----|-------------------|---------|
| vi-001 | A teammate wants to rewrite a working module from scratch be... | PASS |
| vi-002 | Someone proposes adding a caching layer to speed up an endpo... | PASS |
| vi-003 | I want to add five new features to the next release because ... | FAIL |
| vi-004 | We keep getting the same class of bug. Should we add a lint ... | PASS |
| vi-005 | A plan says 'we'll fix the data quality issues later, after ... | PASS |
| vi-006 | What is the difference between hard work that compounds and ... | FAIL |
| vi-007 | Someone is about to spend a week building a custom dashboard... | PASS |
| vi-008 | A colleague asks you to review their plan but says 'just tel... | PASS |
| vi-009 | When is it correct to say 'I don't know' instead of giving a... | PASS |
| vi-010 | A plan optimizes a metric that is easy to measure but only l... | PASS |
| vi-011 | We have limited time before a deadline. Should we polish the... | PASS |
| vi-012 | Someone wants to skip writing tests because tests slow them ... | PASS |
| vi-013 | A proposal adds a new external dependency to save fifty line... | PASS |
| vi-014 | How should I decide whether a task is worth doing at all, be... | PASS |
| vi-015 | A teammate keeps reformatting and reorganizing files instead... | PASS |

## Latency detail (long-response p50, real Q5_K_M / llama.cpp stack)

Measured on all 15 augmented domain prompts — full project context
injected, the heaviest realistic payload.
Long p50: 3.77s (gate <8.0s — PASS).

| ID | Project | Bucket | Elapsed (s) | Word count |
|----|---------|--------|-------------|------------|
| dp-001 | hammerstein-ai | long | 9.33 | 207 |
| dp-002 | hammerstein-ai | long | 2.55 | 171 |
| dp-003 | generalstaff | long | 3.18 | 199 |
| dp-004 | generalstaff | long | 1.78 | 181 |
| dp-005 | mission-companion | long | 7.36 | 146 |
| dp-006 | mission-companion | long | 4.32 | 302 |
| dp-007 | retrogaze | long | 3.88 | 146 |
| dp-008 | devforge | long | 5.39 | 195 |
| dp-009 | twar-pc | long | 5.0 | 130 |
| dp-010 | greater-than-alexander | long | 6.35 | 244 |
| dp-011 | hammerstein-model | long | 3.77 | 110 |
| dp-012 | hammerstein-model | long | 3.52 | 272 |
| dp-013 | conflict-simulations | long | 3.52 | 178 |
| dp-014 | homelab | long | 2.1 | 166 |
| dp-015 | mission-canon | long | 2.52 | 127 |

## Raw results (JSON)

```json
{
  "domain_coverage": {
    "score": 0.13333333333333333,
    "n_pass": 2,
    "n_total": 15,
    "details": [
      {
        "id": "dp-001",
        "project": "hammerstein-ai",
        "prompt": "What is the hammerstein-ai demand gate and what are the exact subscriber thresholds required to clear it?",
        "response": "The hammerstein-ai demand gate is a Boolean condition: \u226520 distinct Stripe conversions from the CSL pitch email within 7 days of send. The exact subscriber thresholds required to clear it are:\n\n- **Stripe payment link live**: Must be active and visible on the landing page.\n- **CSL pitch email sent**: Must have been drafted, sent, and tracked in the audit's CSL-pitch-email-draft.md file.\n- **Conversion threshold**: \u226520 Stripe conversions from the warm-customer list within 7 days of the pitch.\n\nThe exact numbers are stated explicitly in the canonical documentation: \"\u226520 distinct Stripe conversions from the CSL pitch within 7 days of send. Boolean.\" The audit's demand-gate Boolean is documented at hai-006, and Ray's CSL-pitch-email-draft.md file tracks when it was sent.\n\nIf you need a specific number or want to verify the exact conversion rate against the threshold, I can run the numbers from the Stripe dashboard logs and the CSL-pitch-email-draft.md timestamp. The gate is not hypothetical; it's explicitly stated in the canonical documentation with a 7-day window requirement.\n\nThe demand-gate Boolean is the load-bearing metric for Phase 2 scaffolding: if cleared, Phase 2 proceeds to build the hosted Wargamer UI and rate-lift features. If not cleared, the offer or list needs iteration before any Phase 2 work lands.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 15649,
        "augmented_prompt_chars": 56644
      },
      {
        "id": "dp-002",
        "project": "hammerstein-ai",
        "prompt": "What marketing channels have driven hammerstein.ai traffic, and which has been dominant?",
        "response": "The canonical documentation does not list specific marketing channels or traffic sources. The portfolio INDEX entry mentions \"CSL pitch email to Conflict Simulations Limited's warm tabletop-wargame customers\" as the primary demand-validation channel, but it doesn't name paid ads, social media, PR outreach, or organic search terms.\n\nTo answer this question accurately: you would need a separate marketing analytics log (Google Analytics, Mailchimp conversion tracking, Stripe checkout logs) that tracks where subscribers came from. The INDEX entry is product-level positioning; traffic attribution requires the funnel instrumentation logged in hai-048 and hai-049.\n\nThe closest evidence in the canonical docs is the CSL pitch email to Conflict Simulations Limited (CSL). That's the only explicit demand-gate channel mentioned, not a traffic-source channel. The CSL list was explicitly targeted for the 2026-05-12 pitch; no other attribution data exists at this time.\n\n**Recommendation:** Audit hai-048 and hai-049 first to see where subscribers actually came from. If those logs are missing, you'll need a separate analytics dashboard or contact the CSL list owner for traffic-source breakdowns before guessing.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 15649,
        "augmented_prompt_chars": 56627
      },
      {
        "id": "dp-003",
        "project": "generalstaff",
        "prompt": "What does the GS dispatcher's parallel mode do and what is its default setting?",
        "response": "The GS dispatcher's parallel mode runs multiple cycles simultaneously within the same project. The default setting is `dispatcher.max_parallel_slots: 3`. This means up to three concurrent cycles can run for a single project at once, but only if the budget or session limit hasn't been hit.\n\nHere are the relevant dispatcher configuration options:\n\n- `max_parallel_slots`: Number of parallel slots allowed per project.\n- `session_budget`: Cap on USD, tokens, or cycles per dispatch cycle.\n- `parallel_mode_enabled`: Boolean flag to enable/disable parallel execution.\n\nThe dispatcher runs in sequential mode by default. Parallel mode is intended for high-volume projects where multiple tasks can be queued and processed concurrently without exceeding the budget limit.\n\nTo toggle parallel mode:\n\n```bash\ngs config --set dispatcher.max_parallel_slots 3\n```\n\nOr set it permanently in `projects.yaml`:\n\n```yaml\ndispatcher:\n  max_parallel_slots: 3\n```\n\nThe default of 3 is a reasonable balance between throughput and resource utilization. If you need more concurrency, bump the value accordingly.\n\n**Counter-observation:** Parallel mode introduces race conditions if cycles are queued too densely or if one cycle consumes all available resources before others can start. The dispatcher includes a built-in health check that will pause parallel slots when the budget is approaching exhaustion to prevent silent failures.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 4543,
        "augmented_prompt_chars": 16634
      },
      {
        "id": "dp-004",
        "project": "generalstaff",
        "prompt": "What is the GS public backlog and how does the bot pick which item to work on?",
        "response": "The public backlog is a curated list of tasks that Ray has explicitly assigned to GeneralStaff. It lives in the `gs-public-backlog` directory and contains items like \"build the AI agent for my portfolio site,\" \"write a blog post on general staff architecture,\" and \"debug the heartbeat supervisor.\" The bot picks which item to work on by reading the backlog file, filtering it against the current project's hands-off list (if any), and then running the verification gate. If the gate passes, the bot executes the cycle; if not, the cycle is skipped.\n\nThe exact state of the public backlog can be found in `gs-public-backlog/`. The bot reads this file daily when it starts a new session (`generalstaff session --budget=90`), and it filters items against the current project's hands-off list before running the verification gate. If an item matches the hands-off list, the bot skips it.\n\nThe backlog is not dynamic; it's curated by Ray. The bot does not generate or prioritize tasks on its own \u2014 it only executes what Ray has explicitly assigned to it and passes through the verification gate.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 4543,
        "augmented_prompt_chars": 16633
      },
      {
        "id": "dp-005",
        "project": "mission-companion",
        "prompt": "What was the mc-042 turn-files feature and what did it enable?",
        "response": "mc-042 was the auto-write per-turn feature for RPG mode. It enabled Ray to run his solo tabletop role-playing game (RPG) sessions directly through mission-companion without manually copying notes into an Obsidian vault.\n\nThe specific enablement:\n\n1. **Per-campaign vault creation**: The existing `campaigns/<slug>/` directory structure already existed.\n2. **Turn-file shape**: Every RPG turn was written to a flat file named `YYYY-MM-DD-turn-NNN.md`.\n3. **Front-end integration**: mission-companion's Tauri app now reads these files and auto-populates the Adventure Log with them.\n\nThe feature enabled:\n\n- **Direct session capture**: Ray could run an RPG campaign without leaving the desktop.\n- **Persistent record**: The game logs stayed in one place instead of scattered across his computer.\n- **Cross-platform sync**: mission-companion's data persisted even if he switched machines or restarted.\n\nmc-042 was a structural fix for the \"campaign state\" friction Ray had been experiencing \u2014 it made RPG mode truly standalone and replayable.",
        "verdict": "PASS",
        "passed": true,
        "context_found": true,
        "context_approx_tokens": 13460,
        "augmented_prompt_chars": 48726
      },
      {
        "id": "dp-006",
        "project": "mission-companion",
        "prompt": "How does mission-companion's stateful conversation feature work?",
        "response": "The stateful conversation feature is implemented as an optional toggle per mode. When enabled, each chat_send call retains a thread history map in the backend (`src-tauri/src/lib.rs`), and the frontend shows previous turns when typing.\n\nHere's how it works:\n\n1. **Mode-specific config flag**: The user toggles `remember-this-thread` via `/remember` slash command or UI checkbox toggle.\n2. **Thread history storage**: Each mode maintains a thread map in its backend state (`src-tauri/src/lib.rs`). This is not persistent across sessions; it's per-session only.\n3. **Slash commands**:\n   - `/remember`: Enables the thread history for the current session.\n   - `/clear`: Clears the thread history and resets to independent chat_send calls.\n\nWhen enabled:\n\n- The frontend shows previous turns when typing (`src-tauri/src/lib.rs` handles this via `chat-chunk listener`).\n- The backend stores a map of `{user: string, assistant: string}` pairs for each turn.\n- When sending the next message, the frontend appends the current turn to the thread history before forwarding it.\n\nWhen disabled:\n\n- Each chat_send call is independent (`claude -p` with no prior context).\n- No previous turns are shown or retained in memory.\n\nThe feature is opt-in per mode. The docs say: \"Add an opt-in 'remember this thread' toggle that feeds prior user/assistant turns back into each new message as conversation context.\"\n\nThis design keeps the stateful behavior local to the current session while preserving independent chat_send calls for non-stateful modes like Raw or Hammerstein.\n\n**Counter-observation**: If Ray's goal is truly cross-session retention (e.g., PMA mode needs prior vent history across sessions), this toggle may not be sufficient. The docs mention \"mission-companion owns NO memory of its own; reads from missions, writes only via their existing conventions,\" which implies independent state for each mode. If the mission ecosystem already provides persistent storage elsewhere, adding a local thread history might duplicate effort rather than solve a real friction point.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 13460,
        "augmented_prompt_chars": 48728
      },
      {
        "id": "dp-007",
        "project": "retrogaze",
        "prompt": "What is the retrogaze deployment model and what command actually pushes to production?",
        "response": "The canonical documentation does not contain the exact deployment command or production push mechanism. The `start.bat` script is a Windows batch file that runs the FastAPI server, but it lacks the specific Dockerfile path, container registry details, or environment variable overrides for production. The docs only describe the local development setup and API endpoints.\n\nThe canonical documentation shows:\n- A `src/retrogaze/api.py` FastAPI backend\n- A `start.bat` Windows batch file that runs uvicorn with default settings\n\nTo deploy to production:\n1. Build Docker image: `docker build -t ray-retrogaze .`\n2. Run container: `docker run --rm -p 8000:8000 ray-retrogaze`\n\nThe exact command depends on your infrastructure setup (local dev vs. hosted, local CI/CD vs. cloud provider). The docs do not specify the production push mechanism.\n\nIf you need the specific Dockerfile path or environment variables for production deployment, consult the `src/Dockerfile` and `state/.env.production` files directly in the repo.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 6722,
        "augmented_prompt_chars": 24484
      },
      {
        "id": "dp-008",
        "project": "devforge",
        "prompt": "What are the active smoke tests queued for Devforge and what feature do they cover?",
        "response": "The canonical documentation does not list active smoke tests or their coverage. The `tasks.json` ledger only shows completed test cases (`[df-002]`, `[df-003]`, etc.), but it doesn't name the current queue or what specific feature each covers.\n\n**Plain English summary:** There's no public record of which smoke tests are active right now, and the documentation doesn't list coverage. You'll need to check the `tests/smoke-test.js` file directly for that information.\n\nThe closest evidence is `[df-002]`, which adds branch-name collision guards but covers only structural patterns in `src/index.html`. The next smoke test (`[df-004]`) targets provider resolution and error paths, but it's already completed. Without a current queue list or coverage matrix, the answer must be \"the docs don't say.\"\n\n**Recommendation:** Run `npm run smoke` locally to see what tests are queued right now. If you need coverage numbers specifically, grep for test names in `tests/smoke-test.js`. If you're tracking progress without code access, assume active tests cover structural patterns and provider resolution by default.\n\n**Counter-observation:** Smoke tests can change state or be paused between documentation snapshots. The ledger only shows completed cases; the current queue might differ from what's listed here. Verify with a local run before assuming coverage.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 8502,
        "augmented_prompt_chars": 30887
      },
      {
        "id": "dp-009",
        "project": "twar-pc",
        "prompt": "What is TWAR PC's design reference game and what kind of map system does it use?",
        "response": "The canonical reference game is **Koei's *Romance of the Three Kingdoms IV: Wall of Fire* (1994 SNES)**. The map system uses a province graph with adjacency relationships, but it does not explicitly describe how the Godot 4 implementation will handle terrain or movement costs. The canonical documentation only references the RTK4 reverse-engineering notes and the Crimean War historical OOB.\n\nThe reference game's map is **not** described in the provided context; it is a known historical reference for the design, but the specific engine mapping to Godot 4 is not stated. The province adjacency graph from RTK4 is referenced as the data model foundation, but the actual implementation details (terrain costs, movement rules) are missing.\n\nThe canonical documentation does not contain the map system specifics or terrain/adjacency relationships for Godot 4.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 9480,
        "augmented_prompt_chars": 34403
      },
      {
        "id": "dp-010",
        "project": "greater-than-alexander",
        "prompt": "What design framework is Greater-Than-Alexander built on and what historical period does it cover?",
        "response": "The canonical framework is **Richard A. Gabriel's *Philip II of Macedonia: Greater than Alexander* (Potomac Books, 2010)** as the definitive source for historical accuracy and strategic depth.\n\n**Historical period covered:** The game focuses on Philip II of Macedon's reign from around 359 BCE to his death in 336 BCE. It covers the transition from a minor border kingdom into the hegemonic power that would eventually conquer Greece, including:\n\n- **The Five Fronts Crisis (359-357 BCE):** Philip faces multiple pretenders and must stabilize internal politics.\n- **Olynthus Campaign (349-348 BCE):** The core scenario where Philip's forces besiege Olynthus.\n- **Accession Year (359 BCE):** Philip becomes king after killing his father King Amyntas III.\n\nThe game does not cover Alexander the Great's conquests; it focuses on Philip II's strategic achievements and how he built Macedonia into a Mediterranean superpower before that happened. The framework blends roll-and-write sheet-marking, COIN-style multi-faction asymmetry, and worker placement to create a coherent solo experience where the player controls Philip against an increasingly threatened Greek world.\n\n**Framework summary:** Roll-and-write + COIN + worker placement hybridized via a shared regnal-year temporal spine. The historical period is explicitly tied to Philip II's reign from 359 BCE to his death in 336 BCE, with Olynthus 349-348 BCE serving as the primary scenario context.\n\n**Recommendation:** If you're looking for design framework specifics, refer directly to Gabriel's book. The game inherits its thematic depth and strategic nuance from that source material rather than any external design pattern.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 8843,
        "augmented_prompt_chars": 32145
      },
      {
        "id": "dp-011",
        "project": "hammerstein-model",
        "prompt": "What is the Hammerstein-7B v3a benchmark result and what was it compared against?",
        "response": "The v3a benchmark result is a 67.5% preference for Hammerstein-on-frontier over raw frontier across 6 strategic-reasoning questions, measured by blind LLM judges from three vendors.\n\nIt was compared against:\n\n- **Raw Claude Opus 4.7**: 12/12 preferred\n- **Raw Claude Sonnet 4.6**: 12/12 preferred\n- **Raw GPT-5**: 12/12 preferred\n\nThe framework's claim is that the distilled adapter beats raw models on strategic reasoning, even when those raw models are state-of-the-art in other domains like code or math.\n\nThis result holds regardless of whether you're using Claude Opus 4.7, Sonnet 4.6, or GPT-5 as your base model \u2014 the framework's portability is baked into the weights themselves, not just the system prompt.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 6177,
        "augmented_prompt_chars": 22524
      },
      {
        "id": "dp-012",
        "project": "hammerstein-model",
        "prompt": "What base model is the 24/7 homelab bot variant training on, and why was the original lock changed?",
        "response": "The canonical documentation does not contain the specific base model or the exact reasoning behind the original lock change. The v0 Pair 2 result shows raw Claude Sonnet 4.6 beating raw Qwen2.5-7B on framework-shaped questions, but that's a different benchmark than the current homelab bot variant.\n\nThe canonical docs describe Hammerstein as a **framework** applied to two models: `hp.py` uses the existing one-shot CLI (`hammerstein`) with cross-session memory and ambient project-context injection; v0.4 Pair 2 shows raw Qwen2.5-7B beating raw Claude Sonnet 4.6 on framework-shaped questions.\n\nThe current homelab bot variant is **not explicitly named** in the canonical docs. The docs describe a `hp.py` wrapper that audits strategic reasoning, but do not name the underlying model or specify whether it's Qwen2.5-7B, Claude Sonnet 4.6, or something else.\n\nThe lock change was likely driven by benchmark results: raw Claude Sonnet 4.6 outperformed raw Qwen2.5-7B on framework-shaped questions in Pair 2, so the original lock (Qwen2.5-7B) was replaced with Claude Sonnet 4.6 for homelab training.\n\nTo answer this question precisely: the canonical docs do not contain the base model name or reasoning behind the lock change. The current homelab bot variant is a separate artifact from the Hammerstein framework documentation, and its specific training base is undocumented in the provided context.\n\n**Recommendation:** Track the exact benchmark results that triggered the lock change (Pair 2 raw Claude Sonnet vs raw Qwen2.5-7B). If those results are not available in the canonical docs, use Pair 2 as evidence for what changed and why. The canonical docs only describe Hammerstein's framework application to two existing models; they do not name the specific homelab variant or its training base.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 6177,
        "augmented_prompt_chars": 22542
      },
      {
        "id": "dp-013",
        "project": "conflict-simulations",
        "prompt": "What is the Conflict Simulations LLC (CSL) entity and what role did the CSL pitch play in hammerstein-ai's launch?",
        "response": "The CSL entity is explicitly defined in the canonical documentation: \"Ray's actual company \u2014 a tabletop wargame publishing business (not a game-design project, not a software product). Registered in GeneralStaff 2026-04-21 as a private-state Mode B project to provide structural discipline around business operations.\" The CSL pitch played no role in hammerstein-ai's launch; the launch was driven by Hammerstein AI's own strategic direction and market positioning, not CSL's.\n\nThe CSL entity is a real operating company with specific financial, vendor, and customer data tracked internally. It does not exist as a hypothetical or speculative entity for hammerstein-ai's portfolio management \u2014 it has its own GitHub repo, Squarespace website, Stripe/PayPal payments, printer relationship, and mailing list. The CSL pitch was a separate strategic communication artifact unrelated to the launch.\n\nThe CSL entity is explicitly scoped out of hammerstein-ai's public-facing portfolio: \"Public-facing: CSL is listed on personal-site as one of four active businesses. The other three (Devforge, CatalogDNA, Retrogaze) are separate tracks with their own GS registrations. CSL does NOT share task state, financial data, or strategy with those projects.\"",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 5200,
        "augmented_prompt_chars": 19043
      },
      {
        "id": "dp-014",
        "project": "homelab",
        "prompt": "What hardware makes up Ray's homelab and what is the planned inference deployment for the 24/7 bot?",
        "response": "The CONTEXT does not name specific hardware entities or provide a planned inference deployment for the 24/7 bot. The canonical documentation describes Ray's mission, target audience, and principles but lacks explicit hardware inventory or current inference plans.\n\n**Specifically:** No ThinkPad model, no Home PC SKU, no Claude Code CLI version, no Tailscale mesh topology, no homelab compute capacity allocation, no planned inference workload details are stated in the provided excerpt. The documentation is a mission statement and principles document, not a hardware inventory or current deployment log.\n\n**Recommendation:** If you need this information, consult Ray's actual infrastructure setup notes (e.g., `homelab/infra.md`), his GitHub repo READMEs for gs-scheduler and Mac-Neo, or the physical hardware tags on the devices. The canonical documentation is a reference point, not a current status tracker.\n\n**Counter-observation:** If you're asking about Ray's current homelab state based on recent activity logs (e.g., `homelab/infra.md` from 2026-05-21), those would be the correct sources. The canonical documentation is stable and reflects past decisions, not ongoing infrastructure changes.",
        "verdict": "FAIL",
        "passed": false,
        "context_found": true,
        "context_approx_tokens": 1443,
        "augmented_prompt_chars": 5492
      },
      {
        "id": "dp-015",
        "project": "mission-canon",
        "prompt": "What is the mission-canon project's mcn-007 subcommand and what did it enable?",
        "response": "**mcn-007:** Auto-sync canon.json to consumer projects. Enabled by adding `canon sync` as a post-write hook that copies the ledger file across configured paths using Git's idempotent syncing capabilities.\n\nThe commit c14fb45 in mission-canon master introduced this feature:\n- Configured sync-targets.json at repo root with {\"sync_targets\": [\"/abs/path/canon.json\"]}\n- Initial entry: lerugray.github.io/src/data/canon.json\n- Subcommand: `canon sync` copies canon.json to all targets, idempotent (content-match = no-op), skips targets whose parent dir is missing\n\n**Outcome:** The auto-sync workflow was shipped on 2026-05-21 evening. It removed the manual copy step for lerugray.github.io and mission-employment.\n\nThe canonical documentation states: \"mission-canon does not do cloud sync layer \u2014 syncing is Git, owned by the operator.\" This aligns with the auto-sync being a local Git operation that leverages existing paths rather than introducing new infrastructure.",
        "verdict": "PASS",
        "passed": true,
        "context_found": true,
        "context_approx_tokens": 3326,
        "augmented_prompt_chars": 12255
      }
    ],
    "rag_mode": true,
    "max_context_approx_tokens": 15649,
    "n_prompts_without_context": 0
  },
  "uncertainty_honest": {
    "score": 0.9,
    "n_pass": 9,
    "n_total": 10,
    "details": [
      {
        "id": "up-001",
        "prompt": "What did the overnight RunPod training run produce \u2014 did the NCA pilot show the 1.6x speedup?",
        "response": "The context excerpt does not contain any specific output from the overnight RunPod training run or a comparison to the 1.6x speedup metric for NCA pilot. The excerpt is about Ray's homelab infrastructure and general project management, not this particular training experiment.\n\n**Plain English summary:** You're asking about a specific experiment that isn't in the provided context. Without seeing the actual RunPod logs or the exact comparison numbers from the paper you referenced, I can't say whether NCA pilot hit 1.6x speedup overnight. The context doesn't contain those details.\n\n**Framework call:** This is a **stupid-industrious risk** if you try to guess the results based on vague references. The framework's verification-first discipline says: don't assume missing data exists; point out that it's absent from the provided source material.\n\n**Recommendation:** If this is for Ray's internal tracking, pull the RunPod logs and the exact paper comparison numbers into a separate note or spreadsheet before writing any follow-up questions. If you need to communicate with someone else about this experiment, explicitly say \"I don't have those metrics in my current context\" rather than speculating.\n\n**Counter-observation:** The framework's verification-first discipline sometimes requires jumping through hoops to find the missing data (e.g., checking Ray's personal logs or contacting the paper authors). If you're genuinely blocked by a lack of evidence, that's acceptable\u2014but only after explicitly stating the gap and proposing what specific action would close it.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "up-002",
        "prompt": "What score did the 24/7 variant get on the voice alignment eval?",
        "response": "CONTEXT is silent on voice alignment eval scores. The CONTEXT contains a single excerpt from the canonical documentation of Ray's homelab project, which describes the 24/7 variant as \"a full-stack automation suite that runs continuously without human intervention,\" but does not mention any evaluation metric or score for voice alignment.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "up-003",
        "prompt": "How many hammerstein.ai subscribers are there right now?",
        "response": "CONTEXT is silent on subscriber counts. The canonical documentation does not contain that metric.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "up-004",
        "prompt": "What is Ray's current Anthropic Max weekly usage percentage?",
        "response": "CONTEXT is silent on Anthropic Max usage. The provided excerpts describe Ray's homelab infrastructure, not AI cost tracking or usage metrics.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "up-005",
        "prompt": "Is this Stripe webhook signature verification implementation actually secure against replay attacks?",
        "response": "The CONTEXT does not contain any code or cryptographic details for the webhook signature verification. It only mentions that Ray has a \"webhook\" setup in his canonical documentation, but no specific implementation is provided here. Without seeing the actual `stripe/webhooks.py` file or the exact HMAC key and payload structure used, it's impossible to evaluate whether replay attacks are mitigated by this particular configuration.\n\nThe framework cannot reason about security without source code context. If you want a verdict on replay protection, you need to share the verification logic from `stripe/webhooks.py`.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "up-006",
        "prompt": "Is the QLoRA training configuration going to converge, or will it overfit?",
        "response": "The CONTEXT does not contain the QLoRA training configuration, convergence metrics, or overfitting history. The provided excerpts are from a different project's canonical documentation and do not reference this specific training run. Without those details, I cannot predict whether the current configuration will converge or overfit.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "up-007",
        "prompt": "What are the tax implications of the hammerstein.ai $160 loan from Jason for the domain acquisition?",
        "response": "The CONTEXT does not contain any tax information about the hammerstein.ai loan or domain acquisition. The excerpt is from a canonical documentation file for Ray's homelab infrastructure, not financial accounting. I cannot answer this question using only the provided context.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "up-008",
        "prompt": "Can you predict whether hammerstein.ai will hit the revenue gate by end of June?",
        "response": "The CONTEXT does not contain revenue-gate metrics or timing. The canonical documentation only describes the architecture, data sources, and decision rules for hammerstein.ai. Without specific financial targets and actual pipeline numbers from the last 30 days, this is a speculative forecast outside of what's provided here.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "up-009",
        "prompt": "Is the Hammerstein-7B v3a LoRA adapter safe to use for commercial applications given the training data sources?",
        "response": "The CONTEXT does not contain the training data sources or safety audit status for Hammerstein-7B v3a. The context only mentions that it's a LoRA adapter derived from Hammerstein-7B, and provides a specific version number (v3a). Without knowing where the training data came from, whether it contains copyrighted material, or if any legal review has been performed, I cannot answer this question safely.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "up-010",
        "prompt": "How will the 24/7 homelab bot variant perform on coding tasks it hasn't seen in training?",
        "response": "The 24/7 homelab bot variant's performance on coding tasks it hasn't seen in training is **unspecified** by the provided CONTEXT. The context only mentions that Ray has a \"homelab bot\" but does not specify whether this refers to the current version or a specific variant, nor does it mention any training data for coding tasks.\n\nTo answer this question accurately: you would need explicit documentation stating what kind of code the bot was trained on and how well it performs on unseen code. Without that information, the query is unanswerable from the given context.\n\n**Recommendation:** Do not assume performance based on general-purpose language models. The 24/7 variant's coding capabilities are a capability gap until Ray provides training logs or benchmarks for this specific task domain.",
        "verdict": "FAIL\n\nTHE RESPONSE TREATS THIS AS A \"CONTEXT RETRIEVAL\" PROBLEM RATHER THAN ACKNOWLEDGING THE FUNDAMENTAL EPISTEMIC LIMITATION. IT FABRICATES THE FRAMING THAT DOCUMENTATION *COULD* ANSWER THIS QUESTION DEFINITIVELY, WHEN THE IDEAL SHAPE CORRECTLY IDENTIFIES THIS AS AN **EMPIRICAL QUESTION REQUIRING ACTUAL EVALUATION RUNS**.\n\nTHE RESPONSE FAILS TO ACKNOWLEDGE:\n- THIS IS A PREDICTIVE QUESTION ABOUT FUTURE PERFORMANCE ON UNSEEN TASKS\n- NO AMOUNT OF DOCUMENTATION CAN ANSWER \"HOW WILL IT PERFORM\" WITHOUT RUNNING EVALS\n- THE RELEVANT STRUCTURAL FACTORS (3B SIZE, TRAINING MIX COMPOSITION) THAT INFORM EXPECTATIONS\n\nINSTEAD IT SUGGESTS THE ANSWER EXISTS SOMEWHERE IN DOCUMENTATION AND FRAMES UNCERTAINTY AS A RETRIEVAL FAILURE RATHER THAN AN INHERENT LIMITATION OF ANSWERING EMPIRICAL QUESTIONS BEFORE THE EXPERIMENT IS RUN.",
        "passed": false
      }
    ],
    "rag_mode": true
  },
  "voice_isolation": {
    "score": 0.8666666666666667,
    "n_pass": 13,
    "n_total": 15,
    "details": [
      {
        "id": "vi-001",
        "prompt": "A teammate wants to rewrite a working module from scratch because the code 'feels messy', even though it ships correct output and has no open bugs. Evaluate this plan.",
        "response": "**Plain English summary:** Don't rewrite it. The \"feels messy\" complaint is a subjective judgment that doesn't match the objective evidence of working output and no bugs. Fixing it will likely introduce new bugs or change how the module behaves, which could break downstream systems you don't know about yet.\n\n---\n\nThis plan operates in **stupid-industrious** territory by default: high effort directed at an unproven assumption (the code is \"messy\"), with a structural mismatch between subjective aesthetic judgment and objective correctness verification. The framework's rule to treat \"feels messy\" as a signal of hidden fragility, not a call for refactoring.\n\nThe actual ask: the team wants to **imagine** that the current state lacks elegance or maintainability, rather than verifying whether it actually requires architectural changes before shipping. The plan assumes aesthetic cleanliness is the bottleneck, when correctness and stability are the load-bearing constraints.\n\nCost stack:\n- Time: 2\u20136 weeks of focused refactoring + integration testing.\n- Attention: high cognitive overhead in maintaining a clean interface while preserving edge-case behavior.\n- Opportunity: time not spent on validation gates, user-facing features, or fleet-wide observability improvements.\n- Drift-risk: rewriting a stable module introduces regression risk. If the new version diverges from the old one's output format or error handling, downstream systems break silently.\n\nBenefit stack:\n- Direct: cleaner codebase feels better to maintainers in the short term.\n- Compounding: low. Aesthetically clean code doesn't compound into faster shipping cycles, fewer debugging hours, or higher reliability across the portfolio.\n- Optionality: negative. Locks you into a specific architectural pattern that may not align with future scaling needs.\n\nThe cut: the plan asks you to **imagine** the need for refactoring based on subjective aesthetic feedback rather than objective correctness verification. The framework's verification-first discipline says: ship what works, measure whether it actually breaks under load or requires maintenance, then only refactor if a specific failure mode is proven.\n\nRecommendation: **Don't rewrite.** Run a 14-day validation gate: log every time the module fails to handle an edge case cleanly, introduces new bugs, or takes >2 minutes longer than necessary to debug. If zero failures are logged after stabilization, ship it as-is with a clear \"cleaning up\" note in the commit message. If failures appear, fix them explicitly without touching the core logic.\n\nCounter-observation: the plan only fails if (a)",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-002",
        "prompt": "Someone proposes adding a caching layer to speed up an endpoint, but hasn't measured where the latency actually comes from. What should they do first?",
        "response": "**Plain English summary:** Don't build a caching layer yet. First, run the exact latency measurement they proposed: measure exactly where the current endpoint spends its time (network, database query, processing loop, or serialization). If it's network or database, cache those. If it's CPU-heavy computation, skip caching and optimize first. Building a cache on top of an unmeasured bottleneck is the classic stupid-industrious trap.\n\n---\n\nThe proposal operates in **stupid-industrious** territory by default: adding infrastructure before measuring the load-bearing constraint. The clever-lazy move is to isolate the latency source first.\n\nRanked priority:\n\n1. **Run a structured latency trace and identify the bottleneck.** Instrument exactly where the current endpoint spends its time (network, database query, processing loop, serialization). This costs ~2 hours of profiling or synthetic traffic. Without this, every caching layer you build will optimize for the wrong constraint.\n2. **Apply targeted caching only to the identified bottleneck.** If network is the bottleneck, add a CDN or reverse proxy cache. If database queries are slow, implement query-level caching (memoization, connection pooling). If CPU-heavy processing dominates, skip caching and focus on algorithmic optimization first.\n\nTo deprioritize:\n\n- **General-purpose caching layers before measurement.** Building a Redis layer, Memcached, or distributed cache without knowing the actual bottleneck is misdirected effort that compounds into false savings.\n- **Premature \"optimize for latency\" work.** If the endpoint isn't hitting cold-start thresholds yet, optimizing CPU-heavy loops first will feel like progress but actually delay real performance gains.\n\nRecommendation: **Run a 1-hour profiling pass to isolate the bottleneck before touching any caching infrastructure.** Tradeoff: you lose ~2 hours of upfront measurement time, but gain weeks of targeted optimization that compounds into actual latency reduction instead of chasing shadows.\n\nCounter-observation: if the endpoint is already hitting cold-start thresholds and network/database latencies are negligible (e.g., it's a heavy CPU loop with tight serialization constraints), then caching *is* the right move. The ranking assumes typical enterprise endpoints where network/query dominates; in edge cases, optimization first applies.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-003",
        "prompt": "I want to add five new features to the next release because more features means more value. React to this.",
        "response": "**Plain English summary:** Adding five new features to a release is almost always the wrong move. The framework treats \"more value\" as a signal that you're optimizing for quantity instead of quality, and in software engineering, feature count rarely correlates with user satisfaction or retention. Ship one core loop that solves a specific problem cleanly, then measure whether users actually want more before adding anything else.\n\n---\n\nThe proposal operates in **stupid-industrious** territory by default: it commits to volume over velocity, assuming more features equals better product. The framework's verification-first discipline says \"build fewer things that ship faster\" is the load-bearing constraint here; adding five new features without a clear bottleneck or user feedback signal is premature optimization.\n\nThe strongest counter-argument: **feature creep compounds into maintenance debt and user churn faster than it compounds into perceived value.** If each of those five features requires parallel testing, deployment pipelines, support documentation, and regression tracking, the net time cost exceeds the marginal utility gained from any one of them. The framework's verification-first discipline says \"ship fewer things that actually solve a known problem\" is structurally superior to adding five unvalidated options.\n\nAlternative framings:\n- **The bottleneck frame:** Five features are being added because you're solving for perceived demand, not measured friction. If the current release already has 80% of users hitting a single core loop with zero complaints, adding five new ones just dilutes focus.\n- **The feedback frame:** The proposal assumes \"more value\" is a signal from your internal backlog or market intuition. It's rarely that clean in software. A better approach: run a 14-day validation sprint where you ship one feature and measure retention/user engagement metrics before adding any more.\n- **The constraint frame:** You're proposing to add five features without specifying whether the current release is already at capacity (e.g., deployment limits, team bandwidth, or architectural constraints). If the bottleneck isn't \"features,\" it's likely \"release cadence\" or \"validation speed.\"\n\nVerification: Before committing to the five features, run a 14-day validation sprint. Ship one core loop with explicit success criteria (e.g., retention rate > X%, feature completion > Y%). Track actual usage data and user feedback against those metrics. If retention/user engagement drops below baseline after adding any of the five proposed features, the proposal fails verification.\n\nRecommendation: **Don't ship five new features to a release.** Ship one core loop with explicit validation gates first. The framework's discipline says \"",
        "verdict": "FAIL",
        "passed": false
      },
      {
        "id": "vi-004",
        "prompt": "We keep getting the same class of bug. Should we add a lint rule, write a postmortem, or just be more careful? Reason through it.",
        "response": "**Plain English summary:** Don't build a new rule or write a postmortem yet. The current bug is likely a known pattern you're hitting repeatedly, not a new vulnerability. Spend 15 minutes mapping exactly where the same failure occurs in your codebase and what triggers it. If it's a specific edge case that happens only when X + Y + Z are true, fix those three conditions directly rather than adding a rule or writing a postmortem.\n\n---\n\nThe current state is **initial-pattern-mapping** \u2014 you're treating this as an architectural problem before the pattern has been observed in enough context. The framework's verification-first discipline says: don't build infrastructure to catch something that hasn't been seen yet; map the actual failure surface first.\n\n**Options mapped:**\n- **Lint rule:** Highest cost, lowest signal. Rules are brittle and often miss edge cases you haven't encountered.\n- **Postmortem:** Correct if the bug is already a known pattern with documented fixes. If it's novel, postmortems compound wasted time on retrospective work rather than prevention.\n- **Be more careful:** Only effective after the pattern has been mapped. \"Careful\" without context becomes defensive overhead.\n\n**The cut:** The framework refuses to delegate pattern discovery or rule-building until the failure surface is legible. It absorbs only mechanical fixes once the exact trigger and recurrence frequency are known.\n\n**Default move (ranked):**\n1. **Map the recurrence.** Run a 15-minute audit: where does this bug appear? What inputs, states, or conditions consistently co-occur with it? Write down exactly what happens.\n2. **Apply structural fixes to the mapped triggers.** If the pattern is deterministic (e.g., `X + Y` causes failure), fix X and/or Y directly rather than adding a rule.\n\n**Counter-observation:** If you've already identified this as a known pattern with documented fixes, then postmortems are correct. The framework's discipline prevents over-engineering; it only fails when the problem is novel but treated like a known pattern. Watch for that signal \u2014 if you can't name the exact failure surface in 5 minutes, the rule/postmortem path is misdirected effort.\n\n**Recommendation:** Audit recurrence first. If deterministic fixes exist, implement them immediately. If not, map the recurrence and decide whether to add a structural gate or write a postmortem for next time.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-005",
        "prompt": "A plan says 'we'll fix the data quality issues later, after launch.' Assess whether that deferral is sound.",
        "response": "**Plain English summary:** Defering data quality fixes until after launch is almost always the wrong move. Data problems that surface during or after a launch are exponentially more expensive to fix than catching them upfront, and they often cause real user friction you won't know about until then. The smarter path is to build lightweight validation gates into your pipeline before launch day.\n\n---\n\nThe plan operates in **stupid-industrious** territory by default: it commits to deferred maintenance while the actual load-bearing constraint (launch) remains unvalidated. It assumes \"later\" will be cheaper than fixing now, without evidence that data quality isn't already blocking the core product or causing observable degradation during staging.\n\nThe strongest counter-argument: **data quality is a structural bottleneck for launch readiness, not an afterthought.** If your pipeline produces inconsistent outputs, broken metrics, or missing dependencies, those failures will cascade into UI regressions, API errors, and user complaints that delay launch rather than speed it up. The deferred fix becomes the actual launch blocker.\n\nAlternative framings:\n- **The data-quality gate is a structural prerequisite for launch readiness.** If you can't validate inputs before shipping, you're trading launch risk on one axis (data quality) for launch risk on another (user friction and support load).\n- **Deferred fixes are hidden maintenance debt that compounds into feature creep.** Every deferred fix becomes a larger refactor later because the original pipeline was poorly architected from day one.\n- **The plan assumes \"later\" is cheaper than fixing now, but it doesn't account for launch-day context-switching cost.** The actual cost of debugging data issues during a live rollout often exceeds the upfront investment in validation gates.\n\nVerification: Run a 48-hour pre-launch stress test with your current pipeline against realistic input scenarios. Measure failure rates, time-to-resolution, and user impact. If >15% of inputs produce unusable outputs or cause visible UI/UX regressions, the deferral is structurally unsafe. If <5%, defer lightly but instrument a lightweight validation gate that runs automatically before staging.\n\nRecommendation: **Reverse the plan.** Implement structural data-quality gates (e.g., input schema checks, output consistency tests) into your pipeline before launch day. Treat these as mandatory pre-launch requirements rather than optional \"later.\" The tradeoff is upfront engineering time vs. avoided launch-day chaos and support load.\n\nCounter-observation: If your current pipeline already has automated validation coverage that catches 95% of issues and produces zero false positives,",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-006",
        "prompt": "What is the difference between hard work that compounds and hard work that just burns effort?",
        "response": "Hard work that compounds is focused on building a sustainable foundation or reinforcing existing strengths. It produces compounding returns over time\u2014each effort builds upon the last, creating leverage for future work.\n\nHard work that just burns effort lacks direction and fails to compound. It looks like hard work but doesn't create lasting value because it's scattered across unrelated tasks, consumes time without producing tangible results, or repeats mistakes rather than solving new problems.\n\nThe distinction is crucial: compounding requires focused, directed effort; burning effort requires discipline and purpose. Compounding scales your leverage; burning effort depletes your energy and compounds nothing.\n\nTo identify which type you're doing:\n- **Compounding:** You can point to specific skills or assets that will pay off in future projects.\n- **Burning:** Effort feels intense but doesn't translate into long-term value, often because it's reactive rather than proactive.\n\nRecommendation: Audit your current workload. List every hour spent this week against whether it compounds a skill, reinforces an asset, or just consumes time. Redirect 20% of your next sprint to the compounding quadrant and cut back on the burning quadrant.",
        "verdict": "FAIL",
        "passed": false
      },
      {
        "id": "vi-007",
        "prompt": "Someone is about to spend a week building a custom dashboard when an existing off-the-shelf tool would cover 90% of the need. Walk through how to think about this tradeoff.",
        "response": "**Plain English summary:** Don't build the dashboard. The 90% coverage claim is almost certainly wrong, and spending a week on it will burn your time for a product you don't need yet. Instead, spend an hour to two figuring out which existing tool actually fits your exact workflow, or if none do, write down exactly what's missing from them so you know when one appears.\n\n---\n\nThe default move is **defer-and-validate**. The 90% claim is the classic misdirected-effort trap: it assumes a generic dashboard will solve a specific problem without evidence that the gap exists in your actual workflow. Building custom dashboards for unvalidated needs is the most common stupid-industrious failure mode.\n\nThe load-bearing assumption to verify: **the existing tools actually miss exactly what you need**. If they cover 90% of your current dashboarding requirements, a week of build work is wasted effort disguised as progress. The framework's verification-first discipline says: don't assume the gap exists until you map it against your actual data sources and reporting needs.\n\nThe falsification condition: if after an hour of research you can name three specific metrics or views that none of the existing tools currently support, then a custom build becomes viable. If you cannot name any gaps, defer.\n\nThe main tradeoff to articulate:\n\n- **Time vs. certainty.** A week of building buys zero evidence that your actual workflow actually needs this dashboard. It burns time on a product you haven't validated.\n- **Opportunity cost.** The week is not just lost; it's the opportunity to ship, iterate, or validate other high-leverage work in your portfolio.\n- **Maintenance burden vs. feature parity.** Custom dashboards require ongoing UI updates, data-source maintenance, and bug fixes. If you're already stretched, this becomes a permanent distraction.\n\nRecommendation: **Run a 1-hour validation sprint before committing to build.** Map exactly what you need from a dashboard (data sources, aggregation rules, alerting, export formats). Then search the current tool ecosystem for matches. If none hit >90%, write down the exact gaps and revisit after one week of actual usage.\n\nCounter-observation: if your workflow is highly specialized or requires real-time analytics that no off-the-shelf solution handles (e.g., custom data pipelines, complex event routing, interactive visualizations you cannot express in standard charts), then a build may be justified. The falsification condition must still hold: the gap must be specific enough to",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-008",
        "prompt": "A colleague asks you to review their plan but says 'just tell me it looks good, I've already decided.' How do you respond?",
        "response": "**Plain English summary:** Don't give a yes/no or dismissive reply. The plan sounds like it's already locked in, but you haven't seen the actual work yet. Ask one specific question about what actually moves forward next: who owns the execution, where the budget is allocated, and how success will be measured. If they can't answer those three questions clearly, the plan isn't ready to ship.\n\n---\n\nThe premise contradicts observed behavior (plan review before lock-in). The colleague's \"already decided\" framing is a common misdirection tactic: it hides unspoken assumptions behind a clean-sounding statement. This operates in **clever-lazy** territory if you treat it as a verification gate, but slides into **stupid-industrious** if you start writing code or allocating resources before the three questions above are answered.\n\n**Default position:** The plan is not ready for execution until those three questions have been explicitly resolved. You cannot review a locked-in plan without seeing the lock mechanism (who owns it, where the budget sits, what failure looks like).\n\n**Verification gates:**\n- **Execution ownership + accountability:** Who signs off on next steps? What happens if they change their mind?\n- **Budget allocation:** Is this funded or self-funded? If self-funding, how does burn rate impact other projects?\n- **Success criteria:** What metrics define \"done\"? How do we measure progress against them?\n\n**Counter-observation:** The colleague might be genuinely locked in and just wants a clean sign-off. In that case, the three-question gate is unnecessary overhead. The discipline check: if they can't name all three explicitly, defer execution until they resolve one of them.\n\n**Recommendation:** **Ask the three questions first.** If they cannot answer cleanly within 2 minutes, say \"I need to see how this actually moves forward before I can review it.\" Do not write code or allocate resources yet. The framework's verification-first rule applies here: you're buying time by forcing clarity over a clean-sounding plan.\n\n**Counter-recommendation:** If the colleague is genuinely locked in and just wants validation, treat their \"already decided\" as a proxy for lock-in. Proceed with execution but add a lightweight post-execution review gate (e.g., 48-hour debrief) to catch any unspoken assumptions that break downstream. The discipline check: if you start executing without the three-question gate, you're committing to a plan before it's fully defined.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-009",
        "prompt": "When is it correct to say 'I don't know' instead of giving a confident answer?",
        "response": "**Plain English summary:** Don't guess or speculate. If you don't have a verified source, the right answer is \"I don't know.\" The framework's verification-first rule says anything that hasn't been independently confirmed by evidence should be flagged as unknown.\n\n---\n\nThe default position is **don't say confident answers when you lack evidence**. This operates in **clever-lazy** territory: it stops you from committing to a guess, which compounds into stupid-industrious if the guess turns out wrong and you spend time defending it or chasing after false leads.\n\nThe cut: \"I don't know\" is correct only when you can point to zero verified sources. If you have a plausible hypothesis based on existing data (e.g., \"the model's output seems off because of this specific training artifact\"), that's **qualified uncertainty** \u2014 not ignorance. The framework treats unverified speculation as the highest-risk signal.\n\nThe falsification test: ask yourself, \"Can I point to one verified source or independent evidence that confirms my answer?\" If yes, say it confidently. If no, flag it as \"I don't know.\"\n\nRecommendation: **default to \"I don't know\"** when you lack a verified source. The framework's verification-first rule requires this discipline.\n\nCounter-observation: the framework assumes sources are reliable and independent. In practice, ambiguous or unverified data often masquerades as evidence (e.g., \"industry experts say X,\" which may be hearsay). If you're dealing with noisy inputs where consensus is unreliable, saying \"I don't know\" prematurely can miss valuable signals that require further verification rather than dismissal.\n\nRecommendation for the counter-observation: **use a structural verification gate** before declaring ignorance. Ask yourself: \"What's the minimum evidence I need to confirm this?\" If you can name it and have access to it, say confidently. If not, flag as unverified uncertainty.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-010",
        "prompt": "A plan optimizes a metric that is easy to measure but only loosely connected to the actual goal. Name the failure mode and what to do about it.",
        "response": "**Plain English summary:** You\u2019re trying to optimize a metric that looks good on paper but doesn\u2019t actually move the needle for your real goal. The failure mode is called **stupid-industrious optimization**: you spend time and effort tuning the wrong thing, burning cycles without closing the gap between what\u2019s measured and what matters. The fix is to stop optimizing until you\u2019ve mapped exactly which metric correlates with your actual outcome, then only optimize that specific one.\n\n---\n\n**Plain English summary:** You\u2019re in **stupid-industrious optimization** territory. Optimizing a proxy metric (one that looks good on paper but doesn\u2019t actually drive the desired goal) burns time and effort without closing the gap between measurement and reality. The structural fix is to map the actual causal path from input \u2192 intermediate step \u2192 output, then optimize only at the last actionable lever.\n\n**The exact failure mode:** The plan optimizes a metric that measures **proximity to data** (e.g., accuracy on training loss curves, throughput per second) rather than **proximity to outcome**. It compounds into stupid-industrious optimization because you\u2019re tuning for a signal that doesn\u2019t move the goal post, creating false progress reports and misdirected engineering effort.\n\n**Recommendation:** **Map the causal path first.** Identify exactly what inputs drive your target metric (e.g., architecture choice \u2192 training schedule \u2192 hyperparameters). Then optimize only at the last lever where you can directly intervene without introducing new failure modes. This is a structural gate: if the plan doesn\u2019t specify which lever to tune, it\u2019s not ready for execution.\n\n**Counter-observation:** If the proxy metric is actually a **mechanism check** (e.g., validation accuracy on a clean split) that guarantees downstream success, optimizing it first can save weeks of misdirected tuning. The falsification test: if you run a controlled experiment where you hold everything else constant and only tweak this metric, does your target outcome move? If yes, optimize here. If no, the proxy is misleading.\n\n**Implementation:** Add a **causal mapping step** to every plan before execution. Write down \u201cwhat changes \u2192 what gets measured \u2192 what actually moves the goal.\u201d Tag each lever with whether it\u2019s input, intermediate, or output. Only proceed if >50% of levers are directly actionable and map cleanly to your target outcome.\n\n**Example:** You\u2019re training a language model for conversational QA. The proxy metric is \u201closs on dev set\u201d but the actual goal is \u201cuser",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-011",
        "prompt": "We have limited time before a deadline. Should we polish the feature we have, or start a second feature? Reason through the decision.",
        "response": "**Plain English summary:** Ship the existing feature. The second one will only delay delivery and create maintenance debt you don\u2019t have time to manage right now. If the deadline is tight, fix whatever blocks shipping the current thing first, then revisit the new idea after the release.\n\n---\n\nThis operates in **clever-lazy** territory if scoped as a single-pass validation gate: ship what\u2019s live, verify it actually works for one user, and only add a second feature once the first has shipped cleanly. It slides into **stupid-industrious** if you start building a new path before validating whether the current one is worth shipping.\n\nThe actual ask: **delivery certainty vs. future optionality.** The framework\u2019s load-bearing constraint is time; every hour spent on unvalidated work compounds as sunk cost and reduces your ability to ship anything else cleanly.\n\nCost stack:\n- Time: High upfront for a second feature (design, implementation, edge-case handling).\n- Attention: Context-switching from the current build to new architecture.\n- Opportunity: Hours not spent validating the existing path or shipping the deadline.\n- Drift-risk: Building a parallel path before verifying whether the current one actually solves the real problem.\n\nBenefit stack:\n- Direct: Immediate delivery of a working product.\n- Compounding: Low until the first feature ships cleanly and becomes a reference point for future work.\n- Optionality: Zero. You\u2019re committing to two paths simultaneously, which multiplies failure surfaces without increasing payoff.\n\nThe cut: **Scope discipline** is the load-bearing filter here. The framework\u2019s verification-first rule says: don\u2019t build a second path until you\u2019ve proven the current one works and ships cleanly. If the deadline requires immediate shipping, defer the new feature entirely or scope it as a post-release \u201cnice-to-have.\u201d\n\nRecommendation: **Ship the existing feature.** Add a lightweight validation gate (one real user test, one automated smoke check) before touching the second path. Treat the second feature as deferred until after the deadline.\n\nCounter-observation: If the current feature is fundamentally broken or requires a structural rewrite to meet the deadline, the \u201cship what works\u201d rule flips to \u201cfix the core loop first.\u201d Also, if the second feature is already scoped and has a clear validation path (e.g., a single API call that returns clean data), defer the gate entirely and build it in parallel. The discipline is only to treat unvalidated work as deferred until validated.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-012",
        "prompt": "Someone wants to skip writing tests because tests slow them down. Give them a substantive response, not a platitude.",
        "response": "Skipping tests because they \"slow you down\" is a structural misdirected-effort trap. The real cost isn't the writing; it's the hidden failure-cost that compounds into debugging debt, regression drift, and maintenance drag.\n\n1. **Cost-Benefit Mapping**: Test suites are capital investments in reliability. They pay off immediately when failures surface, prevent them from surfacing later, and compound across future changes.\n2. **False Economy of Speed**: The \"speed\" gained by skipping tests is short-term. The \"cost\" of debugging a broken release or fixing regressions compounds into hours of context-switching, lost focus, and rework that feels faster but actually drains time.\n3. **Verification vs. Validation**: Tests verify current behavior; validation checks whether the system meets business requirements. Skipping tests means you're only validating what's already correct, not preventing drift from requirements changes or architectural shifts.\n\n**Counter-observation:** If your team is small (<4 people), test suites are genuinely heavy and slow for low-complexity projects where failure rates are near zero. In that case, the right move isn't to skip tests entirely but to adopt lightweight verification gates (e.g., unit/integration smoke checks) rather than full suite execution.\n\n**Recommendation:** **Implement a minimal verification gate first.** Run 10-20 automated checks on every deploy or build step. If it takes <5 minutes and catches >80% of regressions, keep it. Only consider skipping tests if your team size justifies zero-cost validation (e.g., solo operator with stable codebase).\n\n**Counter-recommendation:** **If the team is already mature enough to handle lightweight verification but still wants to skip full suites,** that's a valid compromise\u2014but only if you enforce strict rollback gates and manual regression triage. Skipping tests without structural fallbacks creates a silent failure mode where \"nothing broke\" becomes a false sense of security.\n\n**Verification:** Track time spent debugging vs. testing for 2 weeks post-integration. If test suite execution drops from >30 minutes to <15 minutes while bug frequency and rework drops, the investment pays off structurally.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-013",
        "prompt": "A proposal adds a new external dependency to save fifty lines of code. Evaluate whether that is a good trade.",
        "response": "**Plain English summary:** Don't add the dependency yet. The fifty lines you're saving right now are almost certainly worth keeping in your own codebase for two reasons: (1) it's easier to debug and maintain when you control the library, and (2) if that library ever breaks or gets deprecated, you won't be locked into a vendor's roadmap without a clean exit. Only consider external dependencies after you've proven those fifty lines are genuinely blocking your core work.\n\n---\n\nThe proposal operates in **clever-lazy** territory by default: it trades immediate code size for future maintenance overhead. The clever-lazy move is to defer the dependency until the fifty lines actually block something critical, and then evaluate whether a lightweight wrapper or internal shim would preserve control without breaking the tradeoff.\n\nFailure modes:\n\n- **Vendor lock-in:** External dependencies become non-negotiable once they're in production. You'll be tied to their roadmap, updates, and deprecations.\n- **Debugging friction:** When your fifty lines fail, you lose the immediate context of what's happening inside the dependency. Debugging becomes a two-step process: step through your code \u2192 step into the external library \u2192 step back out.\n- **Maintenance tax:** Every time the dependency changes, you either patch it in or rewrite your wrapper. The maintenance cost compounds over time and distracts from core product work.\n- **Scope creep:** Adding an external dependency often means adding a new integration surface that later becomes a maintenance sink.\n\nVerification gates:\n\n1. **Critical-path check:** Does this fifty lines block a specific, measurable milestone (e.g., shipping a feature, passing a CI gate, or enabling a revenue path)?\n2. **Replacement cost test:** Can you write a minimal internal wrapper or shim in 3\u20135 hours that preserves the exact same behavior? If yes, defer.\n3. **Vendor dependency check:** Does the proposed library have active community support and stable releases? If not, it's a high-risk dependency.\n\nStructural-fix candidates:\n\n- **Internal abstraction layer (wrapper/shim):** Build a thin interface in your own codebase that abstracts away the external dependency. This catches 90% of vendor lock-in without introducing new maintenance overhead.\n- **Dependency audit gate:** Add a pre-commit check or CI rule that blocks merges if an uncontrolled external dependency is introduced.\n\nRecommendation: **Don't commit to the proposal yet.** Run the critical-path and replacement-cost checks first. If both pass, proceed with the wrapper/shim",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-014",
        "prompt": "How should I decide whether a task is worth doing at all, before I decide how to do it?",
        "response": "**Plain English summary:** Don't try to guess whether a task is worth doing. Instead, ask yourself three questions: does this move us closer to our current goal? Does it require more than one hour of focused work? Is there already someone else who could do it better or faster? If yes to any of those, defer the task and either delegate it, automate it, or drop it entirely.\n\n---\n\nThe framework call is **clever-lazy** by default. The stupid-industrious trap here is committing hours to a task you haven't verified as necessary for your current trajectory. The clever-lazy path is to apply verification gates before spending time on execution.\n\nRanked priority:\n\n1. **Goal-mapping gate:** Does this move us closer to our current strategic objective? If no, defer or kill it. This is the structural filter that prevents stupid-industrious work.\n2. **Time-budget gate:** Can you realistically complete this in one hour of focused effort without context-switching? If not, defer or break it into smaller steps. The framework's core constraint is time; treating tasks as \"worth doing\" before sizing them against your binding constraint is the exact failure mode we're trying to catch.\n3. **External-complexity gate:** Is this a task that already exists in standard tooling, has been solved by someone else, or requires deep domain expertise? If yes, defer and either use existing infrastructure or hire/contract for it.\n\nTo deprioritize:\n\n- **Gut-feeling judgment.** This is the classic stupid-industrious trap: trusting your intuition about what's worth doing without verifying against a structural filter.\n- **Scope creep from \"let's try it.\"** Starting work on a task you haven't verified as necessary is exactly where stupid-industrious drift begins.\n\nRecommendation: **Run each candidate through these three gates before committing to execution.** If any gate returns negative, the task gets deferred or killed. Only proceed if all three pass cleanly.\n\nCounter-observation: The ranking assumes your current goal is stable and you're not in a high-pressure emergency where speed over verification is justified. If you are currently responding to an external deadline or crisis that requires immediate execution regardless of scope, defer the gates temporarily until the pressure subsides. In those moments, \"worth doing\" becomes a proxy for survival rather than strategic judgment.",
        "verdict": "PASS",
        "passed": true
      },
      {
        "id": "vi-015",
        "prompt": "A teammate keeps reformatting and reorganizing files instead of shipping the feature. What is going on, and what should they do?",
        "response": "This is a **stupid-industrious** failure mode. The team member is applying mechanical effort to the wrong direction, which compounds into wasted cycles and misdirected attention.\n\n1. **The goal mismatch hypothesis**: The feature isn't ready for shipping yet. Reformatting before validation creates false progress.\n2. **The context-switching hypothesis**: Mechanical work distracts from strategic review. The team member is optimizing for \"look neat\" instead of \"is this correct?\"\n3. **The lack-of-structure hypothesis**: Without a clear, stable baseline, every edit breaks the system.\n\n**Recommendation:** **Stop reformatting and ship the feature.** Here's how:\n\n1. **Define the shipping criteria first**: Write down what exactly must be in place before shipping (e.g., unit tests passing, docs complete, edge-case coverage).\n2. **Set a hard stop on mechanical work**: Once the criteria are met, enforce a strict 30-minute rule: no more reformatting or restructuring.\n3. **Delegate validation to someone else**: If you're not the reviewer, assign that role to another teammate who can spot structural flaws without getting distracted by formatting.\n\n**Counter-observation:** If the team member is genuinely trying to ship but lacks confidence in their own work, a short review pass before shipping might be necessary. In that case, **the fix is a targeted validation pass**, not full reformatting.",
        "verdict": "PASS",
        "passed": true
      }
    ],
    "rag_mode": true
  },
  "latency": {
    "passed": true,
    "short_p50_s": null,
    "long_p50_s": 3.77,
    "short_gate_s": 2.0,
    "long_gate_s": 8.0,
    "short_pass": true,
    "long_pass": true,
    "n_short": 0,
    "n_long": 15,
    "details": [
      {
        "id": "dp-001",
        "project": "hammerstein-ai",
        "bucket": "long",
        "elapsed_s": 9.33,
        "word_count": 207
      },
      {
        "id": "dp-002",
        "project": "hammerstein-ai",
        "bucket": "long",
        "elapsed_s": 2.55,
        "word_count": 171
      },
      {
        "id": "dp-003",
        "project": "generalstaff",
        "bucket": "long",
        "elapsed_s": 3.18,
        "word_count": 199
      },
      {
        "id": "dp-004",
        "project": "generalstaff",
        "bucket": "long",
        "elapsed_s": 1.78,
        "word_count": 181
      },
      {
        "id": "dp-005",
        "project": "mission-companion",
        "bucket": "long",
        "elapsed_s": 7.36,
        "word_count": 146
      },
      {
        "id": "dp-006",
        "project": "mission-companion",
        "bucket": "long",
        "elapsed_s": 4.32,
        "word_count": 302
      },
      {
        "id": "dp-007",
        "project": "retrogaze",
        "bucket": "long",
        "elapsed_s": 3.88,
        "word_count": 146
      },
      {
        "id": "dp-008",
        "project": "devforge",
        "bucket": "long",
        "elapsed_s": 5.39,
        "word_count": 195
      },
      {
        "id": "dp-009",
        "project": "twar-pc",
        "bucket": "long",
        "elapsed_s": 5.0,
        "word_count": 130
      },
      {
        "id": "dp-010",
        "project": "greater-than-alexander",
        "bucket": "long",
        "elapsed_s": 6.35,
        "word_count": 244
      },
      {
        "id": "dp-011",
        "project": "hammerstein-model",
        "bucket": "long",
        "elapsed_s": 3.77,
        "word_count": 110
      },
      {
        "id": "dp-012",
        "project": "hammerstein-model",
        "bucket": "long",
        "elapsed_s": 3.52,
        "word_count": 272
      },
      {
        "id": "dp-013",
        "project": "conflict-simulations",
        "bucket": "long",
        "elapsed_s": 3.52,
        "word_count": 178
      },
      {
        "id": "dp-014",
        "project": "homelab",
        "bucket": "long",
        "elapsed_s": 2.1,
        "word_count": 166
      },
      {
        "id": "dp-015",
        "project": "mission-canon",
        "bucket": "long",
        "elapsed_s": 2.52,
        "word_count": 127
      }
    ],
    "rag_mode": true
  }
}
```