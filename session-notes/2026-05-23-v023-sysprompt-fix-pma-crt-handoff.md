# Session 2026-05-23 — v0.2.3 training + sysprompt fix + PMA-on-CRT + handoff

Long session. Picks up from morning v0.2.2 ship; ends with v0.2.3 still
in flight on pod attempt 8 (HF push pipeline). Wraps for clear; next
session continues here.

## Where things sit right NOW (fresh-session pickup)

### Live operational state

- **Bot:** running on `127.0.0.1:8765`. Latest version of `bot/server.mjs`
  with PMA endpoint + git-pull + mtime-invalidation patches. Owner is
  Ray (Telegram id 5985502285). Routes through the Rung 1 sidecar.
- **Sidecar:** `scripts/rung1_server.py` on `127.0.0.1:8766`. Latest
  RUNG1_SYSTEM_PROMPT with the deployment-facts block. Restart-on-crash
  loop in the launcher (homelab `scripts/rung1-launcher.bat`).
- **Ollama:** `hammerstein-7b-v022` deployed and serving on `:11434`.
  Modelfile.v022 now carries a SYSTEM block with deployment facts so
  direct `ollama run` calls also get the honesty footing, not just the
  sidecar-routed path.
- **CRT face:** `homelab/crt-face/index.html` loads `crt-face-portrait.js`
  (the ASCII portrait of Hammerstein-Equord). PMA panel rendering as a
  bordered box left of the portrait. Ticker is frame-rate-independent.
  Live polling from the bot on 127.0.0.1.

### Pod in flight — DO NOT START ANOTHER WHILE THIS IS RUNNING

- **Background task:** `bvnlrsp14` (Re-fire v0.2.3 pod — 8th attempt, HF
  push pipeline). Output file at
  `C:\Users\rweis\AppData\Local\Temp\claude\C--Users-rweis-OneDrive-Documents-hammerstein-model\c3904b5d-09a0-436a-9a2b-9d54bea32773\tasks\bvnlrsp14.output`
- **Expected duration:** ~30-40 min from start (started ~14:30 PT today).
- **Success signal:** `bvnlrsp14` completes exit 0, GGUF lands at
  `D:\hammerstein-store\models\v0.2.3\hammerstein-7b-v023-q5_k_m.gguf`
  with magic bytes `b'GGUF'` and sha256 matching the pod-side hash
  embedded in the upload-done sentinel.
- **What previous 7 attempts taught us:** SSH/scp transfer from RunPod
  to this Windows PC is unreliable for 5GB files (truncation + header-zero
  corruption seen on consecutive runs). Switched to HuggingFace push as
  the transfer channel (chunked, checksummed, retryable). Captured in
  memory [[runpod-from-windows]].
- **HF repo target:** `lerugray/hammerstein-7b-v023` (private). Pod
  uploads + sentinel writes; local driver pulls via `hf_hub_download`
  with sha256 verification.

### When the pod lands (next-session immediate actions)

1. Verify `D:\hammerstein-store\models\v0.2.3\hammerstein-7b-v023-q5_k_m.gguf`
   exists, size ~5.07 GiB, first 4 bytes are `b'GGUF'`. (The driver
   should have already verified this, but double-check.)
2. `cp deploy/Modelfile.v023 D:\hammerstein-store\models\v0.2.3\Modelfile`
3. `cd D:/hammerstein-store/models/v0.2.3 && ollama create hammerstein-7b-v023 -f Modelfile`
4. Run the three evals:
   - `python scripts/v023_self_state_probe.py --model hammerstein-7b-v023 --tag v023-post-train`
   - `python scripts/v023_voice_probe.py --model hammerstein-7b-v023 --tag v023-post-train`
   - `python scripts/v2_eval_failure_modes.py --model hammerstein-7b-v023 --tag v023-post-train`
