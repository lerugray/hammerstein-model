#!/usr/bin/env python3
"""hp-status — mechanical Phase 3 gate.

Reads ~/.hammerstein/logs/hp-metrics.jsonl and prints one of:
  ABORT    — at least one threshold breached
  EXTEND   — within 10% of any threshold (warn but don't kill)
  CONTINUE — all thresholds pass

Thresholds (per DESIGN.md):
  - rolling 7-day avg cost_usd > 1.5× plain-hammerstein 7-day avg cost
    (the wrapper's cost-per-call leaking via preamble bloat)
  - < 2 of last 5 hp calls have conclusion_changed=True (memory not
    earning weight; operator-stamped post-hoc)
  - cumulative maintenance hours in last 7 days > 2 (operator-logged
    via 'maintenance_hours' field in metric rows; clever-lazy threshold)

The operator does not get a vote. The gate is deterministic.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from hp_lib import HP_METRICS, MAIN_LOG, read_jsonl

WINDOW_DAYS = 7
COST_RATIO_ABORT = 1.5
COST_RATIO_EXTEND = 1.5 * 0.9  # within 10%
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


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=WINDOW_DAYS)

    hp_metrics = read_jsonl(HP_METRICS)
    main_log = read_jsonl(MAIN_LOG)
    # Exclude hp's own subprocess calls from the baseline so we compare like-for-like:
    # the baseline is plain-hammerstein usage WITHOUT injected preamble. The wrapper's
    # subprocess calls land in main_log too, but they have non-empty `--context-file`
    # mode. The existing log doesn't tag those, so this is a known approximation:
    # the baseline drifts upward as the wrapper is dogfooded. Acknowledge in DESIGN.
    hp_window = [e for e in hp_metrics if in_window(e, cutoff)]
    main_window = [e for e in main_log if in_window(e, cutoff)]

    issues = []
    warnings = []

    # Gate 1: cost ratio
    hp_avg = avg_cost(hp_window)
    base_avg = avg_cost(main_window)
    if hp_avg and base_avg and base_avg > 0:
        ratio = hp_avg / base_avg
        if ratio > COST_RATIO_ABORT:
            issues.append(f"cost ratio {ratio:.2f}× > {COST_RATIO_ABORT}× (hp ${hp_avg:.4f} vs base ${base_avg:.4f})")
        elif ratio > COST_RATIO_EXTEND:
            warnings.append(f"cost ratio {ratio:.2f}× near {COST_RATIO_ABORT}× threshold")
    else:
        warnings.append("insufficient data for cost-ratio gate (need ≥1 row in each log within window)")

    # Gate 2: conclusion_changed in last N
    last_n = hp_metrics[-LAST_N_FOR_CONCLUSION:]
    if len(last_n) < LAST_N_FOR_CONCLUSION:
        warnings.append(f"only {len(last_n)}/{LAST_N_FOR_CONCLUSION} hp calls logged; conclusion-changed gate not yet enforceable")
    else:
        changed = sum(1 for e in last_n if e.get("conclusion_changed") is True)
        if changed < CONCLUSION_CHANGED_MIN:
            issues.append(f"only {changed}/{LAST_N_FOR_CONCLUSION} recent hp calls had conclusion_changed=True (need ≥{CONCLUSION_CHANGED_MIN}); memory not earning weight")
        elif changed == CONCLUSION_CHANGED_MIN:
            warnings.append(f"conclusion_changed at minimum threshold ({changed}/{LAST_N_FOR_CONCLUSION})")

    # Gate 3: maintenance hours
    maint_hrs = sum(e.get("maintenance_hours", 0) or 0 for e in hp_window)
    if maint_hrs > MAINTENANCE_BUDGET_HRS:
        issues.append(f"maintenance hours in last {WINDOW_DAYS}d: {maint_hrs:.1f} > {MAINTENANCE_BUDGET_HRS} budget")
    elif maint_hrs > MAINTENANCE_BUDGET_HRS * 0.9:
        warnings.append(f"maintenance hours {maint_hrs:.1f}h within 10% of {MAINTENANCE_BUDGET_HRS}h budget")

    # Print findings
    print(f"hp-status — window: last {WINDOW_DAYS} days")
    print(f"  hp calls in window: {len(hp_window)}")
    print(f"  baseline calls in window: {len(main_window)}")
    if hp_avg is not None:
        print(f"  hp avg cost: ${hp_avg:.4f}")
    if base_avg is not None:
        print(f"  baseline avg cost: ${base_avg:.4f}")
    if issues:
        print("\nIssues:")
        for i in issues:
            print(f"  - {i}")
    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  - {w}")

    if issues:
        print("\nVerdict: ABORT")
        return 2
    if warnings:
        print("\nVerdict: EXTEND")
        return 1
    print("\nVerdict: CONTINUE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
