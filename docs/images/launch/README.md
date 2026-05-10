# Launch screenshots — wargamer-mode UI

Captured 2026-05-09 with `web/backend/_screenshot.py` (Playwright,
headless Chromium, retina device-scale-factor 2, light theme,
`--no-dev-chips` to hide the dev-preview controls).

Subject campaign: `wargames/2022-ukraine/` — a CSL test campaign
with the *2022: Ukraine* (CSL) v1.12 rulebook uploaded as a PDF
source (auto-converted + LLM-digested), a BGG-sourced box-cover
image as a reference image, and a Turn 4 orders entry from a real
`hp_vision.py` call against the BGG-submitted post-Turn-1 board photo.

## Files

| File | Best use |
|---|---|
| [`wargame-full-page.png`](wargame-full-page.png) | Hero shot — the whole surface in one frame. Use as the lead image in r/LocalLLaMA, HN, X. |
| [`wargame-orders-panel.png`](wargame-orders-panel.png) | The AI-output-quality close-up: 8-section kriegspiel orders with the "What I see on the board" sanity-check belt + the "Unread:" line + Situation / Intent / Main Effort sections. The single most differentiating screenshot. |
| [`wargame-sources-panel.png`](wargame-sources-panel.png) | The NotebookLM angle: rules row with `digest` badge + `rules` badge + regenerate button; reference-image row with actual thumbnail of the box cover + `ref image` badge. Captures the persistent-context story at a glance. |
| [`wargame-turn-input.png`](wargame-turn-input.png) | The "drop a photo, type what happened, click Issue" simplicity shot — board-photo dropzone, OOB dropzone, status textarea, cost-preview row. |
| [`wargame-turn-log.png`](wargame-turn-log.png) | Campaign continuity — the per-turn log with status + INTENT for each prior turn, last-issued timestamp, model footer. |

## Suggested layout for r/LocalLLaMA post

1. Lead with `wargame-full-page.png` — establishes "this is a real
   working app, not a prompt-engineering demo."
2. Embed `wargame-orders-panel.png` after the eval-results section
   to demonstrate output quality.
3. Embed `wargame-sources-panel.png` in the "how it stays grounded"
   section — the digest + ref-image story is the unique angle vs
   other "AI for wargames" pitches.

## Reproducing

Server running on `127.0.0.1:8765` with `wargames/2022-ukraine/`
campaign present:

```bash
web/.venv/bin/python web/backend/_screenshot.py \
  docs/images/launch/wargame-full-page.png \
  --slug 2022-ukraine \
  --theme light \
  --width 1680 \
  --no-dev-chips
```

The script also auto-emits per-region crops next to the full-page
output — see `_screenshot.py` for which `.wg-*` selectors it captures.
