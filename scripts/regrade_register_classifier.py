#!/usr/bin/env python3
"""Re-score a saved register-classifier eval artifact with the current grader.

Use after editing the regex patterns in v027_register_classifier_eval.py to
verify before/after pass counts without re-running the model. Reads the
artifact's per-probe responses, re-grades them with the current grader,
and prints / writes a comparison.

Usage:
  python3 scripts/regrade_register_classifier.py \
      data/eval-register-classifier-hammerstein-7b-v029-1-2026-05-25.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Import the grader from the canonical eval script
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from v027_register_classifier_eval import grade_response, PROBES  # noqa: E402


def regrade_artifact(artifact_path: Path) -> dict:
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    probes_by_id = {p["id"]: p for p in PROBES}

    out_per_probe = []
    total_passes_before = 0
    total_passes_after = 0
    total_runs = 0
    by_reg_before = {"audit": [0, 0], "explanation": [0, 0]}
    by_reg_after = {"audit": [0, 0], "explanation": [0, 0]}

    for probe in data["per_probe"]:
        probe_def = probes_by_id.get(probe["probe_id"])
        if probe_def is None:
            continue
        regraded_runs = []
        passes_before = 0
        passes_after = 0
        for run in probe["runs"]:
            if "error" in run:
                regraded_runs.append(run)
                continue
            text = run.get("response", "")
            before = bool(run.get("passes"))
            new_flags = grade_response(probe_def, text)
            after = bool(new_flags.get("passes"))
            regraded_runs.append({
                "run": run.get("run"),
                "before": before,
                "after": after,
                "flipped": (before != after),
                "response": text,
                "new_flags": {
                    "quadrant_hits": new_flags.get("quadrant_hits"),
                    "definition_marker_hits": new_flags.get("definition_marker_hits"),
                    "audit_apply_hits": new_flags.get("audit_apply_hits"),
                },
            })
            passes_before += int(before)
            passes_after += int(after)
            total_passes_before += int(before)
            total_passes_after += int(after)
            total_runs += 1
            reg = probe["register"]
            by_reg_before[reg][0] += int(before)
            by_reg_before[reg][1] += 1
            by_reg_after[reg][0] += int(after)
            by_reg_after[reg][1] += 1

        out_per_probe.append({
            "probe_id": probe["probe_id"],
            "register": probe["register"],
            "passes_before": passes_before,
            "passes_after": passes_after,
            "total_runs": probe["total_runs"],
            "runs": regraded_runs,
        })

    return {
        "artifact": str(artifact_path),
        "model": data.get("model"),
        "total_runs": total_runs,
        "total_passes_before": total_passes_before,
        "total_passes_after": total_passes_after,
        "by_register_before": by_reg_before,
        "by_register_after": by_reg_after,
        "per_probe": out_per_probe,
    }


def print_report(report: dict) -> None:
    print(f"=== regrade — {report['model']} ===")
    print(f"  artifact: {report['artifact']}")
    print(f"  total:    before {report['total_passes_before']}/{report['total_runs']}  "
          f"after {report['total_passes_after']}/{report['total_runs']}")
    print("  by register:")
    for reg in ("audit", "explanation"):
        b = report["by_register_before"][reg]
        a = report["by_register_after"][reg]
        print(f"    {reg:12s}  before {b[0]}/{b[1]}  after {a[0]}/{a[1]}")
    print()
    print("  per probe:")
    header = f"    {'probe':40s}  {'reg':12s}  before  after  flipped"
    print(header)
    print("    " + "-" * (len(header) - 4))
    for p in report["per_probe"]:
        flipped = sum(1 for r in p["runs"] if r.get("flipped"))
        print(f"    {p['probe_id']:40s}  {p['register']:12s}  "
              f"{p['passes_before']:>3d}/{p['total_runs']:<2d}   "
              f"{p['passes_after']:>3d}/{p['total_runs']:<2d}   {flipped}")

    # Flag flipped-to-fail (regressions) if any
    regressions = []
    for p in report["per_probe"]:
        for r in p["runs"]:
            if r.get("before") and not r.get("after"):
                regressions.append((p["probe_id"], r.get("run"), r.get("response", "")[:140]))
    if regressions:
        print()
        print("  REGRESSIONS (was pass, now fail):")
        for pid, run, resp in regressions:
            print(f"    {pid} run={run}: {resp}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact", help="Path to eval-register-classifier-*.json")
    ap.add_argument("--out", default=None,
                    help="Optional path to write regrade JSON to")
    args = ap.parse_args()

    path = Path(args.artifact)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2
    report = regrade_artifact(path)
    print_report(report)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        print(f"\n  regrade JSON: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
