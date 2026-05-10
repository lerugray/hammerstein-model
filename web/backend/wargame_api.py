"""Wargamer mode API — backs WargamePage.tsx.

Discovers campaigns from `wargame-example/` (shipped) and `wargames/`
(user-private), surfaces their state to the React UI, and proxies
"Issue orders" requests to `hp_vision.py` as a subprocess. Parses
the markdown response into the OrdersData shape the UI expects.

Persistence per campaign (one folder = one state-dir):

    campaign.json      — metadata (name, started, spend, model)
    tasks.json         — OOB / current_turn (operator-edited)
    MISSION.md         — scenario brief + AI role contract
    turn-log.md        — human-readable per-turn narrative
    turn-log.json      — machine-readable [TurnLogEntry] (UI source)
    orders-latest.json — last parsed OrdersData (UI hydration)
    uploads/           — board photos / OOB sheets per request

The hp_vision.py call also writes to hp-calls.jsonl + hp-metrics.jsonl
(the dashboard's data sources), so wargame turns surface in the
dashboard automatically.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from web.backend.wargame_parse import parse_orders
from web.backend.wargame_convert import pdf_to_md
from web.backend.wargame_digest import generate_digest, write_digest

REPO_ROOT = Path(__file__).resolve().parents[2]
HP_VISION_PY = REPO_ROOT / "hp_vision.py"
WARGAMES_DIR = REPO_ROOT / "wargames"
WARGAME_EXAMPLE_DIR = REPO_ROOT / "wargame-example"

DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
DEFAULT_BUDGET_USD = 1.20

router = APIRouter(prefix="/api/wargame", tags=["wargame"])


# --- discovery ---

def _discoverable_dirs() -> list[Path]:
    """All state-dirs the API surfaces. wargame-example always first."""
    out: list[Path] = []
    if (WARGAME_EXAMPLE_DIR / "MISSION.md").is_file():
        out.append(WARGAME_EXAMPLE_DIR)
    if WARGAMES_DIR.is_dir():
        for child in sorted(WARGAMES_DIR.iterdir()):
            if not child.is_dir():
                continue
            if (child / "MISSION.md").is_file():
                out.append(child)
    return out


def _slug_to_dir(slug: str) -> Path:
    """Resolve slug → state-dir, with safety check (no path traversal)."""
    if "/" in slug or ".." in slug or not slug.strip():
        raise HTTPException(400, f"invalid slug: {slug!r}")
    if slug == "wargame-example":
        return WARGAME_EXAMPLE_DIR
    candidate = WARGAMES_DIR / slug
    if not candidate.is_dir() or not (candidate / "MISSION.md").is_file():
        raise HTTPException(404, f"campaign not found: {slug}")
    return candidate


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s or "untitled"


def _read_json(p: Path, default: Any) -> Any:
    if not p.is_file():
        return default
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(p: Path, data: Any) -> None:
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _campaign_meta(state_dir: Path) -> dict[str, Any]:
    """Load campaign.json with sane defaults."""
    slug = state_dir.name
    raw = _read_json(state_dir / "campaign.json", {})
    name = raw.get("name") or slug.replace("-", " ").title()
    return {
        "slug": slug,
        "name": name,
        "started": raw.get("started", ""),
        "spend": float(raw.get("spend", 0.0)),
        "spend_budget": float(raw.get("spend_budget", DEFAULT_BUDGET_USD)),
        "model": raw.get("model", DEFAULT_MODEL),
    }


def _turn_log(state_dir: Path) -> list[dict[str, Any]]:
    return _read_json(state_dir / "turn-log.json", [])


def _current_turn(state_dir: Path) -> int:
    """Highest issued turn number, or 0 if none."""
    log = _turn_log(state_dir)
    return max((e.get("turn", 0) for e in log), default=0)


def _campaign_summary(state_dir: Path) -> dict[str, Any]:
    meta = _campaign_meta(state_dir)
    turn = _current_turn(state_dir)
    meta["turn"] = turn
    return meta


# --- routes ---

@router.get("/healthz")
def healthz() -> dict[str, Any]:
    """Precondition checks for the wargamer-mode upload + issue paths.
    Helps debug 'why doesn't it work' without diving into server logs."""
    checks: dict[str, Any] = {}
    try:
        import pymupdf4llm  # noqa: F401
        checks["pymupdf4llm"] = "ok"
    except ImportError as e:
        checks["pymupdf4llm"] = f"missing: {e}"
    try:
        import openpyxl  # noqa: F401
        checks["openpyxl"] = "ok"
    except ImportError as e:
        checks["openpyxl"] = f"missing: {e}"
    try:
        import multipart  # noqa: F401
        checks["python-multipart"] = "ok"
    except ImportError as e:
        checks["python-multipart"] = f"missing: {e}"
    checks["openrouter_api_key_set"] = bool(os.environ.get("OPENROUTER_API_KEY"))
    checks["hp_vision_present"] = HP_VISION_PY.is_file()
    checks["wargames_dir_writable"] = os.access(REPO_ROOT, os.W_OK)
    issues = [
        k for k, v in checks.items()
        if (isinstance(v, str) and v.startswith("missing")) or v is False
    ]
    return {
        "ok": not issues,
        "checks": checks,
        "issues": issues,
        "campaigns": len(_discoverable_dirs()),
    }


