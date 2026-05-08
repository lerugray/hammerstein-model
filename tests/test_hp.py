"""Phase 2 validation harness for hp. Exercises the structural Boolean
gates from DESIGN.md: token cap, JSONL integrity, schema validation,
subprocess timeout. The full end-to-end audit cycle is dogfooded
manually (Phase 3) — these tests verify the wrapper's invariants
without burning OpenRouter credits per CI run."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hp_lib import (  # noqa: E402
    DEFAULT_MAX_PREAMBLE_TOKENS, append_jsonl, build_preamble, count_tokens,
    entry_ids, filter_similar, format_entry, read_jsonl, select_for_preamble,
    validate_response,
)


def test_entry_ids_coerces_padded_strings():
    e = {"retrieved_corpus_ids": ["01", "02", "33"]}
    assert entry_ids(e) == {1, 2, 33}


def test_entry_ids_handles_missing_and_malformed():
    assert entry_ids({}) == set()
    assert entry_ids({"retrieved_corpus_ids": None}) == set()
    assert entry_ids({"retrieved_corpus_ids": ["01", "x", None, 7]}) == {1, 7}


def test_filter_similar_with_min_match_2():
    entries = [
        {"retrieved_corpus_ids": ["01", "02", "33"]},   # 2 matches
        {"retrieved_corpus_ids": ["01", "99", "98"]},   # 1 match
        {"retrieved_corpus_ids": ["50", "51", "52"]},   # 0 matches
    ]
    out = filter_similar(entries, {1, 2}, min_match=2)
    assert len(out) == 1
    assert entry_ids(out[0]) == {1, 2, 33}


def test_filter_similar_falls_back_to_min_match_1():
    entries = [{"retrieved_corpus_ids": ["01"]}]
    out = filter_similar(entries, {1, 99}, min_match=2)
    # No ≥2 matches, falls back to ≥1
    assert len(out) == 1


def test_select_for_preamble_respects_token_budget():
    """Crafted entries with large bodies; budget forces truncation."""
    entries = [
        {"timestamp": f"2026-05-0{i}T00:00:00Z",
         "retrieved_corpus_ids": ["01", "02"],
         "query": "x" * 1000,
         "response": "y" * 2000,
         "template": "audit-this-plan"}
        for i in range(1, 6)
    ]
    selected = select_for_preamble(entries, {1, 2}, max_tokens=500)
    total = sum(count_tokens(format_entry(e, {1, 2})) for e in selected)
    assert total <= 500


def test_build_preamble_with_no_state_dir():
    p = build_preamble([], {1}, None)
    assert "structurally-similar prior context" in p
    assert "Active project context" not in p


def test_read_project_state_is_noop_without_turn_log(tmp_path: Path):
    """The turn-log.md hook is a no-op cost when the file isn't present.
    Wargame extension preserves general-purpose behavior."""
    from hp_lib import read_project_state
    (tmp_path / "MISSION.md").write_text("# Test mission\n")
    out = read_project_state(tmp_path)
    assert "MISSION.md" in out
    assert "turn-log.md" not in out


def test_read_project_state_includes_turn_log_when_present(tmp_path: Path):
    """Wargame extension: turn-log.md auto-injects when present."""
    from hp_lib import read_project_state
    (tmp_path / "MISSION.md").write_text("# Rules\n")
    (tmp_path / "turn-log.md").write_text("## Turn 1\n- Red advances\n")
    out = read_project_state(tmp_path)
    assert "Red advances" in out
    assert "turn-log.md" in out


def test_validate_response_rejects_empty_stdout():
    ok, parsed = validate_response("", "[backend=x model=y template=z corpus=4 latency_ms=1 cost_usd=$0.01]")
    assert not ok
    assert "empty" in parsed["error"]


def test_validate_response_rejects_missing_header():
    ok, parsed = validate_response("body content", "no header here")
    assert not ok
    assert "header" in parsed["error"]


def test_validate_response_accepts_well_formed():
    stderr = "[backend=openrouter model=qwen/qwen3-x template=audit-this-plan corpus=4 latency_ms=12345 cost_usd=$0.00500]"
    ok, parsed = validate_response("body content", stderr)
    assert ok
    assert parsed["latency_ms"] == 12345
    assert parsed["cost_usd"] == 0.005
    assert parsed["body"] == "body content"


def test_jsonl_roundtrip(tmp_path: Path):
    log = tmp_path / "test.jsonl"
    entries = [{"a": 1}, {"b": [2, 3]}, {"c": "hello — world"}]
    for e in entries:
        append_jsonl(log, e)
    read_back = read_jsonl(log)
    assert read_back == entries


def test_jsonl_append_creates_parent_dirs(tmp_path: Path):
    log = tmp_path / "deep" / "dir" / "test.jsonl"
    append_jsonl(log, {"x": 1})
    assert log.exists()


def test_jsonl_skips_malformed_lines(tmp_path: Path):
    log = tmp_path / "test.jsonl"
    log.write_text('{"a":1}\nnot json\n{"b":2}\n')
    assert read_jsonl(log) == [{"a": 1}, {"b": 2}]


def test_count_tokens_returns_positive_int():
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0


def test_default_max_preamble_tokens_under_qwen_4k_ceiling():
    """Tokenizer drift guard: cl100k proxy at 3500 leaves margin for the
    actual Qwen tokenizer, which DESIGN.md notes is ~10-15% off."""
    assert DEFAULT_MAX_PREAMBLE_TOKENS <= 3500


@pytest.mark.live
def test_cli_contract_pre_flight_passes_against_real_cli():
    """Live test: requires hammerstein on PATH + OPENROUTER_API_KEY.
    Run with `pytest -m live`. Skipped by default."""
    from hp_lib import validate_cli_contract
    validate_cli_contract()  # exits on failure
