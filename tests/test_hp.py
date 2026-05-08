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
from hp_filter import filter_by_relevance, relevance_score, tokenize  # noqa: E402
from hp_lib import (  # noqa: E402
    DEFAULT_MAX_PREAMBLE_TOKENS, append_jsonl, build_preamble, count_tokens,
    entry_ids, format_entry, read_jsonl, select_for_preamble, trim_turn_log,
    validate_response,
)


def test_entry_ids_coerces_padded_strings():
    e = {"retrieved_corpus_ids": ["01", "02", "33"]}
    assert entry_ids(e) == {1, 2, 33}


def test_entry_ids_handles_missing_and_malformed():
    assert entry_ids({}) == set()
    assert entry_ids({"retrieved_corpus_ids": None}) == set()
    assert entry_ids({"retrieved_corpus_ids": ["01", "x", None, 7]}) == {1, 7}


def test_tokenize_strips_stop_words_and_short_tokens():
    out = tokenize("Audit this plan for the TWAR PC dispatcher rebuild")
    # 'audit', 'plan', 'this', 'for', 'the' are stop words; 'PC' is < 3 chars
    assert "twar" in out
    assert "dispatcher" in out
    assert "rebuild" in out
    assert "audit" not in out
    assert "plan" not in out
    assert "the" not in out


def test_relevance_score_zero_for_no_overlap():
    import datetime as dt
    now = dt.datetime(2026, 5, 8, tzinfo=dt.timezone.utc)
    e = {"query": "completely unrelated content", "timestamp": "2026-05-08T00:00:00Z"}
    assert relevance_score(tokenize("TWAR dispatcher rebuild"), e, now) == 0.0


def test_relevance_score_decays_with_age():
    import datetime as dt
    now = dt.datetime(2026, 5, 8, tzinfo=dt.timezone.utc)
    fresh = {"query": "TWAR dispatcher rebuild plan", "timestamp": "2026-05-08T00:00:00Z"}
    old = {"query": "TWAR dispatcher rebuild plan", "timestamp": "2026-04-15T00:00:00Z"}
    qt = tokenize("TWAR dispatcher rebuild plan")
    assert relevance_score(qt, fresh, now) > relevance_score(qt, old, now)


def test_filter_by_relevance_returns_score_sorted():
    """Tiny corpora trigger the rare-token threshold pathology; force
    rare_threshold=1.01 to count every token as 'rare' for the test."""
    import datetime as dt
    now = dt.datetime(2026, 5, 8, tzinfo=dt.timezone.utc)
    entries = [
        {"query": "TWAR dispatcher noise irrelevant", "timestamp": "2026-05-08T00:00:00Z"},
        {"query": "TWAR dispatcher rebuild plan exact", "timestamp": "2026-05-08T00:00:00Z"},
        {"query": "completely unrelated thing", "timestamp": "2026-05-08T00:00:00Z"},
    ]
    out = filter_by_relevance(entries, "TWAR dispatcher rebuild plan",
                              now=now, min_score=1.0, rare_threshold=1.01)
    assert len(out) == 2  # third is dropped (no overlap)
    assert "exact" in out[0]["query"]  # higher overlap ranks first


def test_filter_by_relevance_respects_top_k():
    import datetime as dt
    now = dt.datetime(2026, 5, 8, tzinfo=dt.timezone.utc)
    entries = [
        {"query": f"TWAR dispatcher rebuild plan match{i}", "timestamp": "2026-05-08T00:00:00Z"}
        for i in range(10)
    ]
    out = filter_by_relevance(entries, "TWAR dispatcher rebuild plan",
                              now=now, min_score=1.0, top_k=3, rare_threshold=1.01)
    assert len(out) == 3


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


def test_trim_turn_log_passes_short_logs_through():
    """If turn-log has fewer turns than `keep`, return unchanged."""
    text = "# header\n\n## Turn 1 — foo\nbody\n\n## Turn 2 — bar\nbody\n"
    assert trim_turn_log(text, keep=3) == text
    assert trim_turn_log("", keep=3) == ""


def test_trim_turn_log_keeps_first_n_when_over():
    """Spec: newest-on-top in turn-log.md, so 'first N' = N most recent."""
    text = (
        "# header\n\n"
        "## Turn 5\nfive\n\n"
        "## Turn 4\nfour\n\n"
        "## Turn 3\nthree\n\n"
        "## Turn 2\ntwo\n\n"
        "## Turn 1\none\n"
    )
    out = trim_turn_log(text, keep=2)
    assert "## Turn 5" in out
    assert "## Turn 4" in out
    assert "## Turn 3" not in out
    assert "## Turn 2" not in out
    assert "## Turn 1" not in out
    assert "earlier turn(s) omitted" in out


def test_trim_turn_log_preserves_pre_turn_blurb():
    """The leading prose (## Setup, etc.) before the first ## Turn
    section stays in the preamble — it's not a turn snapshot."""
    text = (
        "# Turn log\n\nIntro prose.\n\n"
        "## Turn 3\nthree\n\n"
        "## Turn 2\ntwo\n\n"
        "## Turn 1\none\n"
    )
    out = trim_turn_log(text, keep=1)
    assert "Intro prose." in out
    assert "## Turn 3" in out
    assert "## Turn 2" not in out


@pytest.mark.live
def test_cli_contract_pre_flight_passes_against_real_cli():
    """Live test: requires hammerstein on PATH + OPENROUTER_API_KEY.
    Run with `pytest -m live`. Skipped by default."""
    from hp_lib import validate_cli_contract
    validate_cli_contract()  # exits on failure