@router.get("/campaigns")
def list_campaigns() -> list[dict[str, Any]]:
    return [_campaign_summary(d) for d in _discoverable_dirs()]


@router.get("/campaigns/{slug}")
def get_campaign(slug: str) -> dict[str, Any]:
    state_dir = _slug_to_dir(slug)
    return {
        "campaign": _campaign_summary(state_dir),
        "turn_log": _turn_log(state_dir),
        "last_orders": _read_json(state_dir / "orders-latest.json", None),
    }


class CreateCampaignBody(BaseModel):
    name: str
    mission_md: str
    spend_budget: float = DEFAULT_BUDGET_USD
    model: str = DEFAULT_MODEL


@router.post("/campaigns")
def create_campaign(body: CreateCampaignBody) -> dict[str, Any]:
    if not body.name.strip():
        raise HTTPException(400, "name required")
    if not body.mission_md.strip():
        raise HTTPException(400, "mission_md required")

    slug = _slugify(body.name)
    target = WARGAMES_DIR / slug
    if target.exists():
        raise HTTPException(409, f"campaign exists: {slug}")
    target.mkdir(parents=True, exist_ok=False)

    (target / "MISSION.md").write_text(body.mission_md)
    _write_json(target / "tasks.json", {
        "scenario": body.name,
        "current_turn": 1,
        "ai_plays_side": "Red",
        "blue": [],
        "red": [],
    })
    (target / "turn-log.md").write_text(
        f"# Turn log — {body.name}\n\n"
        "Append-only per-turn snapshots. Newest turn at the top so "
        "the wrapper's recency-decay surfaces it first.\n\n---\n"
    )
    _write_json(target / "turn-log.json", [])
    _write_json(target / "campaign.json", {
        "slug": slug,
        "name": body.name,
        "started": dt.date.today().isoformat(),
        "spend": 0.0,
        "spend_budget": body.spend_budget,
        "model": body.model,
    })

    return {"campaign": _campaign_summary(target),
            "turn_log": [],
            "last_orders": None}


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
TEXT_EXTS = {".md", ".markdown", ".txt"}


