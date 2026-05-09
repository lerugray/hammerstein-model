"""Tests for normalize_call — the only non-trivial backend logic.

The web layer otherwise just reads JSONL + computes the same gates
as hp_status.py + does an atomic rewrite for the toggle. The shape
normalization is the load-bearing piece because hp.py and
hp_vision.py write to the same log with different schemas.

Run: cd web && .venv/bin/python -m pytest backend/test_normalize.py -q
"""

from __future__ import annotations

from web.backend.server import normalize_call


def test_audit_row_normalizes() -> None:
    call = {
        "timestamp": "2026-05-08T14:00:38Z",
        "query": "Audit this plan: rebuild the dispatcher",
        "template": "audit-this-plan",
        "new_query_corpus_ids": [18, 19],
        "matched_prior_corpus_ids": [18, 19],
        "injected_prior_count": 7,
        "preamble_tokens": 2765,
        "response": "...",
        "latency_ms": 67012,
        "cost_usd": 0.00817,
        "wrapper_elapsed_ms": 69822,
        "retrieved_corpus_ids": [18, 19],
    }
    metric = {"timestamp": "2026-05-08T14:00:38Z", "conclusion_changed": True, "exit_code": 0}
    out = normalize_call(call, metric)
    assert out["kind"] == "audit"
    assert out["label"] == "audit-this-plan"
    assert out["tokens"] == 2765
    assert out["cost_usd"] == 0.00817
    assert out["conclusion_changed"] is True
    assert out["matched_prior_corpus_ids"] == [18, 19]
    assert out["images"] == []
    assert out["xlsx"] == []


def test_vision_row_normalizes() -> None:
    call = {
        "timestamp": "2026-05-08T22:58:51Z",
        "mode": "wargame-vision",
        "query": "Just played Turn 3 …",
        "model": "anthropic/claude-sonnet-4.6",
        "state_dir": "wargame-example/",
        "images": ["/abs/path/board.jpg"],
        "xlsx": ["/abs/path/oob.xlsx"],
        "preamble_text_tokens": 7965,
        "response": "## Situation\n…",
        "latency_ms": 10530,
        "usage": {"cost": 0.032454, "total_tokens": 9274},
        "cost_usd": None,
    }
    metric = {
        "timestamp": "2026-05-08T22:58:51Z",
        "mode": "wargame-vision",
        "preamble_tokens": 7965,
        "image_count": 1,
        "xlsx_count": 1,
        "cost_usd": 0.032454,
    }
    out = normalize_call(call, metric)
    assert out["kind"] == "vision"
    assert out["label"] == "anthropic/claude-sonnet-4.6"
    assert out["tokens"] == 7965
    assert out["cost_usd"] == 0.032454, "cost falls back to metrics row when calls row is null"
    assert out["images"] == ["/abs/path/board.jpg"]
    assert out["xlsx"] == ["/abs/path/oob.xlsx"]
    assert out["state_dir"] == "wargame-example/"
    assert out["image_count"] == 1


def test_vision_row_cost_falls_back_to_usage() -> None:
    """When both cost_usd fields are null, surface usage.cost."""
    call = {
        "timestamp": "x",
        "mode": "wargame-vision",
        "model": "m",
        "preamble_text_tokens": 100,
        "usage": {"cost": 0.005},
        "cost_usd": None,
    }
    out = normalize_call(call, {"timestamp": "x", "cost_usd": None})
    assert out["cost_usd"] == 0.005


def test_missing_metric_row() -> None:
    """If hp-metrics.jsonl lacks a row for a given timestamp, conclusion_changed
    surfaces as None (drives the unchecked switch state)."""
    call = {
        "timestamp": "x",
        "template": "t",
        "preamble_tokens": 1,
        "cost_usd": 0.001,
    }
    out = normalize_call(call, {})
    assert out["conclusion_changed"] is None
    assert out["exit_code"] is None
