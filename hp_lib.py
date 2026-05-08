"""hp_lib — building blocks for the hp wrapper. See hp.py and DESIGN.md."""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
MAIN_LOG = HOME / ".hammerstein" / "logs" / "hammerstein-calls.jsonl"
HP_LOG = HOME / ".hammerstein" / "logs" / "hp-calls.jsonl"
HP_METRICS = HOME / ".hammerstein" / "logs" / "hp-metrics.jsonl"
GS_STATE_ROOT = HOME / "Desktop" / "Dev Work" / "generalstaff-private" / "state"
PREAMBLE_FILE = ".hp-preamble.md"
QUARANTINE_DIR = "quarantine"
DEFAULT_MAX_PREAMBLE_TOKENS = 3500
DEFAULT_TIMEOUT_S = 180
DEFAULT_TEMPLATE = "audit-this-plan"
HAMMERSTEIN_BIN = "hammerstein"
CORPUS_ID_RE = re.compile(r"## Reference: corpus #(\d+)")
HEADER_RE = re.compile(
    r"^\[backend=\S+ model=\S+ template=\S+ corpus=\d+ latency_ms=\d+ cost_usd=\$\d+\.\d+\]"
)


def count_tokens(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except ImportError:
        return len(text) // 4  # char-count fallback


def fetch_corpus_ids(query: str, template: str, timeout: int = 30) -> list[int]:
    cmd = [HAMMERSTEIN_BIN, "--show-prompt", "--template", template, query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"--show-prompt failed (rc={r.returncode}): {r.stderr.strip()}")
    return sorted({int(m.group(1)) for m in CORPUS_ID_RE.finditer(r.stdout)})


def validate_cli_contract() -> None:
    """Pre-flight: --show-prompt must produce ≥1 corpus ID. Exit 1 on drift."""
    try:
        ids = fetch_corpus_ids("contract pre-flight ping", DEFAULT_TEMPLATE, timeout=15)
    except (subprocess.TimeoutExpired, RuntimeError, FileNotFoundError) as e:
        sys.exit(f"hp: CLI contract pre-flight failed: {e}")
    if not ids:
        sys.exit("hp: CLI contract pre-flight failed: --show-prompt returned no corpus IDs")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def entry_ids(entry: dict) -> set[int]:
    """Coerce retrieved_corpus_ids (zero-padded strings in the log) to ints.
    Diagnostic only post-Phase-1.5 — the intersection-based filter was
    replaced; see hp_filter.py."""
    out = set()
    for x in entry.get("retrieved_corpus_ids") or []:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            pass
    return out


def format_entry(entry: dict, new_ids: set[int]) -> str:
    ts = entry.get("timestamp", "?")
    tmpl = entry.get("template", "?")
    matched = sorted(entry_ids(entry) & new_ids)
    query = (entry.get("query") or "").strip()
    if len(query) > 400:
        query = query[:400] + "…"
    response = (entry.get("response") or "").strip()
    if len(response) > 800:
        response = response[:800] + "…"
    return (
        f"### {ts} — template:{tmpl} — shared corpus IDs: {matched}\n\n"
        f"**Prior query:** {query}\n\n"
        f"**Prior response (excerpt):** {response}\n\n"
    )


def select_for_preamble(matches: list[dict], new_ids: set[int], max_tokens: int) -> list[dict]:
    """Greedy fill respecting a token budget. Input order preserved — callers
    are responsible for ordering (relevance-sorted from filter_by_relevance)."""
    selected, running = [], 0
    for e in matches:
        cost = count_tokens(format_entry(e, new_ids))
        if running + cost > max_tokens:
            break
        selected.append(e)
        running += cost
    return selected


def auto_detect_project_state(override: str | None) -> Path | None:
    if override:
        p = GS_STATE_ROOT / override
        return p if p.is_dir() else None
    p = GS_STATE_ROOT / Path.cwd().name
    return p if p.is_dir() else None


def read_project_state(state_dir: Path) -> str:
    parts = []
    mission = state_dir / "MISSION.md"
    if mission.is_file():
        parts.append(f"### MISSION.md\n\n{mission.read_text()}\n")
    tasks = state_dir / "tasks.json"
    if tasks.is_file():
        try:
            data = json.loads(tasks.read_text())
            parts.append(f"### tasks.json\n\n```json\n{json.dumps(data, indent=2)}\n```\n")
        except json.JSONDecodeError:
            pass
    turn_log = state_dir / "turn-log.md"  # load-bearing for wargame extension
    if turn_log.is_file():
        parts.append(f"### turn-log.md\n\n{turn_log.read_text()}\n")
    return "\n".join(parts)


def build_preamble(selected: list[dict], new_ids: set[int], state_dir: Path | None) -> str:
    parts = ["# hp preamble — structurally-similar prior context\n"]
    if selected:
        parts.append("## Prior structurally-similar audits\n")
        for e in selected:
            parts.append(format_entry(e, new_ids))
    if state_dir:
        body = read_project_state(state_dir)
        if body:
            parts.append("## Active project context\n")
            parts.append(body)
    return "\n".join(parts)


def run_hammerstein(query: str, template: str, ctx: Path, timeout: int) -> tuple[int, str, str]:
    cmd = [HAMMERSTEIN_BIN, "--template", template, "--context-file", str(ctx), query]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return r.returncode, r.stdout, r.stderr


def validate_response(stdout: str, stderr: str) -> tuple[bool, dict]:
    """Body on stdout, header on stderr. Both required for a valid call."""
    if not stdout.strip():
        return False, {"error": "empty stdout"}
    header_line = next((ln for ln in stderr.splitlines() if HEADER_RE.match(ln)), None)
    if not header_line:
        return False, {"error": "missing or malformed header line in stderr"}
    cost_m = re.search(r"cost_usd=\$(\d+\.\d+)", header_line)
    latency_m = re.search(r"latency_ms=(\d+)", header_line)
    return True, {
        "header": header_line,
        "cost_usd": float(cost_m.group(1)) if cost_m else None,
        "latency_ms": int(latency_m.group(1)) if latency_m else None,
        "body": stdout,
    }


def quarantine_output(stdout: str, stderr: str, error: str) -> Path:
    qdir = Path.cwd() / QUARANTINE_DIR
    qdir.mkdir(exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    qpath = qdir / f"{ts}.txt"
    qpath.write_text(f"# error: {error}\n\n## stdout\n\n{stdout}\n\n## stderr\n\n{stderr}\n")
    return qpath


def append_jsonl(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