5. Compare to v0.2.2 baselines at `data/eval-self-state-probe-v022-*`,
   `data/eval-hammerstein-7b-2026-05-22-v1-baseline-v2.json`, etc. Use
   `python scripts/v2_compare_eval_runs.py` for the diff markdown.
6. If win: edit `homelab/.env` `MODEL=hammerstein-7b-v023`, restart bot.
   Verify via Telegram by sending "how you feeling?" — should land in
   the hybrid casual register with reciprocation, no fabrications.

## What changed this session (summary, with file refs)

### v0.2.3 training data + scripts (committed)

- `data/v023-voice-anchor-hand-2026-05-23.jsonl` — 40 hand-crafted
  voice pairs in the hybrid casual register Ray ratified via
  AskUserQuestion. Categories: bare greetings (no reciprocation),
  relational check-ins (with reciprocation), hybrid context-y casual,
  capability casual, pushback, emotional nuance, closers, self-state
  honesty.
- `data/v023-voice-anchor-extension-2026-05-23.jsonl` — 50 Sonnet-
  generated extension pairs in the same voice. Voice red-flag scan
  clean (no commercial-LLM tics, no framework-vocab leak, no emoji).
- `data/v023-voice-anchor-combined-2026-05-23.jsonl` — 90 pairs total.
- `data/ray-stack-sft-v0.2.3-additions.jsonl` — 444 pairs (354 v0.2.2
  + 90 voice). Sanitized clean.
- `scripts/v023_concat_sanitize.py` — builds the additions JSONL.
- `training/24-7-variant/train_v023_continued.py` — LR 2e-4, 2 epochs,
  3x oversample of additions, 250-pair v3a anchor. Dry-run: 2,123
  total examples, ~26 min on A5000.
- `training/24-7-variant/run_v023_pod.sh` — now uses HF push (replaced
  scp). Pod-side uploads GGUF + LoRA tar to private HF repo, writes
  sentinel + sha256 to `/workspace/v023-hf-upload-done`.
- `scripts/v023_fire_pod.py` — local driver. Reads HF token silently
  from `~/.cache/huggingface/token`, passes it to pod via env. Polls
  for sentinel, then `hf_hub_download` + magic-byte + sha256 verify.
- `deploy/Modelfile.v023` — Ollama Modelfile with tool-aware chat
  template and deployment-facts SYSTEM block.

### v0.2.2 deployment hardening (committed + deployed)

- `scripts/rung1_server.py` `RUNG1_SYSTEM_PROMPT` extended with the
  version history (v3a/v0.1/v0.2/v0.2.1/v0.2.2 only), Qwen2.5-7B base,
  port map, and explicit list of things that do NOT exist (dashboard,
  tracker, metrics, session IDs, GPU/uptime visibility, OpenRouter
  entry). Lifted manual-graded self-state honesty from 55.6% → 80.0%
  with zero training spend.
- `deploy/Modelfile.v022` + `.v023` — same SYSTEM block as the sidecar
  injects, so direct `ollama run` users also get the facts. Voice
  rules stay in weights; only deployment facts in SYSTEM.
- `D:\hammerstein-store\models\v0.2.2\Modelfile` synced to match.

### Probes + eval infrastructure (committed)

- `scripts/v023_self_state_probe.py` — 15 prompts × 3 runs at temp 0.7.
  Heuristic for invented-feature words. Outputs JSON + per-probe stats.
- `scripts/v023_voice_probe.py` — 15 prompts × 3 runs. Word-band per
  category, reciprocation correctness (relational MUST reciprocate /
  others MUST NOT), commercial-LLM-tic + framework-vocab denylist.
- `scripts/v023_rung1_plus_system_prompt.txt` — reference copy of the
  new sidecar prompt for grep-ability.
- Manual-graded baselines at:
  - `data/eval-self-state-probe-v022-baseline-manual-grades.json`
    (55.6% pass without sysprompt fix)
  - `data/eval-self-state-probe-v022-sysprompt-fix-manual-grades.json`
    (80.0% pass with sysprompt fix)

