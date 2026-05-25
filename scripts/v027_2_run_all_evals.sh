#!/bin/bash
# v0.2.7.2 — drive all evals against hammerstein-7b-v027-2.
set -e
cd "$(dirname "$0")/.."

MODEL=hammerstein-7b-v027-2
RUNS=2

echo "=== v0.2.7.2 eval driver ==="
echo "Model: $MODEL"
echo "Runs:  $RUNS"
date
echo ""

run_eval() {
    local name=$1; shift
    echo ""
    echo "###################### $name ######################"
    "$@" 2>&1 | tail -40 || echo "  WARN: $name returned non-zero"
}

run_eval "anti-engagement"      python scripts/v027_anti_engagement_eval.py        --model $MODEL --runs $RUNS
run_eval "interface-aware-close" python scripts/v027_interface_aware_close_eval.py --model $MODEL --runs $RUNS
run_eval "symmetric-polemic"    python scripts/v027_symmetric_polemic_eval.py      --model $MODEL --runs $RUNS
run_eval "tool-use-judgment"    python scripts/v027_tool_use_judgment_eval.py      --model $MODEL --runs $RUNS
run_eval "anti-meta-leakage"    python scripts/v027_anti_meta_leakage_eval.py      --model $MODEL --runs $RUNS
run_eval "register-classifier"  python scripts/v027_register_classifier_eval.py    --model $MODEL --runs $RUNS

run_eval "voice-probe"          python scripts/v023_voice_probe.py                 --model $MODEL --runs 3
run_eval "self-state-probe"     python scripts/v023_self_state_probe.py            --model $MODEL --runs 3
run_eval "v2-failure-modes"     python scripts/v2_eval_failure_modes.py            --model $MODEL
run_eval "moral-weight"         python scripts/v026_moral_weight_eval.py           --model $MODEL --runs 2
run_eval "extraction-reliability" python scripts/v026_extraction_reliability_eval.py --model $MODEL --runs 2

echo ""
echo "=== v0.2.7.2 eval driver complete ==="
date
echo ""
echo "Eval artifacts in data/eval-*-${MODEL}-*.json"
