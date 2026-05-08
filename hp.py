#!/usr/bin/env python3
"""hp — Hammerstein Persistent. Stateful pull-based wrapper around the
existing hammerstein CLI. See DESIGN.md for the locked-in scope."""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

from hp_filter import filter_by_relevance
from hp_lib import (
    DEFAULT_MAX_PREAMBLE_TOKENS, DEFAULT_TEMPLATE, DEFAULT_TIMEOUT_S,
    HP_LOG, HP_METRICS, MAIN_LOG, PREAMBLE_FILE,
    append_jsonl, build_preamble, count_tokens,
    entry_ids, fetch_corpus_ids, quarantine_output,
    read_jsonl, read_project_state, resolve_state_dir, run_hammerstein,
    select_for_preamble, validate_cli_contract, validate_response,
)


def main() -> int:
    p = argparse.ArgumentParser(prog="hp", description="Hammerstein persistent wrapper")
    p.add_argument("query", help="Strategic-reasoning query.")
    p.add_argument("--template", default=DEFAULT_TEMPLATE,
                   help=f"Few-shot template. Default: {DEFAULT_TEMPLATE}.")
    p.add_argument("--max-preamble-tokens", type=int, default=DEFAULT_MAX_PREAMBLE_TOKENS)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    p.add_argument("--project", default=None, help="GS state dir name override.")
    p.add_argument("--state-dir", default=None,
                   help="Explicit project-state directory (any path on disk). "
                        "Overrides --project / GS auto-detect. Used by the wargame "
                        "extension so a wargame folder can ship outside GS.")
    p.add_argument("--no-memory", action="store_true",
                   help="Skip prior-audit retrieval (project state still injected). For ablation.")
    p.add_argument("--no-context", action="store_true",
                   help="Skip ALL preamble (no memory, no project state). Full ablation.")
    p.add_argument("--validate-cli", action="store_true", help="Run pre-flight only; exit.")
    p.add_argument("--dry-run", action="store_true", help="Build preamble + print stats, no inference.")
    args = p.parse_args()

    validate_cli_contract()
    if args.validate_cli:
        print("hp: CLI contract pre-flight passed.", file=sys.stderr)
        return 0

    t0 = dt.datetime.now(dt.timezone.utc)
    new_ids = set(fetch_corpus_ids(args.query, args.template))

    state_dir = None if args.no_context else resolve_state_dir(args.state_dir, args.project)
    state_overhead = count_tokens(read_project_state(state_dir)) if state_dir else 0
    audit_budget = max(0, args.max_preamble_tokens - state_overhead)

    if args.no_memory or args.no_context:
        selected, matched_ids = [], []
    else:
        all_entries = read_jsonl(MAIN_LOG) + read_jsonl(HP_LOG)
        matches = filter_by_relevance(all_entries, args.query)
        selected = select_for_preamble(matches, new_ids, audit_budget)
        matched_ids = sorted({i for e in selected for i in (entry_ids(e) & new_ids)})

    preamble = build_preamble(selected, new_ids, state_dir)
    preamble_tokens = count_tokens(preamble)
    if preamble_tokens > args.max_preamble_tokens:
        sys.exit(f"hp: preamble token cap exceeded ({preamble_tokens} > {args.max_preamble_tokens})")
    preamble_path = Path.cwd() / PREAMBLE_FILE
    preamble_path.write_text(preamble)

    if args.dry_run:
        print(f"hp: query corpus IDs: {sorted(new_ids)}", file=sys.stderr)
        print(f"hp: matched prior entries: {len(selected)}", file=sys.stderr)
        print(f"hp: matched corpus IDs: {matched_ids}", file=sys.stderr)
        print(f"hp: preamble tokens: {preamble_tokens}", file=sys.stderr)
        print(f"hp: preamble written to {preamble_path}", file=sys.stderr)
        return 0

    try:
        rc, stdout, stderr = run_hammerstein(args.query, args.template, preamble_path, args.timeout)
    except subprocess.TimeoutExpired:
        qpath = quarantine_output("", "", f"timeout after {args.timeout}s")
        sys.exit(f"hp: hammerstein timed out, quarantined at {qpath}")

    if rc != 0:
        qpath = quarantine_output(stdout, stderr, f"non-zero exit {rc}")
        sys.exit(f"hp: hammerstein returned {rc}, quarantined at {qpath}")

    ok, parsed = validate_response(stdout, stderr)
    if not ok:
        qpath = quarantine_output(stdout, stderr, parsed.get("error", "?"))
        sys.exit(f"hp: response validation failed ({parsed.get('error')}), quarantined at {qpath}")

    t1 = dt.datetime.now(dt.timezone.utc)
    elapsed_ms = int((t1 - t0).total_seconds() * 1000)
    ts_str = t0.strftime("%Y-%m-%dT%H:%M:%SZ")

    append_jsonl(HP_LOG, {
        "timestamp": ts_str,
        "query": args.query,
        "template": args.template,
        "new_query_corpus_ids": sorted(new_ids),
        "matched_prior_corpus_ids": matched_ids,
        "injected_prior_count": len(selected),
        "preamble_tokens": preamble_tokens,
        "response": parsed.get("body", ""),
        "latency_ms": parsed.get("latency_ms"),
        "cost_usd": parsed.get("cost_usd"),
        "wrapper_elapsed_ms": elapsed_ms,
        "retrieved_corpus_ids": sorted(new_ids),
    })
    append_jsonl(HP_METRICS, {
        "timestamp": ts_str,
        "preamble_tokens": preamble_tokens,
        "match_count": len(selected),
        "latency_ms": parsed.get("latency_ms"),
        "wrapper_elapsed_ms": elapsed_ms,
        "exit_code": 0,
        "cost_usd": parsed.get("cost_usd"),
        "conclusion_changed": None,
    })

    # Pass-through: header line on stderr, body on stdout (matches CLI shape).
    if parsed.get("header"):
        print(parsed["header"], file=sys.stderr)
    sys.stdout.write(stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
