# wargames/

User campaigns created via the wargamer-mode UI live here as
state-dirs (one folder per campaign). This directory is
gitignored except for `.gitignore` and this README.

The shipped example campaign stays at
[`wargame-example/`](../wargame-example/) at the repo root —
it doubles as the public-domain reference scenario.

## State-dir convention

Each campaign is a folder with:

```
wargames/<slug>/
├── MISSION.md        # scenario brief, ROE, victory conditions
├── tasks.json        # current OOB / orders / current_turn
├── turn-log.md       # human-readable per-turn narrative (append-only)
├── turn-log.json     # machine-readable per-turn structured entries
├── campaign.json     # name, started, spend, spend_budget, model
└── uploads/          # board photos / OOB sheets uploaded per turn
```

The wrapper (`hp_vision.py`) reads `MISSION.md`, `tasks.json`, and
`turn-log.md` automatically when called with `--state-dir
wargames/<slug>/`. The web UI writes the structured `turn-log.json`
+ `campaign.json` sidecars; both files are safe to edit by hand if
you need to repair state.

## Why the dir is gitignored

Campaign data is personal: board photos may be of copyrighted
materials (counter sheets, rulebook diagrams), and the `.md` files
are your in-progress play notes. Don't commit them upstream.