### CRT face (homelab repo, committed)

- `crt-face/crt-face-portrait.js` — full ASCII portrait of
  Hammerstein-Equord rendered with char-density brightness mapping.
  Replaces the procedural box-drawing face. State-signaling moved to
  palette + glow + scanline roll + glitch frequency + faint per-state
  jitter on the portrait block.
- PMA panel: bordered box LEFT of the portrait, "PMA" label breaking
  top edge, wrapped reflection text inside. Reads from bot's
  `/pma-reflection` endpoint every 30s.
- Ticker advance now frame-rate-independent (was slowing with the
  heavier portrait render load).
- Background-haze tier for the portrait (faint phosphor wash where the
  source photo's gray background is).

### Bot endpoint (homelab repo, committed)

- `bot/server.mjs` — new `/pma-reflection` endpoint. Reads
  `mission-PMA-private/state/{checkins,vents}`, parses ONLY PMA-response
  blocks from vents (Ray's raw input is filtered out before anything
  leaves the local box), calls Sonnet via OpenRouter for a one-line
  PMA-voice reflection. Cached 5min. mtime-watches the full state/ tree
  for invalidation. Auto-runs `git pull --ff-only` on
  `mission-PMA-private` per request (rate-limited to 25s intervals) so
  Ray's live mission-companion vents from the Mac surface on the CRT
  within ~30s of him sending a message from any device.
- `homelab/.gitignore` — added `bot/pma-reflection-cache.json`.
- `homelab/.env` — added `OPENROUTER_API_KEY` (sourced from
  `MiroShark/.env` per global CLAUDE.md).

### Memory files saved (global, persists across sessions)

- `feedback_sysprompt_before_retrain.md` — for self-state failures, try
  fact-injection in system prompt before committing to retrain. SFT
  fixes trained reflexes; system prompt fixes missing context.
- `reference_runpod_from_windows.md` — four real footguns: SSH detach
  (use tmux), GPU capacity flap (multi-candidate fallback), cp1252
  subprocess defaults (force UTF-8), Cloudflare 1010 (UA + Bearer).
  Also captures the scp corruption pattern that drove the HF switch.
- `feedback_no_engagement_pushing.md` — UPDATED with the relational-
  reciprocation relaxation. Relational prompts may reciprocate ("You?"
  / "Anything notable?"); audit / knowledge / refusal still hold the
  strict rule.
- `feedback_spot_check_visual_changes.md` — CRT/face/UI changes need a
  browser eyeball before "done." Headless capture on this Windows box
  has been unreliable; falling back to "ask Ray to verify on refresh"
  is acceptable IF explicitly flagged.
- `project_hammerstein_north_star.md` — long-term goal: hammerstein
  as Ray's daily-driver agent so he can downgrade Anthropic sub to
  $100/mo tier. Pod + agentic work bias toward replacing Claude use
  cases.
- `project_hammerstein_code_task_safety.md` — TIGHTENED 7-rule safety
  posture for v0.2.4+ agentic work. Branch-first for ALL repos (no
  own-project exception), separate `@hammerstein-bot` GitHub account
  (not Ray's token), credential-read denylist on file_read, human
  review required for CI/secrets/deploy/infra changes, kill switch +
  per-hour action ceiling, append-only audit log.

## Queued for the NEXT session (besides watching the pod)

Ray's request at end of session: build out a dashboard + a Mac-portable
version of the CRT face, both accessible from his Mac.

### A. Mac-accessible dashboard

Goal: a web UI visible from Ray's Mac that surfaces homelab state.
- **Hosted on this PC**, accessible from Mac on the LAN (or via
  Tailscale if not on same LAN).
- **What to show:** bot state (idle/thinking/etc), model version (v022
  vs v023 when deployed), recent Telegram exchanges (read-only),
  current PMA reflection, sidecar health, Ollama loaded models, pod
  status (if a pod is in flight, show progress; if not, show idle).
- **How to host:** simplest is to extend `bot/server.mjs` with a few
  new routes (`/dashboard`, `/api/recent`, `/api/pod-status`) and
  serve a small static HTML page from `homelab/dashboard/`. Bind to
  0.0.0.0 instead of 127.0.0.1 (currently it's loopback only). Need
  to verify Windows firewall allows inbound 8765 on the LAN — likely
  needs a one-time rule add.
- **From Mac:** point a browser at `http://<home-pc-ip>:8765/dashboard`.
  If Tailscale is set up between PC and Mac, use the Tailscale IP.

### B. Mac-portable CRT face (for 5" portable monitor)

Goal: Ray runs the same CRT face on a 5" portable monitor he uses at
work or wherever. Same visuals, scaled / cropped appropriately for the
small display.

- **Approach 1 (simplest):** the existing CRT face HTML is already
  responsive (uses window.innerWidth/Height). If Ray opens
  `http://<home-pc-ip>:8765/crt` (a new route serving
  `crt-face/index.html`) on his Mac in fullscreen mode, the face
  renders at the Mac's display size. For a 5" portable monitor at e.g.
  800x480, the fit math should handle it — but verify the portrait
  doesn't crop weirdly and the chrome (rails, ticker, sig meter) stays
  readable at that resolution. Likely need a tighter overscan margin
  for small displays.
- **Approach 2 (more polish):** create a "mini" variant
  (`crt-face-mini.js`) optimized for ~5" displays — possibly with a
  smaller portrait, larger chrome, simpler animations. New HTML page
  `mini.html` loads it. Bot serves both via simple static routing.
- **State source:** Mac CRT polls the home PC's bot `/state` +
  `/pma-reflection` over LAN. Same code path as the desktop CRT —
  no Mac-side logic needed beyond the browser.
- **Same firewall concern as the dashboard** — bot must bind 0.0.0.0.

### C. Continue watching the pod

If `bvnlrsp14` is still in flight when the next session opens, just
read its output file periodically (no polling needed — system notifies
on completion). If it's already done, follow the "When the pod lands"
checklist above.

## Total session spend

- OpenRouter: a handful of Sonnet calls for the PMA reflection
  generation and one for the voice-extension pair generation. <$0.20.
- RunPod: 8 pod-fire attempts. Each one ran some training (~30 min
  on A5000 at $0.16/hr or 4090 at $0.34/hr). Cost estimate ~$1.50-
  $2.50 across all attempts.
- Anthropic: significant Opus usage on this session, mostly justified
  by debug + design work.

## Quick-reference paths

| Thing | Path |
|---|---|
| Pod fire driver | `hammerstein-model/scripts/v023_fire_pod.py` |
| Pod run script | `hammerstein-model/training/24-7-variant/run_v023_pod.sh` |
| Modelfile.v022 | `hammerstein-model/deploy/Modelfile.v022` |
| Modelfile.v023 | `hammerstein-model/deploy/Modelfile.v023` |
| Sidecar | `hammerstein-model/scripts/rung1_server.py` |
| Bot | `homelab/bot/server.mjs` |
| CRT face | `homelab/crt-face/crt-face-portrait.js` |
| CRT entry | `homelab/crt-face/index.html` |
| Telegram conversation log | `homelab/log/conversations.md` |
| PMA state | `mission-PMA-private/state/{checkins,vents,journal,roasts}/` |
| Model storage | `D:\hammerstein-store\models\v0.X.X\` |
| Memory tree | `~/.claude/projects/.../memory/MEMORY.md` |
| HF token (DO NOT print) | `~/.cache/huggingface/token` |
| RunPod API key (DO NOT print) | `hammerstein-model/.env` `RUNPOD_API_KEY` |
| OpenRouter key | `homelab/.env` `OPENROUTER_API_KEY` (also `MiroShark/.env`) |