@router.get("/campaigns/{slug}/sources")
def list_sources(slug: str) -> list[dict[str, Any]]:
    """List all persisted sources (rules + reference images) for this
    campaign. Both kinds get auto-included in every issue call:

      rules/*.md          → stacked into the AI's text preamble
      reference/*.{jpg,…} → attached as image_blocks every API call

    The frontend renders them as a single Sources list with kind tags.
    Digest sidecars (`<book>.digest.md`) are surfaced as a `has_digest`
    flag on the parent rule rather than as separate list rows."""
    state_dir = _slug_to_dir(slug)
    out: list[dict[str, Any]] = []
    rules_dir = state_dir / "rules"
    if rules_dir.is_dir():
        all_md = sorted(rules_dir.glob("*.md"))
        digest_stems = {f.stem.removesuffix(".digest") for f in all_md if f.name.endswith(".digest.md")}
        for f in all_md:
            if f.name.endswith(".digest.md"):
                continue  # surfaced via has_digest on parent
            digest_path = rules_dir / (f.stem + ".digest.md")
            has_digest = digest_path.is_file()
            digest_size = digest_path.stat().st_size if has_digest else 0
            # When a digest exists, the digest is what gets injected by
            # default — show its size in the UI's "tokens added" total
            # rather than the full rulebook's size.
            effective_size = digest_size if has_digest else f.stat().st_size
            out.append({
                "kind": "rules",
                "name": f.name,
                "size_bytes": f.stat().st_size,
                "tokens_est": _estimate_tokens(effective_size),
                "source": (
                    "converted from pdf"
                    if (rules_dir / (f.stem + ".pdf")).is_file()
                    else "uploaded markdown"
                ),
                "has_digest": has_digest,
                "digest_size_bytes": digest_size,
                "digest_tokens_est": _estimate_tokens(digest_size) if has_digest else 0,
            })
    ref_dir = state_dir / "reference"
    if ref_dir.is_dir():
        for f in sorted(ref_dir.iterdir()):
            if f.suffix.lower() in IMAGE_EXTS:
                out.append({
                    "kind": "reference",
                    "name": f.name,
                    "size_bytes": f.stat().st_size,
                    "tokens_est": 0,  # images are not counted in text tokens
                    "source": "reference image",
                    "has_digest": False,
                    "digest_size_bytes": 0,
                    "digest_tokens_est": 0,
                })
    return out


