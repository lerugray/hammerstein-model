#!/usr/bin/env python3
"""Build the per-project RAG context bundle for the Stage 0 retrieval test.

Stage 0 (scope doc: docs/research/24-7-homelab-bot-variant-scope-2026-05-21.md)
asks the cheapest question that gates a RAG build: if you inject the relevant
project's canonical docs into the prompt, does the v0.1 model answer the domain
questions?

This script does the *retrieval* half — once, on a machine where the project
docs are checked out — and writes a portable JSON bundle the eval harness reads:

    {project_id: {"context": "<compacted canonical-doc text>",
                  "sources": [...], "approx_tokens": N}}

It is run on Ray's machine (where generalstaff-private + the project repos are
cloned), NOT on the RunPod pod. The pod only ever sees the resulting JSON.

CANONICAL DOCS ONLY. Session notes are excluded as noise per the Stage 0 spec.
Per project the bundle includes, when present:
  - README.md          from the project repo
  - MISSION.md         from generalstaff-private/state/<id>/ (or the repo)
  - tasks.json         COMPACTED — raw tasks.json is 75-136 KB (~25-40k tokens),
                       which alone overflows a 3B's 32k window. Each task is
                       reduced to: id | status | priority | title | done_note,
                       with long free-text fields truncated.
  - the INDEX.md entry for the project (one bullet of registration metadata)

tasks.json compaction is the load-bearing trick: it keeps the project-fact
signal (what shipped, what's pending, task titles) while dropping the JSON
structure bloat and the multi-paragraph done_note / interactive_only_reason
prose that pushes raw injection past the context limit.

Usage:
  python build_rag_context.py [--out PATH] [--dev-root DIR] [--max-task-chars N]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# project_id (as used in domain-prompts.jsonl) -> repo dir name under DEV_ROOT.
# None = no standalone repo; canonical docs come only from the GS-private state dir.
PROJECT_REPO = {
    "hammerstein-ai": "hammerstein-ai",
    "generalstaff": "GeneralStaff",
    "mission-companion": "mission-companion",
    "retrogaze": "retrogaze",
    "devforge": "Devforge",
    "twar-pc": "twar-pc",
    "greater-than-alexander": "greater-than-alexander",
    "hammerstein-model": "hammerstein-model",
    "conflict-simulations": "conflict-simulations",
    "homelab": None,
    "mission-canon": "mission-canon",
}

# project_id -> dir name under generalstaff-private/state/ (case as on disk).
PROJECT_STATE = {
    "hammerstein-ai": "hammerstein-ai",
    "generalstaff": None,  # public-state project; no private state/<id> dir
    "mission-companion": "mission-companion",
    "retrogaze": "retrogaze",
    "devforge": "devforge",
    "twar-pc": "twar-pc",
    "greater-than-alexander": "greater-than-alexander",
    "hammerstein-model": "hammerstein-model",
    "conflict-simulations": "conflict-simulations",
    "homelab": "homelab",
    "mission-canon": "mission-canon",
}

APPROX_CHARS_PER_TOKEN = 3.6  # conservative for English+JSON mix


def approx_tokens(text: str) -> int:
    return int(len(text) / APPROX_CHARS_PER_TOKEN)


def truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())  # collapse whitespace
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " [...]"


def compact_tasks_json(path: Path, max_task_chars: int) -> str:
    """Reduce a tasks.json array to a compact per-task line list.

    Raw tasks.json files run 75-136 KB; injecting them whole overflows the
    context window. Each task -> one block: id, status, priority, title,
    done_note (truncated). Drops interactive_only_reason, expected_touches,
    and other orchestration-only fields that carry no project-fact signal.
    """
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return f"(tasks.json unreadable: {e})"

    tasks = data.get("tasks", data) if isinstance(data, dict) else data
    if not isinstance(tasks, list):
        return "(tasks.json: unexpected shape)"

    lines = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        tid = t.get("id", "?")
        status = t.get("status", "?")
        prio = t.get("priority", "")
        title = truncate(str(t.get("title", t.get("description", ""))), max_task_chars)
        block = f"- [{tid}] status={status}"
        if prio != "":
            block += f" priority={prio}"
        block += f": {title}"
        # done_note carries the "what actually shipped" facts — keep, truncated.
        dn = t.get("done_note") or t.get("notes")
        if dn:
            block += f"\n    OUTCOME: {truncate(str(dn), max_task_chars)}"
        lines.append(block)
    return "\n".join(lines)


def extract_index_entry(index_path: Path, project_id: str) -> str:
    """Pull the one-or-two-line INDEX.md bullet for a project."""
    if not index_path.exists():
        return ""
    text = index_path.read_text()
    # Bullets look like: "- **<id>** — F:.../..." optionally with a description
    # line indented underneath. Match the bullet + any immediately-following
    # non-bullet indented continuation lines.
    lines = text.splitlines()
    out = []
    capturing = False
    # the id in INDEX may differ slightly; match the bare token in **bold**
    pat = re.compile(r"^\s*-\s+\*\*" + re.escape(project_id) + r"\*\*")
    # also try without the -private suffix that some INDEX ids carry
    alt_ids = [project_id, project_id + "-private"]
    pats = [re.compile(r"^\s*-\s+\*\*" + re.escape(a) + r"\*\*") for a in alt_ids]
    for ln in lines:
        if any(p.match(ln) for p in pats):
            capturing = True
            out.append(ln.strip())
            continue
        if capturing:
            # continuation = indented non-bullet line; stop at next bullet/header
            if ln.strip() == "" or ln.lstrip().startswith("-") or ln.startswith("#"):
                break
            out.append(ln.strip())
    return "\n".join(out)


def build_project_context(
    project_id: str,
    dev_root: Path,
    index_path: Path,
    max_task_chars: int,
) -> dict:
    parts = []
    sources = []

    repo_name = PROJECT_REPO.get(project_id)
    state_name = PROJECT_STATE.get(project_id)
    repo_dir = (dev_root / repo_name) if repo_name else None
    state_dir = (
        dev_root / "generalstaff-private" / "state" / state_name
        if state_name else None
    )

    # --- README.md (project repo) ---
    if repo_dir and (repo_dir / "README.md").exists():
        readme = (repo_dir / "README.md").read_text()
        parts.append(f"## {project_id} — README.md\n\n{readme.strip()}")
        sources.append(f"{repo_name}/README.md")

    # --- MISSION.md (prefer private state dir, fall back to repo) ---
    mission_text = None
    mission_src = None
    if state_dir and (state_dir / "MISSION.md").exists():
        mission_text = (state_dir / "MISSION.md").read_text()
        mission_src = f"state/{state_name}/MISSION.md"
    elif repo_dir and (repo_dir / "MISSION.md").exists():
        mission_text = (repo_dir / "MISSION.md").read_text()
        mission_src = f"{repo_name}/MISSION.md"
    if mission_text and mission_text.strip():
        parts.append(f"## {project_id} — MISSION.md\n\n{mission_text.strip()}")
        sources.append(mission_src)

    # --- tasks.json (compacted) ---
    tasks_path = None
    tasks_src = None
    if state_dir and (state_dir / "tasks.json").exists():
        tasks_path = state_dir / "tasks.json"
        tasks_src = f"state/{state_name}/tasks.json"
    elif repo_dir and (repo_dir / "tasks.json").exists():
        tasks_path = repo_dir / "tasks.json"
        tasks_src = f"{repo_name}/tasks.json"
    if tasks_path:
        compacted = compact_tasks_json(tasks_path, max_task_chars)
        parts.append(
            f"## {project_id} — task ledger (tasks.json, compacted)\n\n{compacted}"
        )
        sources.append(f"{tasks_src} (compacted)")

    # --- INDEX.md entry ---
    idx = extract_index_entry(index_path, project_id)
    if idx:
        parts.append(f"## {project_id} — portfolio INDEX entry\n\n{idx}")
        sources.append("state/INDEX.md (entry)")

    context = "\n\n".join(parts)
    return {
        "context": context,
        "sources": sources,
        "approx_tokens": approx_tokens(context),
        "approx_chars": len(context),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        default="training/24-7-variant/eval/rag-context.json",
        help="Output bundle path.",
    )
    ap.add_argument(
        "--dev-root",
        default=str(Path.home() / "Desktop" / "Dev Work"),
        help="Directory holding the project repos + generalstaff-private.",
    )
    ap.add_argument(
        "--max-task-chars",
        type=int,
        default=320,
        help="Truncation limit for per-task title / done_note free text.",
    )
    args = ap.parse_args()

    dev_root = Path(args.dev_root)
    index_path = dev_root / "generalstaff-private" / "state" / "INDEX.md"
    if not dev_root.exists():
        print(f"ERROR: --dev-root not found: {dev_root}")
        sys.exit(1)

    bundle = {}
    total_tokens = 0
    print(f"Building RAG context bundle from {dev_root}\n")
    for project_id in PROJECT_REPO:
        entry = build_project_context(
            project_id, dev_root, index_path, args.max_task_chars
        )
        bundle[project_id] = entry
        total_tokens += entry["approx_tokens"]
        flag = "  <-- OVER 24k" if entry["approx_tokens"] > 24000 else ""
        print(
            f"  {project_id:24s} ~{entry['approx_tokens']:6d} tok  "
            f"({len(entry['sources'])} sources){flag}"
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, indent=2))
    print(f"\nWrote {out_path}")
    print(f"Largest single-project context: "
          f"{max(e['approx_tokens'] for e in bundle.values())} tokens")
    over = [p for p, e in bundle.items() if e["approx_tokens"] > 24000]
    if over:
        print(f"WARNING: {len(over)} project(s) exceed 24k tokens: {over}")
        print("  Lower --max-task-chars or trim docs before the pod run.")
    else:
        print("OK: every project context fits under the 24k context budget.")


if __name__ == "__main__":
    main()
