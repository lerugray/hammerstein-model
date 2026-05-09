"""hp_web backend — read-only dashboard over hp-calls.jsonl + hp-metrics.jsonl.

Single write action: POST /api/conclusion-changed flips the `conclusion_changed`
field for one metric row, identified by timestamp. The CLI stays the input
surface for everything else.

Run: python -m web.backend.server  (or via launch.sh at repo root)
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from hp_lib import HP_LOG, HP_METRICS, MAIN_LOG, read_jsonl  # noqa: E402

DIST_DIR = REPO_ROOT / "web" / "frontend" / "dist"

WINDOW_DAYS = 7
COST_RATIO_ABORT = 1.5
COST_RATIO_EXTEND = COST_RATIO_ABORT * 0.9
LAST_N_FOR_CONCLUSION = 5
CONCLUSION_CHANGED_MIN = 2
MAINTENANCE_BUDGET_HRS = 2.0


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")


def in_window(entry: dict, cutoff: dt.datetime) -> bool:
    ts = entry.get("timestamp")
    if not ts:
        return False
    try:
        return parse_ts(ts) >= cutoff
    except ValueError:
        return False


def avg_cost(entries: list[dict]) -> float | None:
    costs = [e["cost_usd"] for e in entries if isinstance(e.get("cost_usd"), (int, float))]
    return sum(costs) / len(costs) if costs else None


def compute_status() -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=WINDOW_DAYS)

    hp_metrics = read_jsonl(HP_METRICS)
    main_log = read_jsonl(MAIN_LOG)
    hp_window = [e for e in hp_metrics if in_window(e, cutoff)]
    main_window = [e for e in main_log if in_window(e, cutoff)]

    issues: list[str] = []
    warnings: list[str] = []
    gates: list[dict[str, Any]] = []

    hp_avg = avg_cost(hp_window)
    base_avg = avg_cost(main_window)
    if hp_avg and base_avg and base_avg > 0:
        ratio = hp_avg / base_avg
        gate = {
            "name": "cost_ratio",
            "value": round(ratio, 3),
            "threshold": COST_RATIO_ABORT,
            "detail": f"hp ${hp_avg:.4f} vs baseline ${base_avg:.4f}",
        }
        if ratio > COST_RATIO_ABORT:
            gate["status"] = "abort"
            issues.append(f"cost ratio {ratio:.2f}× > {COST_RATIO_ABORT}× (hp ${hp_avg:.4f} vs base ${base_avg:.4f})")
        elif ratio > COST_RATIO_EXTEND:
            gate["status"] = "warn"
            warnings.append(f"cost ratio {ratio:.2f}× near {COST_RATIO_ABORT}× threshold")
        else:
            gate["status"] = "ok"
        gates.append(gate)
    else:
        gates.append({
            "name": "cost_ratio",
            "value": None,
            "threshold": COST_RATIO_ABORT,
            "status": "unknown",
            "detail": "insufficient data (need ≥1 row in each log within window)",
        })
        warnings.append("insufficient data for cost-ratio gate")

    last_n = hp_metrics[-LAST_N_FOR_CONCLUSION:]
    if len(last_n) < LAST_N_FOR_CONCLUSION:
        gates.append({
            "name": "conclusion_changed",
            "value": sum(1 for e in last_n if e.get("conclusion_changed") is True),
            "threshold": CONCLUSION_CHANGED_MIN,
            "status": "unknown",
            "detail": f"only {len(last_n)}/{LAST_N_FOR_CONCLUSION} hp calls logged",
        })
        warnings.append(f"only {len(last_n)}/{LAST_N_FOR_CONCLUSION} hp calls logged; conclusion-changed gate not yet enforceable")
    else:
        changed = sum(1 for e in last_n if e.get("conclusion_changed") is True)
        gate = {
            "name": "conclusion_changed",
            "value": changed,
            "threshold": CONCLUSION_CHANGED_MIN,
            "detail": f"{changed}/{LAST_N_FOR_CONCLUSION} of last hp calls had conclusion_changed=True",
        }
        if changed < CONCLUSION_CHANGED_MIN:
            gate["status"] = "abort"
            issues.append(f"only {changed}/{LAST_N_FOR_CONCLUSION} recent hp calls had conclusion_changed=True")
        elif changed == CONCLUSION_CHANGED_MIN:
            gate["status"] = "warn"
            warnings.append(f"conclusion_changed at minimum threshold ({changed}/{LAST_N_FOR_CONCLUSION})")
        else:
            gate["status"] = "ok"
        gates.append(gate)

    maint_hrs = sum(e.get("maintenance_hours", 0) or 0 for e in hp_window)
    gate = {
        "name": "maintenance_hours",
        "value": round(maint_hrs, 2),
        "threshold": MAINTENANCE_BUDGET_HRS,
        "detail": f"{maint_hrs:.1f}h of {MAINTENANCE_BUDGET_HRS}h budget used in last {WINDOW_DAYS}d",
    }
    if maint_hrs > MAINTENANCE_BUDGET_HRS:
        gate["status"] = "abort"
        issues.append(f"maintenance hours in last {WINDOW_DAYS}d: {maint_hrs:.1f} > {MAINTENANCE_BUDGET_HRS}")
    elif maint_hrs > MAINTENANCE_BUDGET_HRS * 0.9:
        gate["status"] = "warn"
        warnings.append(f"maintenance hours {maint_hrs:.1f}h within 10% of budget")
    else:
        gate["status"] = "ok"
    gates.append(gate)

    if issues:
        verdict = "ABORT"
    elif warnings:
        verdict = "EXTEND"
    else:
        verdict = "CONTINUE"

    return {
        "verdict": verdict,
        "window_days": WINDOW_DAYS,
        "hp_calls_in_window": len(hp_window),
        "baseline_calls_in_window": len(main_window),
        "hp_avg_cost": hp_avg,
        "baseline_avg_cost": base_avg,
        "gates": gates,
        "issues": issues,
        "warnings": warnings,
    }


def normalize_call(c: dict, m: dict) -> dict:
    """Shape `hp.py` (audit) and `hp_vision.py` (wargame-vision) rows into a
    single contract for the frontend. The two writers share hp-calls.jsonl /
    hp-metrics.jsonl but diverge on field names (template vs model;
    preamble_tokens vs preamble_text_tokens) and which fields exist
    (corpus IDs are audit-only; images / xlsx are vision-only)."""
    kind = "vision" if c.get("mode") == "wargame-vision" else "audit"
    if kind == "vision":
        label = c.get("model", "")
        tokens = c.get("preamble_text_tokens") or m.get("preamble_tokens") or 0
    else:
        label = c.get("template", "")
        tokens = c.get("preamble_tokens") or m.get("preamble_tokens") or 0

    cost = c.get("cost_usd")
    if cost is None:
        cost = m.get("cost_usd")
    if cost is None and isinstance(c.get("usage"), dict):
        cost = c["usage"].get("cost")

    return {
        "timestamp": c.get("timestamp"),
        "kind": kind,
        "label": label,
        "query": c.get("query", ""),
        "response": c.get("response", ""),
        "tokens": tokens,
        "cost_usd": cost,
        "latency_ms": c.get("latency_ms"),
        "wrapper_elapsed_ms": c.get("wrapper_elapsed_ms"),
        "conclusion_changed": m.get("conclusion_changed"),
        "exit_code": m.get("exit_code"),
        # audit-only
        "template": c.get("template"),
        "new_query_corpus_ids": c.get("new_query_corpus_ids", []),
        "matched_prior_corpus_ids": c.get("matched_prior_corpus_ids", []),
        "injected_prior_count": c.get("injected_prior_count"),
        # vision-only
        "model": c.get("model"),
        "state_dir": c.get("state_dir"),
        "images": c.get("images", []),
        "xlsx": c.get("xlsx", []),
        "image_count": m.get("image_count"),
        "xlsx_count": m.get("xlsx_count"),
    }


def load_calls() -> list[dict]:
    """Join hp-calls + hp-metrics on timestamp. Calls is the long row, metrics
    holds conclusion_changed and exit_code. Indexed-by-timestamp join (1:1
    append pattern from hp.py + hp_vision.py)."""
    calls = read_jsonl(HP_LOG)
    metrics = {m.get("timestamp"): m for m in read_jsonl(HP_METRICS)}
    return [normalize_call(c, metrics.get(c.get("timestamp"), {})) for c in calls]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="hp-web", lifespan=lifespan)


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    return compute_status()


@app.get("/api/calls")
def get_calls(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    rows = load_calls()
    rows.reverse()  # newest first for the table
    total = len(rows)
    sliced = rows[offset : offset + limit]
    return {"total": total, "limit": limit, "offset": offset, "rows": sliced}


@app.get("/api/calls/{timestamp}")
def get_call_detail(timestamp: str) -> dict[str, Any]:
    for row in load_calls():
        if row.get("timestamp") == timestamp:
            return row
    raise HTTPException(404, f"call {timestamp} not found")


class ToggleBody(BaseModel):
    timestamp: str
    conclusion_changed: bool | None


@app.post("/api/conclusion-changed")
def set_conclusion_changed(body: ToggleBody) -> dict[str, Any]:
    """Atomic rewrite of hp-metrics.jsonl with the toggle flipped on the
    matching timestamp. Uses fcntl.flock so concurrent hp.py appends and
    web toggles can't corrupt the file."""
    if not HP_METRICS.exists():
        raise HTTPException(404, "hp-metrics.jsonl missing")

    with HP_METRICS.open("r+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            rows: list[dict] = []
            found = False
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("timestamp") == body.timestamp:
                    obj["conclusion_changed"] = body.conclusion_changed
                    found = True
                rows.append(obj)
            if not found:
                raise HTTPException(404, f"timestamp {body.timestamp} not in metrics")
            f.seek(0)
            f.truncate()
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    return {"ok": True, "timestamp": body.timestamp, "conclusion_changed": body.conclusion_changed}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "hp_log_exists": HP_LOG.exists(),
        "hp_metrics_exists": HP_METRICS.exists(),
        "main_log_exists": MAIN_LOG.exists(),
    }


if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        target = DIST_DIR / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(DIST_DIR / "index.html")
else:
    @app.get("/")
    def root():
        return JSONResponse({
            "hint": "frontend not built — run `cd web/frontend && npm run build`, or use `npm run dev` on port 5173",
            "api": ["/api/status", "/api/calls", "/api/calls/{timestamp}", "/api/conclusion-changed", "/api/health"],
        })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