@router.post("/campaigns/{slug}/sources")
async def upload_sources(
    slug: str,
    files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    """Upload sources for this campaign. Routing by extension:

      .pdf            → pymupdf4llm + CSL cleanup pipeline → rules/<name>.md
      .md/.markdown/.txt → rules/<name>.md as-is
      .jpg/.png/.webp/.gif → reference/<name> as-is (every issue includes it)
    """
    state_dir = _slug_to_dir(slug)
    if not files:
        raise HTTPException(400, "no files uploaded")
    rules_dir = state_dir / "rules"
    ref_dir = state_dir / "reference"

    accepted: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for upload in files:
        if not upload.filename:
            continue
        safe_name = Path(upload.filename).name
        suffix = Path(safe_name).suffix.lower()
        data = await upload.read()
        if suffix == ".pdf":
            rules_dir.mkdir(parents=True, exist_ok=True)
            pdf_dest = rules_dir / safe_name
            pdf_dest.write_bytes(data)
            try:
                md = pdf_to_md(pdf_dest)
            except Exception as e:
                pdf_dest.unlink(missing_ok=True)
                errors.append({"file": safe_name, "error": f"pdf convert failed: {e}"})
                continue
            md_path = rules_dir / (Path(safe_name).stem + ".md")
            md_path.write_text(md)
            digest_err = _try_generate_digest(md_path, md)
            accepted.append({
                "kind": "rules",
                "name": md_path.name,
                "size_bytes": md_path.stat().st_size,
                "tokens_est": _estimate_tokens(md_path.stat().st_size),
                "source": "converted from pdf",
                "digest_status": digest_err or "ok",
            })
        elif suffix in TEXT_EXTS:
            rules_dir.mkdir(parents=True, exist_ok=True)
            md_dest = rules_dir / (Path(safe_name).stem + ".md")
            md_dest.write_bytes(data)
            digest_err = _try_generate_digest(md_dest, md_dest.read_text())
            accepted.append({
                "kind": "rules",
                "name": md_dest.name,
                "size_bytes": md_dest.stat().st_size,
                "tokens_est": _estimate_tokens(md_dest.stat().st_size),
                "source": "uploaded markdown",
                "digest_status": digest_err or "ok",
            })
        elif suffix in IMAGE_EXTS:
            if len(data) > 20 * 1024 * 1024:
                errors.append({
                    "file": safe_name,
                    "error": f"image > 20 MB (OpenRouter limit per image)",
                })
                continue
            ref_dir.mkdir(parents=True, exist_ok=True)
            img_dest = ref_dir / safe_name
            img_dest.write_bytes(data)
            accepted.append({
                "kind": "reference",
                "name": img_dest.name,
                "size_bytes": img_dest.stat().st_size,
                "tokens_est": 0,
                "source": "reference image",
            })
        else:
            errors.append({
                "file": safe_name,
                "error": (
                    f"unsupported extension {suffix!r} (accepted: "
                    ".pdf, .md, .markdown, .txt, .jpg, .jpeg, .png, .webp, .gif)"
                ),
            })

    return {"accepted": accepted, "errors": errors, "sources": list_sources(slug)}


@router.get("/campaigns/{slug}/reference/{filename}")
def get_reference_image(slug: str, filename: str) -> FileResponse:
    """Serve a reference image for thumbnail rendering in the Sources panel.
    Read-only static-file route restricted to images in `reference/`."""
    state_dir = _slug_to_dir(slug)
    if "/" in filename or ".." in filename or not filename.strip():
        raise HTTPException(400, f"invalid filename: {filename!r}")
    target = state_dir / "reference" / filename
    if not target.is_file() or target.suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(404, f"reference image not found: {filename}")
    return FileResponse(target)


@router.post("/campaigns/{slug}/sources/rules/{filename}/regenerate-digest")
def regenerate_digest(slug: str, filename: str) -> dict[str, Any]:
    """Re-run the LLM digest generation against an existing rules MD.
    Useful after a system-prompt tweak or model upgrade — saves the
    user from having to delete + re-upload the source PDF."""
    state_dir = _slug_to_dir(slug)
    if "/" in filename or ".." in filename or not filename.endswith(".md"):
        raise HTTPException(400, f"invalid filename: {filename!r}")
    if filename.endswith(".digest.md"):
        raise HTTPException(400, "cannot regenerate digest of a digest")
    rules_dir = state_dir / "rules"
    src = rules_dir / filename
    if not src.is_file():
        raise HTTPException(404, f"rules source not found: {filename}")
    err = _try_generate_digest(src, src.read_text())
    if err:
        raise HTTPException(502, err)
    return {"regenerated": filename, "sources": list_sources(slug)}


@router.delete("/campaigns/{slug}/sources/{kind}/{filename}")
def delete_source(slug: str, kind: str, filename: str) -> dict[str, Any]:
    state_dir = _slug_to_dir(slug)
    if "/" in filename or ".." in filename or not filename.strip():
        raise HTTPException(400, f"invalid filename: {filename!r}")
    if kind not in ("rules", "reference"):
        raise HTTPException(400, f"invalid kind: {kind!r}")
    sub_dir = state_dir / kind
    target = sub_dir / filename
    if not target.is_file():
        raise HTTPException(404, f"source not found: {kind}/{filename}")
    target.unlink()
    if kind == "rules":
        # Also drop the source PDF if it was the origin.
        src_pdf = sub_dir / (target.stem + ".pdf")
        src_pdf.unlink(missing_ok=True)
    return {"deleted": f"{kind}/{filename}", "sources": list_sources(slug)}


def _estimate_tokens(byte_count: int) -> int:
    """Rough heuristic: ~4 chars per token for English markdown."""
    return byte_count // 4


def _reference_image_paths(state_dir: Path) -> list[Path]:
    """All persisted reference images for this campaign, sorted."""
    ref_dir = state_dir / "reference"
    if not ref_dir.is_dir():
        return []
    return sorted(
        f for f in ref_dir.iterdir()
        if f.suffix.lower() in IMAGE_EXTS and f.is_file()
    )


def _try_generate_digest(md_path: Path, full_md: str) -> str | None:
    """Generate the digest sidecar. Returns None on success, an error
    string on failure. Failures are non-fatal — the upload still
    succeeds; the digest just isn't created (full rulebook stays in
    preamble until next attempt)."""
    try:
        digest_md, _meta = generate_digest(full_md)
        write_digest(md_path, digest_md)
        return None
    except Exception as e:
        return f"digest gen failed: {e}"


@router.post("/campaigns/{slug}/issue")
async def issue_orders(
    slug: str,
    status: str = Form(...),
    images: list[UploadFile] = File(default=[]),
    xlsx: UploadFile | None = File(default=None),
) -> JSONResponse:
    state_dir = _slug_to_dir(slug)
    if not status.strip():
        raise HTTPException(400, "status text required")
    # Precondition: the issue path requires OPENROUTER_API_KEY (hp_vision.py
    # would error after subprocess start otherwise — fail fast with a clean
    # message that surfaces in the UI's IssueRow error slot).
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise HTTPException(
            503,
            "OPENROUTER_API_KEY not set in server env. Add it to "
            "~/.hammerstein.env or ./.env and restart hp_web.sh.",
        )

    # Stage uploads in a per-request temp dir; they're persisted into
    # the campaign's uploads/ folder only after a successful issue so
    # we don't leave junk on failures.
    with tempfile.TemporaryDirectory(prefix="hp-wargame-") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        image_paths: list[Path] = []
        for upload in images:
            if not upload.filename:
                continue
            safe_name = Path(upload.filename).name
            dest = tmpdir / safe_name
            data = await upload.read()
            dest.write_bytes(data)
            image_paths.append(dest)

        xlsx_path: Path | None = None
        if xlsx is not None and xlsx.filename:
            safe_name = Path(xlsx.filename).name
            dest = tmpdir / safe_name
            dest.write_bytes(await xlsx.read())
            xlsx_path = dest

        # Persisted reference images (campaign-level Sources) are
        # prepended to the image list so the model sees them BEFORE
        # the per-turn board photo. Their static nature gets called
        # out in the status text so the model knows which is which.
        # The ref-note is added ONLY to the version sent to the model
        # (`status_for_model`); the persisted turn-log records the
        # operator's original input verbatim.
        reference_paths = _reference_image_paths(state_dir)
        status_for_model = status
        if reference_paths:
            ref_note = (
                "Persisted reference image(s) attached to this campaign "
                "(included in every turn — not the live board state): "
                + ", ".join(p.name for p in reference_paths)
                + ". The board photo(s) for THIS turn follow them."
            )
            status_for_model = ref_note + "\n\n" + status

        # Subprocess hp_vision.py with staged paths.
        cmd = [
            sys.executable, str(HP_VISION_PY),
            "--state-dir", str(state_dir),
        ]
        for p in reference_paths:
            cmd += ["--image", str(p)]
        for p in image_paths:
            cmd += ["--image", str(p)]
        if xlsx_path is not None:
            cmd += ["--xlsx", str(xlsx_path)]
        cmd.append(status_for_model)

        env = dict(os.environ)
        try:
            proc = subprocess.run(
                cmd, cwd=str(REPO_ROOT), capture_output=True,
                text=True, timeout=210, env=env,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(504, "hp_vision.py timed out (>210s)")

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[-1500:]
            raise HTTPException(502, f"hp_vision.py failed: {err}")

        body_md = proc.stdout
        stderr_tail = (proc.stderr or "").splitlines()
        cost_usd, latency_ms = _parse_hp_vision_stderr(stderr_tail)

        orders = parse_orders(body_md)

        # Persist uploads into the campaign's uploads/ dir keyed by turn.
        turn_n = _current_turn(state_dir) + 1
        ts_str = dt.datetime.now().strftime("%b %-d · %H:%M")
        if image_paths or xlsx_path is not None:
            persist_dir = state_dir / "uploads" / f"turn-{turn_n:02d}"
            persist_dir.mkdir(parents=True, exist_ok=True)
            for p in image_paths:
                shutil.copy2(p, persist_dir / p.name)
            if xlsx_path is not None:
                shutil.copy2(xlsx_path, persist_dir / xlsx_path.name)

        # Update turn-log.json (append + flip current flag).
        log = _turn_log(state_dir)
        for e in log:
            e["current"] = False
        intent_text = ""
        for sec in orders["sections"]:
            if sec["title"] == "Intent" and sec["body"]:
                intent_text = sec["body"][0]
                break
        new_entry = {
            "turn": turn_n,
            "time": ts_str,
            "model": _campaign_meta(state_dir)["model"].split("/")[-1],
            "status": status,
            "intent": intent_text,
            "current": True,
        }
        log.insert(0, new_entry)
        _write_json(state_dir / "turn-log.json", log)

        # Append a narrative entry to turn-log.md (keeps the human-
        # readable file in sync; the JSON is the UI source).
        _append_turn_log_md(state_dir / "turn-log.md", new_entry, body_md)

        # Persist parsed orders for hydration on next page load.
        _write_json(state_dir / "orders-latest.json", orders)

        # Bump tasks.json:current_turn so an external view (e.g. the
        # operator scripting around the state-dir) sees the same turn
        # number the UI does. Skip if tasks.json is malformed.
        tasks_path = state_dir / "tasks.json"
        if tasks_path.is_file():
            tasks = _read_json(tasks_path, None)
            if isinstance(tasks, dict):
                tasks["current_turn"] = turn_n
                _write_json(tasks_path, tasks)

        # Update campaign spend.
        meta_path = state_dir / "campaign.json"
        meta = _read_json(meta_path, {})
        meta["spend"] = round(float(meta.get("spend", 0.0)) + (cost_usd or 0.0), 6)
        if "slug" not in meta:
            meta["slug"] = state_dir.name
        if "name" not in meta:
            meta["name"] = state_dir.name.replace("-", " ").title()
        if "spend_budget" not in meta:
            meta["spend_budget"] = DEFAULT_BUDGET_USD
        if "model" not in meta:
            meta["model"] = DEFAULT_MODEL
        if "started" not in meta:
            meta["started"] = dt.date.today().isoformat()
        _write_json(meta_path, meta)

        return JSONResponse({
            "orders": orders,
            "campaign": _campaign_summary(state_dir),
            "turn_log_entry": new_entry,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
        })


def _parse_hp_vision_stderr(lines: list[str]) -> tuple[float | None, int | None]:
    """Pull cost_usd + latency_ms out of the hp_vision.py stderr header line.
    Header shape: '[backend=openrouter model=... mode=wargame-vision images=N latency_ms=M cost_usd=$0.0XYZ]'"""
    cost = None
    latency = None
    for line in lines:
        if not line.startswith("[backend="):
            continue
        m = re.search(r"latency_ms=(\d+)", line)
        if m:
            latency = int(m.group(1))
        m = re.search(r"cost_usd=\$(\d+\.\d+)", line)
        if m:
            cost = float(m.group(1))
    return cost, latency


def _append_turn_log_md(path: Path, entry: dict[str, Any], orders_md: str) -> None:
    """Append a fresh narrative section to turn-log.md."""
    intent = entry.get("intent", "").strip()
    block = (
        f"\n## Turn {entry['turn']} — {entry['time']} (model: {entry['model']})\n\n"
        f"**Status:** {entry['status']}\n\n"
        f"**Intent:** {intent}\n\n"
        f"**Orders (verbatim):**\n\n"
        + "\n".join(f"> {ln}" for ln in orders_md.strip().splitlines())
        + "\n\n---\n"
    )
    if not path.is_file():
        path.write_text("# Turn log\n\n---\n")
    with path.open("a") as f:
        f.write(block)
