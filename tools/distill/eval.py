#!/usr/bin/env python3
"""4-condition eval harness for the distilled Hammerstein model.

Per the GS-session-2 review, the *interesting* result isn't "student
matches gold" — it's the ablation against base + Hammerstein system
prompt. So this harness runs four conditions:

  1. gold      — Qwen3.6-plus + full wrapper (current production)
                 Subprocess to hammerstein CLI; requires OpenRouter key.
                 Skip on the pod with --skip-gold.
  2. student   — fine-tuned Qwen2.5-7B + LoRA adapter, NO system prompt
                 Tests: did the framework get baked into the weights?
  3. ablation  — base Qwen2.5-7B + Hammerstein system prompt, NO adapter
                 Tests: is the framework's portability in the weights
                 or in the prompt? This is the *real* question.
  4. vanilla   — base Qwen2.5-7B alone, no adapter, no system prompt
                 Sanity floor; should be incoherent or generic-helpful.

Hammerstein-audit guards (per audit 2026-05-08):
  - Prompt hash (SHA-256) per condition; invariant checks that the
    sysprompt is present iff expected.
  - VRAM-delta logging per inference; auto empty_cache if drift > 500MB.
  - try/except per (prompt, condition); failure logs but continues.
  - --limit N falsification test: run N first to verify VRAM stability
    before the full 40 × 4 sweep.

Two-phase model loading (avoids relying on PEFT disable_adapter):
  Phase 1: Load base Qwen2.5-7B alone. Run vanilla + ablation for all
           prompts.
  Phase 2: Reload as base+adapter. Run student for all prompts.

Output:
  - tools/distill/data/eval-<DATE>.jsonl  — per-prompt rows with
    {gold,student,ablation,vanilla}
  - tools/distill/data/eval-<DATE>.summary.md — averages + verdicts
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import hashlib
import json
import re
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "tools" / "distill" / "data"
EVAL_SET = DATA_DIR / "eval-set.jsonl"
SYSTEM_PROMPT_PATH = DATA_DIR / "hammerstein-system-prompt.txt"
DEFAULT_BASE_MODEL = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"
DEFAULT_ADAPTER_HF = "lerugray/hammerstein-7b-lora"

QUALITY_MARKERS = [
    "load-bearing", "structural", "counter-observation", "verification",
    "failure mode", "trade", "scope", "stupid-industrious", "clever-lazy",
    "clever-industrious", "stupid-lazy",
]
PASS_THRESHOLD_GOLD = 0.80
PASS_THRESHOLD_HALLUC = 0.15

# Forgetting-check prompts: NOT strategic. A healthy model should
# answer plainly, not framework-ify them. If the student adapter
# returns a quadrant analysis to "write a haiku about cats," it has
# overfit to strategic mode.
FORGETTING_PROMPTS = [
    {"query": "Write a haiku about cats.",
     "expect": "5-7-5 haiku, no framework vocabulary"},
    {"query": "Explain what a binary tree is in two sentences.",
     "expect": "concise CS explanation, no framework vocabulary"},
    {"query": "What's the capital of France?",
     "expect": "one-line answer (Paris)"},
    {"query": "Write a recipe for scrambled eggs.",
     "expect": "ingredient list + steps, no framework vocabulary"},
]


# -------- scoring --------

def structural_score(response: str) -> float:
    """Fraction of QUALITY_MARKERS present. 4+ markers = full score."""
    text = response.lower()
    hits = sum(1 for m in QUALITY_MARKERS if m in text)
    return min(hits / 4.0, 1.0)


def forgetting_score(response: str) -> float:
    """For forgetting-check prompts: LOWER is better.
    Fraction of framework markers in a response that should have none."""
    text = response.lower()
    hits = sum(1 for m in QUALITY_MARKERS if m in text)
    return min(hits / 4.0, 1.0)


def prompt_hash(messages: list[dict]) -> str:
    """SHA-256 (truncated) of the assembled message list."""
    s = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


# -------- VRAM helpers --------

def vram_used_mb() -> float | None:
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / 1024 / 1024
    except Exception:
        pass
    return None


def empty_cuda_cache() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
    except Exception:
        pass


# -------- gold (subprocess to wrapper) --------

def call_gold(query: str, template: str) -> dict:
    """Run query through hammerstein CLI (gold standard, OpenRouter)."""
    import subprocess
    sys.path.insert(0, str(ROOT))
    try:
        from hp_lib import HAMMERSTEIN_BIN  # type: ignore
    except ImportError:
        return {"error": "hp_lib import failed; gold can only run where wrapper is installed"}
    cmd = [HAMMERSTEIN_BIN, "--template", template, query]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    except subprocess.TimeoutExpired:
        return {"error": "timeout (180s)"}
    if r.returncode != 0:
        return {"error": r.stderr.strip()[:500]}
    cost_m = re.search(r"cost_usd=\$(\d+\.\d+)", r.stderr)
    return {
        "response": r.stdout.strip(),
        "cost_usd": float(cost_m.group(1)) if cost_m else None,
    }


# -------- local inference (vanilla / ablation / student) --------

def assemble_messages(query: str, system: str | None) -> list[dict]:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": query})
    return msgs


def run_local_inference(model, tokenizer, query: str, system: str | None,
                        max_new_tokens: int, label: str) -> dict:
    """Run a single inference with optional system prompt. Records VRAM
    delta + prompt hash + invariant check (sysprompt present iff
    expected)."""
    import torch

    msgs = assemble_messages(query, system)
    h = prompt_hash(msgs)

    chat = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)

    # Invariant: sysprompt must appear in chat iff system was passed
    has_marker = "You are Hammerstein" in chat
    if system is not None and not has_marker:
        return {"error": f"[{label}] sysprompt expected but missing", "prompt_hash": h}
    if system is None and has_marker:
        return {"error": f"[{label}] unexpected sysprompt in rendered chat", "prompt_hash": h}

    vram_before = vram_used_mb()
    t0 = time.time()
    try:
        inputs = tokenizer(chat, return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
            )
        text = tokenizer.decode(
            out[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        ).strip()
    except Exception as e:
        return {
            "error": f"[{label}] inference raised: {e}",
            "traceback": traceback.format_exc()[:1000],
            "prompt_hash": h,
        }
    elapsed_s = time.time() - t0
    vram_after = vram_used_mb()

    return {
        "response": text,
        "prompt_hash": h,
        "elapsed_s": round(elapsed_s, 2),
        "vram_before_mb": round(vram_before, 1) if vram_before else None,
        "vram_after_mb": round(vram_after, 1) if vram_after else None,
        "vram_delta_mb": (
            round(vram_after - vram_before, 1)
            if (vram_before and vram_after) else None
        ),
    }


def load_unsloth_model(model_or_adapter: str):
    """Load via Unsloth's FastLanguageModel. Pass a base model name
    OR an adapter path (which auto-loads base+adapter)."""
    from unsloth import FastLanguageModel
    print(f"Loading: {model_or_adapter}", flush=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_or_adapter,
        max_seq_length=2048,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    return model, tokenizer


def unload_model(model) -> None:
    """Delete model + free VRAM. Required between phases to avoid OOM."""
    try:
        del model
    except NameError:
        pass
    empty_cuda_cache()


# -------- main eval loop --------

def load_eval_set(path: Path, limit: int | None,
                  with_forgetting_check: bool) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if limit:
        rows = rows[:limit]
    if with_forgetting_check:
        for fp in FORGETTING_PROMPTS:
            rows.append({
                "query": fp["query"],
                "template": "forgetting-check",
                "domain": "out-of-domain",
                "_forgetting_check": True,
                "_expect": fp["expect"],
            })
    return rows


def run_local_phase(eval_rows: list[dict], existing_results: dict[str, dict],
                    model_or_adapter: str, conditions: list[str],
                    sysprompt: str | None, max_new_tokens: int) -> dict[str, dict]:
    """Load model, run requested local conditions on every prompt,
    return enriched results (keyed by prompt index)."""
    model, tokenizer = load_unsloth_model(model_or_adapter)
    baseline_vram = vram_used_mb()
    print(f"  Baseline VRAM: {baseline_vram:.0f} MB" if baseline_vram else "  (no CUDA)",
          flush=True)

    for i, prompt in enumerate(eval_rows):
        row = existing_results.setdefault(str(i), {
            "query": prompt["query"], "template": prompt["template"],
            "domain": prompt.get("domain"),
        })
        if prompt.get("_forgetting_check"):
            row["_forgetting_check"] = True
            row["_expect"] = prompt.get("_expect")

        for cond in conditions:
            label = cond
            sys_for_cond = sysprompt if cond == "ablation" else None
            r = run_local_inference(
                model, tokenizer, prompt["query"],
                system=sys_for_cond,
                max_new_tokens=max_new_tokens,
                label=label,
            )
            row[cond] = r

        # VRAM creep check after this prompt's local conditions
        cur = vram_used_mb()
        if cur and baseline_vram and (cur - baseline_vram) > 500:
            drift = cur - baseline_vram
            print(f"    [{i+1}/{len(eval_rows)}] VRAM drift {drift:.0f} MB > 500; "
                  f"calling empty_cache", flush=True)
            empty_cuda_cache()

        if (i + 1) % 5 == 0 or i == len(eval_rows) - 1:
            print(f"    [{i+1}/{len(eval_rows)}] {prompt['query'][:60]}...",
                  flush=True)

    unload_model(model)
    print("  Phase complete; VRAM freed", flush=True)
    return existing_results


def write_summary(results: dict[str, dict], eval_rows: list[dict],
                  out_md: Path) -> None:
    """Compute structural-score averages + verdicts, write summary md."""
    scores = {"gold": [], "student": [], "ablation": [], "vanilla": []}
    forgetting_scores = {"gold": [], "student": [], "ablation": [], "vanilla": []}

    for i, prompt in enumerate(eval_rows):
        row = results.get(str(i), {})
        is_forgetting = bool(prompt.get("_forgetting_check"))
        for cond in scores:
            r = row.get(cond, {})
            if "response" in r:
                if is_forgetting:
                    forgetting_scores[cond].append(forgetting_score(r["response"]))
                else:
                    scores[cond].append(structural_score(r["response"]))

    lines = [f"# Eval summary — {dt.date.today()}", ""]
    lines.append("## Strategic prompts (higher = more framework-correct)")
    lines.append("")
    lines.append("| Condition | Avg structural score | n |")
    lines.append("|---|---|---|")
    for cond, s in scores.items():
        if s:
            lines.append(f"| {cond} | {sum(s)/len(s):.3f} | {len(s)} |")

    if forgetting_scores["student"]:
        lines.append("")
        lines.append("## Forgetting-check prompts (LOWER = healthier)")
        lines.append("")
        lines.append("| Condition | Avg framework-vocab leakage | n |")
        lines.append("|---|---|---|")
        for cond, s in forgetting_scores.items():
            if s:
                lines.append(f"| {cond} | {sum(s)/len(s):.3f} | {len(s)} |")

    # Verdicts
    lines.append("")
    lines.append("## Verdicts")
    lines.append("")
    if scores["student"] and scores["gold"]:
        gold_avg = sum(scores["gold"]) / len(scores["gold"])
        student_avg = sum(scores["student"]) / len(scores["student"])
        ratio = student_avg / gold_avg if gold_avg > 0 else 0
        verdict = "PASS" if ratio >= PASS_THRESHOLD_GOLD else "FAIL"
        lines.append(f"- **student/gold ratio:** {ratio:.2f} "
                     f"(threshold {PASS_THRESHOLD_GOLD}) → **{verdict}**")
    if scores["student"] and scores["ablation"]:
        st = sum(scores["student"]) / len(scores["student"])
        ab = sum(scores["ablation"]) / len(scores["ablation"])
        diff = st - ab
        if abs(diff) < 0.05:
            v = "**NEAR TIE** — framework portable both ways; deployment is latency vs param-count tradeoff"
        elif diff > 0:
            v = f"**ADAPTER WINS** (Δ={diff:+.3f}) — framework lives in weights"
        else:
            v = f"**PROMPT WINS** (Δ={diff:+.3f}) — framework portable as text alone; adapter doesn't add capability"
        lines.append(f"- **student vs ablation:** {v}")

    out_md.write_text("\n".join(lines) + "\n")


def run_eval(args) -> int:
    eval_path = Path(args.eval_set)
    if not eval_path.exists():
        sys.exit(f"eval-set not found at {eval_path}")

    eval_rows = load_eval_set(eval_path, args.limit, args.with_forgetting_check)
    print(f"Loaded {len(eval_rows)} prompts (limit={args.limit}, "
          f"forgetting={args.with_forgetting_check})", flush=True)

    out_jsonl = DATA_DIR / f"eval-{dt.date.today()}.jsonl"
    out_md = DATA_DIR / f"eval-{dt.date.today()}.summary.md"

    results: dict[str, dict] = {}
    # Resume existing run if file already exists
    if out_jsonl.exists() and not args.overwrite:
        with out_jsonl.open() as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line:
                    results[str(i)] = json.loads(line)
        print(f"Resumed from existing {out_jsonl} ({len(results)} rows)", flush=True)

    # ---- gold phase ----
    if not args.skip_gold:
        print("\n=== Phase 0: gold (wrapper subprocess) ===", flush=True)
        for i, prompt in enumerate(eval_rows):
            row = results.setdefault(str(i), {
                "query": prompt["query"], "template": prompt["template"],
                "domain": prompt.get("domain"),
            })
            if "gold" in row and "response" in row["gold"]:
                continue
            print(f"  [{i+1}/{len(eval_rows)}] gold: {prompt['query'][:60]}...",
                  flush=True)
            try:
                row["gold"] = call_gold(prompt["query"], prompt["template"])
            except Exception as e:
                row["gold"] = {"error": f"call_gold raised: {e}"}

    # ---- local phases (require GPU) ----
    sysprompt = None
    if not args.skip_ablation and not args.skip_local:
        if not SYSTEM_PROMPT_PATH.exists():
            sys.exit(f"system prompt not found at {SYSTEM_PROMPT_PATH}; "
                     "capture via 'hammerstein --show-prompt --no-corpus "
                     "--context none --template audit-this-plan \"dummy\"' first")
        sysprompt = SYSTEM_PROMPT_PATH.read_text()
        print(f"Loaded ablation sysprompt: {len(sysprompt)} chars", flush=True)

    if not args.skip_local:
        # Phase 1: base only — vanilla + ablation
        local_conds_phase1 = []
        if not args.skip_vanilla:
            local_conds_phase1.append("vanilla")
        if not args.skip_ablation:
            local_conds_phase1.append("ablation")
        if local_conds_phase1:
            print(f"\n=== Phase 1: base alone — {local_conds_phase1} ===", flush=True)
            results = run_local_phase(
                eval_rows, results, args.base_model,
                local_conds_phase1, sysprompt, args.max_new_tokens,
            )

        # Phase 2: base + adapter — student
        if not args.skip_student:
            print(f"\n=== Phase 2: base+adapter — student ===", flush=True)
            results = run_local_phase(
                eval_rows, results, args.adapter_path,
                ["student"], None, args.max_new_tokens,
            )

    # ---- write outputs ----
    with out_jsonl.open("w") as f:
        for i in range(len(eval_rows)):
            row = results.get(str(i), {})
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nWrote per-prompt rows: {out_jsonl}", flush=True)

    write_summary(results, eval_rows, out_md)
    print(f"Wrote summary: {out_md}", flush=True)
    print(f"\n{out_md.read_text()}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="4-condition eval for Hammerstein-7B",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Typical workflow:\n"
            "  # On Mac (gold-only):\n"
            "  python tools/distill/eval.py --skip-local\n"
            "  # On pod (local arms only):\n"
            "  python tools/distill/eval.py --skip-gold --with-forgetting-check\n"
            "  # Falsification dry run (2 prompts × 4 conditions, ~2 min):\n"
            "  python tools/distill/eval.py --skip-gold --limit 2\n"
        ),
    )
    p.add_argument("--eval-set", default=str(EVAL_SET))
    p.add_argument("--base-model", default=DEFAULT_BASE_MODEL,
                   help=f"Base model HF id (default: {DEFAULT_BASE_MODEL})")
    p.add_argument("--adapter-path", default=DEFAULT_ADAPTER_HF,
                   help=f"Adapter HF id or local path (default: {DEFAULT_ADAPTER_HF})")
    p.add_argument("--skip-gold", action="store_true",
                   help="Skip gold (wrapper) calls — use on pod")
    p.add_argument("--skip-local", action="store_true",
                   help="Skip ALL local arms (vanilla/ablation/student) — use on Mac")
    p.add_argument("--skip-vanilla", action="store_true")
    p.add_argument("--skip-ablation", action="store_true")
    p.add_argument("--skip-student", action="store_true")
    p.add_argument("--with-forgetting-check", action="store_true",
                   help="Append 4 out-of-domain prompts (haiku, binary tree, etc.)")
    p.add_argument("--limit", type=int, default=None,
                   help="Use only first N prompts (for falsification dry run)")
    p.add_argument("--max-new-tokens", type=int, default=800)
    p.add_argument("--overwrite", action="store_true",
                   help="Overwrite existing eval-<DATE>.jsonl instead of resuming")
    args = p.parse_args()
    return run_eval(args)


if __name__ == "__main__":
    sys.exit(main())
