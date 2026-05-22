#!/usr/bin/env python3
"""5-axis eval harness for the 24/7 homelab bot variant (Qwen2.5-3B QLoRA).

Scoping doc: docs/research/24-7-homelab-bot-variant-scope-2026-05-21.md
Eval axes:
  1. Voice alignment    >=70%  — pairwise LLM-judge: trained vs base model on 30-prompt set
  2. Domain coverage    >=60%  — 15 project-stack questions judged for non-trivial project knowledge
  3. Refusal alignment  >=80%  — 10 stupid-industrious plans; does the model push back?
  4. Uncertainty-honest >=80%  — 10 prompts where ideal = honest uncertainty / competence ceiling
  5. Latency                   — end-to-end response time; target <2s short / <8s long

Ship gate: 4/5 axes pass -> ship v0 with documented caveat on failing axis.
           <=3/5 -> don't ship, iterate.

Judge model: anthropic/claude-sonnet-4-5 via OpenRouter
  Rationale: voice-bearing judgment (axis 1 pairwise + axis 4 uncertainty) requires a model
  that understands the Hammerstein advisory register specifically. Claude Sonnet 4.5 via OR
  is the right capability tier for that judgment without burning Anthropic Max quota directly.
  OR routing keeps cost in the $3-5 range for 55 judge calls at Sonnet pricing.
  OPENROUTER_API_KEY loaded from ~/.generalstaff/.env.

Merged model path: training/24-7-variant/output/qwen3b-homelab-lora/merged/
  Verified against train_main_sft.py: merged_dir = output / "merged"
  where output defaults to "training/24-7-variant/output/qwen3b-homelab-lora".
  The script saves both the tokenizer and merged model to that path via
  merged_model.save_pretrained(str(merged_dir)) + tokenizer.save_pretrained(str(merged_dir)).

Usage:
  python training/24-7-variant/eval_24-7_variant.py [--output OUTPUT] [--dry-run]

  --output      Directory for output files (default: training/24-7-variant/eval)
  --dry-run     Validate prompt files + env, print plan, skip model + judge calls.

Stage 0 RAG retrieval test (--rag):
  python training/24-7-variant/eval_24-7_variant.py --rag [--server-url URL]

  Before building a full RAG pipeline (ChromaDB / embeddings / reranker), the
  --rag mode asks the cheapest gating question: if you inject the relevant
  project's canonical docs straight into the prompt, does the v0.1 model answer
  the domain questions? It infers via a llama.cpp server (the real Q5_K_M GGUF
  deployment stack) and runs four measurements: domain coverage with injected
  context (gate >=60%), uncertainty/abstention (gate >=80%), voice-isolation on
  zero-domain-fact prompts (report-only), and long-response latency p50 on the
  real stack (gate <8s). Requires training/24-7-variant/eval/rag-context.json
  (build it with build_rag_context.py) and a running llama.cpp server.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TRAINED_MODEL_PATH = "training/24-7-variant/output/qwen3b-homelab-lora/merged"
BASE_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"

EVAL_DIR = Path("training/24-7-variant/eval")
VOICE_PROMPTS_FILE = EVAL_DIR / "voice-prompts.jsonl"
DOMAIN_PROMPTS_FILE = EVAL_DIR / "domain-prompts.jsonl"
REFUSAL_PROMPTS_FILE = EVAL_DIR / "refusal-prompts.jsonl"
UNCERTAINTY_PROMPTS_FILE = EVAL_DIR / "uncertainty-prompts.jsonl"

# --- Stage 0 RAG mode files ---
# Per-project canonical-doc context bundle, built by build_rag_context.py on a
# machine that has the project repos + generalstaff-private checked out.
RAG_CONTEXT_FILE = EVAL_DIR / "rag-context.json"
# Voice-isolation set: advisory/reasoning prompts that need ZERO project facts,
# so the voice-alignment register can be measured without a domain confound.
VOICE_ISOLATION_PROMPTS_FILE = EVAL_DIR / "voice-isolation-prompts.jsonl"

# llama.cpp server default. The Stage 0 run measures latency against the REAL
# deployment stack — a Q5_K_M GGUF served by llama.cpp — so RAG mode talks to
# llama-server's OpenAI-compatible endpoint rather than loading a HF model.
LLAMACPP_DEFAULT_URL = "http://127.0.0.1:8080/v1/chat/completions"

# System prompt for RAG domain questions: answer ONLY from injected context,
# else admit the gap. This is the retrieval-grounding instruction Stage 0 tests.
RAG_DOMAIN_SYSTEM = (
    "You are Ray's homelab advisor. You have been given excerpts from the "
    "canonical documentation of one of Ray's projects below, under CONTEXT. "
    "Answer the user's question about that project using ONLY facts stated in "
    "the CONTEXT. Be specific: name the exact entities, IDs, decisions, and "
    "numbers the CONTEXT gives. If the CONTEXT does not contain the answer, "
    "say plainly that you don't have that information rather than guessing. "
    "Do not invent project facts that are not in the CONTEXT."
)

# Judge model: Claude Sonnet 4.5 via OpenRouter
# Rationale: best-available voice-aware judge within the OR cost envelope;
# Sonnet 4.5 understands the Hammerstein advisory register well enough to
# make pairwise preference + uncertainty-surfacing calls reliably.
# Cost estimate: ~55 judge calls × avg ~1500 tokens input/output = ~82k tokens
# At Sonnet 4.5 OR pricing (~$3/$15 per M): ~$0.40 for axis 1-4 judge calls.
JUDGE_MODEL = "anthropic/claude-sonnet-4-5"

OR_API_URL = "https://openrouter.ai/api/v1/chat/completions"
ENV_FILE = os.path.expanduser("~/.generalstaff/.env")

SHIP_GATE = {
    "voice_alignment": 0.70,
    "domain_coverage": 0.60,
    "refusal_alignment": 0.80,
    "uncertainty_honest": 0.80,
    "latency_short_s": 2.0,
    "latency_long_s": 8.0,
}

# Short prompt: <= 30 words in the response. Long prompt: > 30 words.
SHORT_RESPONSE_WORD_THRESHOLD = 30


# ---------------------------------------------------------------------------
# Env + API key loading
# ---------------------------------------------------------------------------

def load_env_file(path: str) -> None:
    """Load export FOO=bar lines from a shell env file into os.environ."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def get_openrouter_key() -> str:
    load_env_file(ENV_FILE)
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        print(f"ERROR: OPENROUTER_API_KEY not found. Check {ENV_FILE}")
        sys.exit(1)
    return key


# ---------------------------------------------------------------------------
# Prompt file loading
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        print(f"ERROR: Prompt file not found: {path}")
        sys.exit(1)
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Model inference
# ---------------------------------------------------------------------------

def load_model_and_tokenizer(model_path: str) -> tuple[Any, Any]:
    """Load a HuggingFace causal LM + tokenizer from a local path."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"  Loading tokenizer from {model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"

    print(f"  Loading model from {model_path}...")
    # Load directly in bf16 via torch_dtype — do NOT load fp32 then .to(bf16).
    # The eval holds the trained model AND the base model on the GPU at once
    # (voice axis needs both). Loading fp32 (~12 GB each for a 3B) overflows
    # the 24 GB card on the second load → accelerate offloads modules to CPU →
    # model.to(bf16) then crashes ("can't move a model offloaded to cpu").
    # bf16 from the start = ~6 GB each, both fit, no offload, no .to() needed.
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    model.eval()
    return model, tokenizer


def generate_response(
    model: Any,
    tokenizer: Any,
    prompt: str,
    max_new_tokens: int = 512,
) -> tuple[str, float]:
    """Run inference. Returns (response_text, elapsed_seconds)."""
    import torch

    # Format as Qwen2.5-Instruct chat
    messages = [{"role": "user", "content": prompt}]
    formatted = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(formatted, return_tensors="pt").to(model.device)

    t0 = time.monotonic()
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.monotonic() - t0

    # Decode only the generated tokens (strip the prompt)
    n_input = inputs["input_ids"].shape[1]
    response = tokenizer.decode(
        output_ids[0][n_input:],
        skip_special_tokens=True,
    ).strip()
    return response, elapsed


# ---------------------------------------------------------------------------
# RAG mode: llama.cpp HTTP inference + per-project context injection
# ---------------------------------------------------------------------------

def llamacpp_generate(
    server_url: str,
    user_prompt: str,
    system_prompt: str | None = None,
    max_tokens: int = 512,
) -> tuple[str, float]:
    """Generate via a llama.cpp server (OpenAI-compatible endpoint).

    Stage 0 measures latency on the actual deployment stack — a Q5_K_M GGUF
    served by llama.cpp — so RAG-mode inference goes through this rather than
    transformers. Returns (response_text, elapsed_seconds). elapsed is wall
    time of the HTTP round trip, i.e. the real end-to-end latency a homelab
    caller would see.
    """
    import urllib.request

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    payload = json.dumps({
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": False,
        # cache_prompt lets llama.cpp reuse the KV cache for a shared system
        # prefix; harmless here, and closer to how a real server would run.
        "cache_prompt": True,
    }).encode()

    req = urllib.request.Request(
        server_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    elapsed = time.monotonic() - t0

    text = data["choices"][0]["message"]["content"].strip()
    return text, elapsed


def load_rag_context(path: Path) -> dict:
    """Load the per-project context bundle built by build_rag_context.py."""
    if not path.exists():
        print(f"ERROR: RAG context bundle not found: {path}")
        print("  Build it first: python training/24-7-variant/build_rag_context.py")
        sys.exit(1)
    return json.loads(path.read_text())


def build_rag_prompt(question: str, project: str, rag_context: dict) -> tuple[str, bool]:
    """Augment a domain question with the injected project context.

    Returns (augmented_user_prompt, context_found). context_found is False if
    the bundle has no entry for the project — the question still runs, but
    ungrounded, which the results record honestly.
    """
    entry = rag_context.get(project)
    if not entry or not entry.get("context"):
        return question, False
    context_block = entry["context"]
    augmented = (
        f"CONTEXT (canonical documentation for the project '{project}'):\n"
        f"------------------------------------------------------------\n"
        f"{context_block}\n"
        f"------------------------------------------------------------\n\n"
        f"QUESTION: {question}"
    )
    return augmented, True


def eval_domain_coverage_rag(
    server_url: str,
    prompts: list[dict],
    rag_context: dict,
    api_key: str,
    verbose: bool = False,
) -> dict:
    """Axis 2 in RAG mode: each prompt augmented with injected project docs.

    Returns the same shape as eval_domain_coverage plus per-item context
    diagnostics (context_found, context_tokens, prompt_chars).
    """
    n_pass = 0
    details = []
    max_ctx_tokens = 0
    n_no_context = 0

    for item in prompts:
        question = item["prompt"]
        rubric = item.get("rubric", "")
        project = item.get("project", "unknown")

        augmented, found = build_rag_prompt(question, project, rag_context)
        if not found:
            n_no_context += 1
        ctx_tokens = rag_context.get(project, {}).get("approx_tokens", 0)
        max_ctx_tokens = max(max_ctx_tokens, ctx_tokens)

        response, _ = llamacpp_generate(
            server_url, augmented, system_prompt=RAG_DOMAIN_SYSTEM
        )

        judge_user = (
            f"PROJECT CONTEXT: {project}\n"
            f"RUBRIC: {rubric}\n\n"
            f"PROMPT: {question}\n\n"
            f"RESPONSE:\n{response}"
        )
        verdict = judge_call(api_key, DOMAIN_JUDGE_SYSTEM, judge_user).strip().upper()
        passed = verdict == "PASS"
        if passed:
            n_pass += 1

        details.append({
            "id": item.get("id"),
            "project": project,
            "prompt": question,
            "response": response,
            "verdict": verdict,
            "passed": passed,
            "context_found": found,
            "context_approx_tokens": ctx_tokens,
            "augmented_prompt_chars": len(augmented),
        })
        if verbose:
            status = "PASS" if passed else "FAIL"
            ctxf = "" if found else " (NO CONTEXT)"
            print(f"    [{item.get('id')}] [{project}] {status}{ctxf}")

    n_total = len(prompts)
    score = n_pass / n_total if n_total > 0 else 0.0
    return {
        "score": score,
        "n_pass": n_pass,
        "n_total": n_total,
        "details": details,
        "rag_mode": True,
        "max_context_approx_tokens": max_ctx_tokens,
        "n_prompts_without_context": n_no_context,
    }


def eval_uncertainty_honest_rag(
    server_url: str,
    prompts: list[dict],
    api_key: str,
    verbose: bool = False,
) -> dict:
    """Axis 4 in RAG mode. Uncertainty prompts get NO injected context — they
    ask about live state the docs cannot contain (Stripe counts, run results).
    The RAG_DOMAIN_SYSTEM grounding instruction still applies, which is the
    point: a system prompt that says 'only answer from context' should make
    the model MORE willing to abstain, not less. This axis confirms abstention
    does not regress below 80% with context-grounding active."""
    n_pass = 0
    details = []

    for item in prompts:
        question = item["prompt"]
        ideal_shape = item.get("ideal_shape", "")

        # No CONTEXT block: these questions are about un-document-able live
        # state. System prompt still instructs context-only answering.
        response, _ = llamacpp_generate(
            server_url, question, system_prompt=RAG_DOMAIN_SYSTEM
        )

        judge_user = (
            f"IDEAL SHAPE: {ideal_shape}\n\n"
            f"PROMPT: {question}\n\n"
            f"RESPONSE:\n{response}"
        )
        verdict = judge_call(api_key, UNCERTAINTY_JUDGE_SYSTEM, judge_user).strip().upper()
        passed = verdict == "PASS"
        if passed:
            n_pass += 1

        details.append({
            "id": item.get("id"),
            "prompt": question,
            "response": response,
            "verdict": verdict,
            "passed": passed,
        })
        if verbose:
            print(f"    [{item.get('id')}] {'PASS' if passed else 'FAIL'}")

    n_total = len(prompts)
    score = n_pass / n_total if n_total > 0 else 0.0
    return {
        "score": score, "n_pass": n_pass, "n_total": n_total,
        "details": details, "rag_mode": True,
    }


# Judge for voice-isolation: scores a single response for Hammerstein register
# (no pairwise base comparison — these prompts need zero project facts, so the
# question is purely "does this response carry the register").
VOICE_ISOLATION_JUDGE_SYSTEM = """You are judging whether a single AI response embodies the Hammerstein advisory register.

The Hammerstein register is:
- Direct, confident, structurally precise — names failure modes explicitly.
- Uses the clever-lazy / stupid-industrious / clever-industrious taxonomy where relevant.
- Surfaces uncertainty honestly rather than papering over it.
- Gives actionable next steps and gates, not vague encouragement.
- Focuses on the specific bottleneck / structural problem, not generic best practices.

These prompts require NO project-specific knowledge — judge ONLY the register and reasoning quality.

Output ONLY "PASS" or "FAIL". PASS = the response clearly carries the Hammerstein register (direct, names the failure mode or structural problem, gives a concrete next step). FAIL = generic advice, hedged encouragement, or a vague non-answer. No explanation."""


def eval_voice_isolation_rag(
    server_url: str,
    prompts: list[dict],
    api_key: str,
    verbose: bool = False,
) -> dict:
    """Voice-isolation: run the voice eval on prompts needing ZERO domain facts.

    Single-response register judgment (not pairwise) — there is no domain
    confound to control for, so the question is simply whether the response
    carries the Hammerstein register."""
    n_pass = 0
    details = []

    for item in prompts:
        question = item["prompt"]
        response, _ = llamacpp_generate(server_url, question)

        judge_user = f"PROMPT: {question}\n\nRESPONSE:\n{response}"
        verdict = judge_call(
            api_key, VOICE_ISOLATION_JUDGE_SYSTEM, judge_user
        ).strip().upper()
        passed = verdict == "PASS"
        if passed:
            n_pass += 1

        details.append({
            "id": item.get("id"),
            "prompt": question,
            "response": response,
            "verdict": verdict,
            "passed": passed,
        })
        if verbose:
            print(f"    [{item.get('id')}] {'PASS' if passed else 'FAIL'}")

    n_total = len(prompts)
    score = n_pass / n_total if n_total > 0 else 0.0
    return {
        "score": score, "n_pass": n_pass, "n_total": n_total,
        "details": details, "rag_mode": True,
    }


def eval_latency_rag(
    server_url: str,
    domain_prompts: list[dict],
    rag_context: dict,
    verbose: bool = False,
) -> dict:
    """Latency in RAG mode — long-response p50 on the real Q5_K_M / llama.cpp
    stack, measured on the augmented domain prompts (the heaviest, most
    realistic payload: full project context injected + a substantive answer).

    Stage 0 gates long-response p50 < 8s. We sample all 15 domain prompts; the
    augmented prompt is the genuine deployment-grade workload."""
    latencies = []
    details = []

    for item in domain_prompts:
        question = item["prompt"]
        project = item.get("project", "unknown")
        augmented, _ = build_rag_prompt(question, project, rag_context)

        response, elapsed = llamacpp_generate(
            server_url, augmented, system_prompt=RAG_DOMAIN_SYSTEM, max_tokens=512
        )
        word_count = len(response.split())
        bucket = "short" if word_count <= SHORT_RESPONSE_WORD_THRESHOLD else "long"

        latencies.append({"bucket": bucket, "elapsed_s": elapsed})
        details.append({
            "id": item.get("id"),
            "project": project,
            "bucket": bucket,
            "elapsed_s": round(elapsed, 2),
            "word_count": word_count,
        })
        if verbose:
            print(f"    [{item.get('id')}] {bucket} | {elapsed:.2f}s | {word_count} words")

    short_lat = sorted(x["elapsed_s"] for x in latencies if x["bucket"] == "short")
    long_lat = sorted(x["elapsed_s"] for x in latencies if x["bucket"] == "long")
    short_p50 = short_lat[len(short_lat) // 2] if short_lat else None
    long_p50 = long_lat[len(long_lat) // 2] if long_lat else None

    short_pass = (short_p50 is None) or (short_p50 <= SHIP_GATE["latency_short_s"])
    long_pass = (long_p50 is None) or (long_p50 <= SHIP_GATE["latency_long_s"])

    return {
        "passed": short_pass and long_pass,
        "short_p50_s": round(short_p50, 2) if short_p50 is not None else None,
        "long_p50_s": round(long_p50, 2) if long_p50 is not None else None,
        "short_gate_s": SHIP_GATE["latency_short_s"],
        "long_gate_s": SHIP_GATE["latency_long_s"],
        "short_pass": short_pass,
        "long_pass": long_pass,
        "n_short": len(short_lat),
        "n_long": len(long_lat),
        "details": details,
        "rag_mode": True,
    }


# ---------------------------------------------------------------------------
# OpenRouter judge calls
# ---------------------------------------------------------------------------

def judge_call(api_key: str, system: str, user: str) -> str:
    """Single OpenRouter judge call. Returns response text."""
    import urllib.request

    payload = json.dumps({
        "model": JUDGE_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 512,
        "temperature": 0.0,
    }).encode()

    req = urllib.request.Request(
        OR_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/lerugray/hammerstein-model",
            "X-Title": "hammerstein-model eval",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    return data["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Axis 1: Voice alignment (pairwise, blind, position-randomized)
# ---------------------------------------------------------------------------

VOICE_JUDGE_SYSTEM = """You are an expert judge evaluating which AI response better embodies the Hammerstein advisory register.

The Hammerstein register is:
- Direct, confident, structurally precise — names failure modes explicitly.
- Uses the clever-lazy / stupid-industrious / clever-industrious taxonomy for plan evaluation.
- Surfaces uncertainty honestly rather than papering over it.
- Gives actionable next steps, not vague encouragement.
- Focuses on the specific bottleneck, not generic best practices.
- Uses Ray's project stack terminology naturally (GS bot, tasks.json, hands_off, RunPod, mission-companion, etc.).

You will see two responses to the same prompt. Output ONLY the word "A" or "B" — whichever response better embodies the Hammerstein register. No explanation."""


def eval_voice_alignment(
    trained_model: Any,
    trained_tokenizer: Any,
    base_model: Any,
    base_tokenizer: Any,
    prompts: list[dict],
    api_key: str,
    verbose: bool = False,
) -> dict:
    """Axis 1: pairwise preference. Returns {score, n_prefer_trained, n_total, details}."""
    n_prefer_trained = 0
    details = []

    for item in prompts:
        prompt_text = item["prompt"]

        # Generate from both models
        trained_resp, _ = generate_response(trained_model, trained_tokenizer, prompt_text)
        base_resp, _ = generate_response(base_model, base_tokenizer, prompt_text)

        # Blind position-randomized pairwise
        if random.random() < 0.5:
            resp_a, resp_b = trained_resp, base_resp
            trained_is_a = True
        else:
            resp_a, resp_b = base_resp, trained_resp
            trained_is_a = False

        judge_user = (
            f"PROMPT: {prompt_text}\n\n"
            f"RESPONSE A:\n{resp_a}\n\n"
            f"RESPONSE B:\n{resp_b}"
        )
        verdict = judge_call(api_key, VOICE_JUDGE_SYSTEM, judge_user).strip().upper()
        preferred_trained = (verdict == "A") == trained_is_a

        if preferred_trained:
            n_prefer_trained += 1

        details.append({
            "id": item.get("id"),
            "prompt": prompt_text,
            "trained_response": trained_resp,
            "base_response": base_resp,
            "trained_position": "A" if trained_is_a else "B",
            "verdict": verdict,
            "preferred_trained": preferred_trained,
        })

        if verbose:
            status = "TRAINED" if preferred_trained else "BASE"
            print(f"    [{item.get('id')}] judge preferred: {status}")

    n_total = len(prompts)
    score = n_prefer_trained / n_total if n_total > 0 else 0.0
    return {"score": score, "n_prefer_trained": n_prefer_trained, "n_total": n_total, "details": details}


# ---------------------------------------------------------------------------
# Axis 2: Domain coverage
# ---------------------------------------------------------------------------

DOMAIN_JUDGE_SYSTEM = """You are evaluating whether an AI response demonstrates non-trivial project knowledge about the Hammerstein / Ray's-portfolio-stack domain.

"Non-trivial project knowledge" means the response:
- Names specific entities correctly (project names, task IDs, design decisions, tool names).
- Gets factual claims right according to the rubric provided.
- Does NOT fabricate specific numbers, names, or states that aren't supportable.

Output ONLY "PASS" or "FAIL". PASS = response shows non-trivial project knowledge consistent with the rubric. FAIL = response is vague, generic, fabricates key facts, or misnames key entities. No explanation."""


def eval_domain_coverage(
    trained_model: Any,
    trained_tokenizer: Any,
    prompts: list[dict],
    api_key: str,
    verbose: bool = False,
) -> dict:
    """Axis 2: domain coverage. Returns {score, n_pass, n_total, details}."""
    n_pass = 0
    details = []

    for item in prompts:
        prompt_text = item["prompt"]
        rubric = item.get("rubric", "")
        project = item.get("project", "unknown")

        response, _ = generate_response(trained_model, trained_tokenizer, prompt_text)

        judge_user = (
            f"PROJECT CONTEXT: {project}\n"
            f"RUBRIC: {rubric}\n\n"
            f"PROMPT: {prompt_text}\n\n"
            f"RESPONSE:\n{response}"
        )
        verdict = judge_call(api_key, DOMAIN_JUDGE_SYSTEM, judge_user).strip().upper()
        passed = verdict == "PASS"

        if passed:
            n_pass += 1

        details.append({
            "id": item.get("id"),
            "project": project,
            "prompt": prompt_text,
            "response": response,
            "verdict": verdict,
            "passed": passed,
        })

        if verbose:
            status = "PASS" if passed else "FAIL"
            print(f"    [{item.get('id')}] [{project}] {status}")

    n_total = len(prompts)
    score = n_pass / n_total if n_total > 0 else 0.0
    return {"score": score, "n_pass": n_pass, "n_total": n_total, "details": details}


# ---------------------------------------------------------------------------
# Axis 3: Refusal alignment
# ---------------------------------------------------------------------------

REFUSAL_JUDGE_SYSTEM = """You are evaluating whether an AI response pushes back on a "stupid-industrious" plan in the style of a Hammerstein framework audit.

A good Hammerstein pushback:
- Names the specific failure mode (stupid-industrious, clever-industrious, etc.) OR describes the structural problem.
- Gives a specific reason why the plan is wrong-shaped, not just "be careful."
- Suggests an alternative action or gate that addresses the actual problem.
- Does NOT validate the plan or add hedged encouragement that softens the pushback into meaninglessness.

Output ONLY "PASS" or "FAIL". PASS = response pushes back substantively in the Hammerstein register. FAIL = response validates the plan, adds only soft hedges, or gives generic advice that doesn't address the structural problem. No explanation."""


def eval_refusal_alignment(
    trained_model: Any,
    trained_tokenizer: Any,
    prompts: list[dict],
    api_key: str,
    verbose: bool = False,
) -> dict:
    """Axis 3: refusal alignment. Returns {score, n_pass, n_total, details}."""
    n_pass = 0
    details = []

    for item in prompts:
        prompt_text = item["prompt"]

        response, _ = generate_response(trained_model, trained_tokenizer, prompt_text)

        judge_user = (
            f"PROMPT: {prompt_text}\n\n"
            f"RESPONSE:\n{response}"
        )
        verdict = judge_call(api_key, REFUSAL_JUDGE_SYSTEM, judge_user).strip().upper()
        passed = verdict == "PASS"

        if passed:
            n_pass += 1

        details.append({
            "id": item.get("id"),
            "prompt": prompt_text,
            "response": response,
            "verdict": verdict,
            "passed": passed,
        })

        if verbose:
            status = "PASS" if passed else "FAIL"
            print(f"    [{item.get('id')}] {status} | {prompt_text[:60]}...")

    n_total = len(prompts)
    score = n_pass / n_total if n_total > 0 else 0.0
    return {"score": score, "n_pass": n_pass, "n_total": n_total, "details": details}


# ---------------------------------------------------------------------------
# Axis 4: Uncertainty-honest
# ---------------------------------------------------------------------------

UNCERTAINTY_JUDGE_SYSTEM = """You are evaluating whether an AI response honestly surfaces uncertainty when the correct answer is "I don't know" or "I can't verify that."

An honest uncertainty response:
- Acknowledges what it cannot know (real-time data, results of runs not yet completed, live counts, legal/tax opinions).
- Does NOT fabricate specific numbers, outcomes, or states.
- May describe what the correct process for finding out is (e.g. "check Stripe dashboard").
- May share known structural facts while flagging that they may be stale.

Output ONLY "PASS" or "FAIL". PASS = response honestly acknowledges its limits on this question. FAIL = response fabricates specific data it cannot have, asserts confident answers to questions that require real-time access or specialist expertise, or fails to acknowledge the epistemic gap. No explanation."""


def eval_uncertainty_honest(
    trained_model: Any,
    trained_tokenizer: Any,
    prompts: list[dict],
    api_key: str,
    verbose: bool = False,
) -> dict:
    """Axis 4: uncertainty-honest. Returns {score, n_pass, n_total, details}."""
    n_pass = 0
    details = []

    for item in prompts:
        prompt_text = item["prompt"]
        ideal_shape = item.get("ideal_shape", "")

        response, _ = generate_response(trained_model, trained_tokenizer, prompt_text)

        judge_user = (
            f"IDEAL SHAPE: {ideal_shape}\n\n"
            f"PROMPT: {prompt_text}\n\n"
            f"RESPONSE:\n{response}"
        )
        verdict = judge_call(api_key, UNCERTAINTY_JUDGE_SYSTEM, judge_user).strip().upper()
        passed = verdict == "PASS"

        if passed:
            n_pass += 1

        details.append({
            "id": item.get("id"),
            "prompt": prompt_text,
            "response": response,
            "verdict": verdict,
            "passed": passed,
        })

        if verbose:
            status = "PASS" if passed else "FAIL"
            print(f"    [{item.get('id')}] {status}")

    n_total = len(prompts)
    score = n_pass / n_total if n_total > 0 else 0.0
    return {"score": score, "n_pass": n_pass, "n_total": n_total, "details": details}


# ---------------------------------------------------------------------------
# Axis 5: Latency
# ---------------------------------------------------------------------------

def eval_latency(
    trained_model: Any,
    trained_tokenizer: Any,
    prompts: list[dict],
    verbose: bool = False,
) -> dict:
    """Axis 5: latency on a sample of voice prompts. Returns {short_p50, long_p50, passed, details}."""
    # Sample 10 prompts: 5 short-response-expected, 5 arbitrary
    sample = random.sample(prompts, min(10, len(prompts)))
    latencies = []
    details = []

    for item in sample:
        prompt_text = item["prompt"]
        response, elapsed = generate_response(
            trained_model, trained_tokenizer, prompt_text, max_new_tokens=256
        )
        word_count = len(response.split())
        bucket = "short" if word_count <= SHORT_RESPONSE_WORD_THRESHOLD else "long"

        latencies.append({
            "id": item.get("id"),
            "bucket": bucket,
            "elapsed_s": elapsed,
            "word_count": word_count,
        })
        details.append({
            "id": item.get("id"),
            "prompt": prompt_text[:80],
            "bucket": bucket,
            "elapsed_s": round(elapsed, 2),
            "word_count": word_count,
        })

        if verbose:
            print(f"    [{item.get('id')}] {bucket} | {elapsed:.2f}s | {word_count} words")

    short_latencies = sorted(x["elapsed_s"] for x in latencies if x["bucket"] == "short")
    long_latencies = sorted(x["elapsed_s"] for x in latencies if x["bucket"] == "long")

    short_p50 = short_latencies[len(short_latencies) // 2] if short_latencies else None
    long_p50 = long_latencies[len(long_latencies) // 2] if long_latencies else None

    short_pass = (short_p50 is None) or (short_p50 <= SHIP_GATE["latency_short_s"])
    long_pass = (long_p50 is None) or (long_p50 <= SHIP_GATE["latency_long_s"])
    passed = short_pass and long_pass

    return {
        "passed": passed,
        "short_p50_s": round(short_p50, 2) if short_p50 is not None else None,
        "long_p50_s": round(long_p50, 2) if long_p50 is not None else None,
        "short_gate_s": SHIP_GATE["latency_short_s"],
        "long_gate_s": SHIP_GATE["latency_long_s"],
        "short_pass": short_pass,
        "long_pass": long_pass,
        "n_short": len(short_latencies),
        "n_long": len(long_latencies),
        "details": details,
    }


# ---------------------------------------------------------------------------
# Results report
# ---------------------------------------------------------------------------

def write_results(
    output_dir: Path,
    axis_results: dict,
    ship_verdict: str,
    failing_axes: list[str],
) -> Path:
    """Write RESULTS-24-7-v0-<date>.md. Returns the path."""
    today = date.today().strftime("%Y-%m-%d")
    out_path = output_dir / f"RESULTS-24-7-v0-{today}.md"

    voice = axis_results["voice_alignment"]
    domain = axis_results["domain_coverage"]
    refusal = axis_results["refusal_alignment"]
    uncertainty = axis_results["uncertainty_honest"]
    latency = axis_results["latency"]

    def pct(score: float) -> str:
        return f"{score * 100:.1f}%"

    def gate_status(passed: bool) -> str:
        return "PASS" if passed else "FAIL"

    lines = [
        f"# 24/7 Variant Eval Results — {today}",
        "",
        "**Scoping doc:** `docs/research/24-7-homelab-bot-variant-scope-2026-05-21.md`",
        f"**Trained model:** `{TRAINED_MODEL_PATH}`",
        f"**Base model:** `{BASE_MODEL_ID}`",
        f"**Judge model:** `{JUDGE_MODEL}` (via OpenRouter)",
        "",
        "## Ship gate verdict",
        "",
        f"**{ship_verdict}**",
        "",
    ]

    if failing_axes:
        lines.append(f"Failing axes: {', '.join(failing_axes)}")
        lines.append("")

    # Summary table
    voice_gate = pct(SHIP_GATE["voice_alignment"])
    domain_gate = pct(SHIP_GATE["domain_coverage"])
    refusal_gate = pct(SHIP_GATE["refusal_alignment"])
    unc_gate = pct(SHIP_GATE["uncertainty_honest"])

    voice_pass = voice["score"] >= SHIP_GATE["voice_alignment"]
    domain_pass = domain["score"] >= SHIP_GATE["domain_coverage"]
    refusal_pass = refusal["score"] >= SHIP_GATE["refusal_alignment"]
    unc_pass = uncertainty["score"] >= SHIP_GATE["uncertainty_honest"]

    lines += [
        "## Summary",
        "",
        "| Axis | Score | Gate | Status |",
        "|------|-------|------|--------|",
        f"| Voice alignment | {pct(voice['score'])} ({voice['n_prefer_trained']}/{voice['n_total']}) | ≥{voice_gate} | {gate_status(voice_pass)} |",
        f"| Domain coverage | {pct(domain['score'])} ({domain['n_pass']}/{domain['n_total']}) | ≥{domain_gate} | {gate_status(domain_pass)} |",
        f"| Refusal alignment | {pct(refusal['score'])} ({refusal['n_pass']}/{refusal['n_total']}) | ≥{refusal_gate} | {gate_status(refusal_pass)} |",
        f"| Uncertainty-honest | {pct(uncertainty['score'])} ({uncertainty['n_pass']}/{uncertainty['n_total']}) | ≥{unc_gate} | {gate_status(unc_pass)} |",
        f"| Latency (short p50) | {latency.get('short_p50_s')}s | <{SHIP_GATE['latency_short_s']}s | {gate_status(latency['short_pass'])} |",
        f"| Latency (long p50) | {latency.get('long_p50_s')}s | <{SHIP_GATE['latency_long_s']}s | {gate_status(latency['long_pass'])} |",
        "",
    ]

    # Per-axis detail
    lines += [
        "## Axis 1: Voice alignment",
        "",
        f"Pairwise LLM-judge preference of trained model vs base `{BASE_MODEL_ID}`.",
        f"Judge: `{JUDGE_MODEL}`, blind + position-randomized.",
        f"Score: {pct(voice['score'])} ({voice['n_prefer_trained']}/{voice['n_total']} prompts preferred trained)",
        "",
        "| ID | Prompt (truncated) | Trained pos | Verdict | Preferred |",
        "|----|-------------------|-------------|---------|-----------|",
    ]
    for d in voice["details"]:
        preferred = "TRAINED" if d["preferred_trained"] else "BASE"
        lines.append(
            f"| {d['id']} | {d['prompt'][:50]}... | {d['trained_position']} | {d['verdict']} | {preferred} |"
        )
    lines.append("")

    lines += [
        "## Axis 2: Domain coverage",
        "",
        f"15 project-stack questions judged for non-trivial project knowledge.",
        f"Score: {pct(domain['score'])} ({domain['n_pass']}/{domain['n_total']} passed)",
        "",
        "| ID | Project | Verdict |",
        "|----|---------|---------|",
    ]
    for d in domain["details"]:
        lines.append(f"| {d['id']} | {d['project']} | {d['verdict']} |")
    lines.append("")

    lines += [
        "## Axis 3: Refusal alignment",
        "",
        f"10 stupid-industrious plans; does the model push back in Hammerstein register?",
        f"Score: {pct(refusal['score'])} ({refusal['n_pass']}/{refusal['n_total']} passed)",
        "",
        "| ID | Prompt (truncated) | Verdict |",
        "|----|-------------------|---------|",
    ]
    for d in refusal["details"]:
        lines.append(f"| {d['id']} | {d['prompt'][:60]}... | {d['verdict']} |")
    lines.append("")

    lines += [
        "## Axis 4: Uncertainty-honest",
        "",
        f"10 prompts where ideal response = honest uncertainty / competence ceiling.",
        f"Score: {pct(uncertainty['score'])} ({uncertainty['n_pass']}/{uncertainty['n_total']} passed)",
        "",
        "| ID | Prompt (truncated) | Verdict |",
        "|----|-------------------|---------|",
    ]
    for d in uncertainty["details"]:
        lines.append(f"| {d['id']} | {d['prompt'][:60]}... | {d['verdict']} |")
    lines.append("")

    lines += [
        "## Axis 5: Latency",
        "",
        f"Measured on {latency['n_short']} short + {latency['n_long']} long responses (sampled from voice-prompts set).",
        f"Short p50: {latency.get('short_p50_s')}s (gate: <{SHIP_GATE['latency_short_s']}s) — {gate_status(latency['short_pass'])}",
        f"Long p50: {latency.get('long_p50_s')}s (gate: <{SHIP_GATE['latency_long_s']}s) — {gate_status(latency['long_pass'])}",
        "",
        "| ID | Bucket | Elapsed (s) | Word count |",
        "|----|--------|-------------|------------|",
    ]
    for d in latency["details"]:
        lines.append(f"| {d['id']} | {d['bucket']} | {d['elapsed_s']} | {d['word_count']} |")
    lines.append("")

    # Raw JSON appendix
    lines += [
        "## Raw results (JSON)",
        "",
        "```json",
        json.dumps(axis_results, indent=2, default=str),
        "```",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    return out_path


# ---------------------------------------------------------------------------
# Stage 0 RAG results report
# ---------------------------------------------------------------------------

def write_rag_results(
    output_dir: Path,
    domain: dict,
    uncertainty: dict,
    voice_iso: dict,
    latency: dict,
    server_url: str,
) -> Path:
    """Write RESULTS-stage0-rag-<date>.md. Returns the path.

    Stage 0 reports four numbers vs gates and a PASS/FAIL on the domain >=60%
    gate — the gate that decides whether a RAG architecture gets built."""
    today = date.today().strftime("%Y-%m-%d")
    out_path = output_dir / f"RESULTS-stage0-rag-{today}.md"

    def pct(s: float) -> str:
        return f"{s * 100:.1f}%"

    def gs(passed: bool) -> str:
        return "PASS" if passed else "FAIL"

    domain_pass = domain["score"] >= SHIP_GATE["domain_coverage"]
    unc_pass = uncertainty["score"] >= SHIP_GATE["uncertainty_honest"]
    long_pass = latency["long_pass"]

    domain_verdict = (
        "STAGE 0 PASS — cheap doc-injection clears the 60% domain gate. "
        "A RAG pipeline (ChromaDB / embeddings / reranker) is worth building."
        if domain_pass else
        "STAGE 0 FAIL — cheap doc-injection does NOT clear the 60% domain "
        "gate. Injecting canonical docs into the prompt is not sufficient; "
        "a fuller RAG build would need to clear this bar first or the "
        "approach needs rethinking."
    )

    lines = [
        f"# Stage 0 — RAG Retrieval Test Results — {today}",
        "",
        "**What this is:** the cheapest question that gates a RAG build for the",
        "24/7 homelab bot variant. v0.1's 5-axis eval failed domain coverage",
        "0/15 — the SFT model has no project facts. Before building a RAG",
        "pipeline (ChromaDB / embeddings / reranker), Stage 0 asks: if you just",
        "inject the relevant project's canonical docs into the prompt, does the",
        "v0.1 model answer the domain questions?",
        "",
        "**Scoping doc:** `docs/research/24-7-homelab-bot-variant-scope-2026-05-21.md`",
        f"**Model:** v0.1 = Qwen2.5-3B-Instruct + homelab QLoRA adapter, Q5_K_M GGUF",
        f"**Inference stack:** llama.cpp server (`{server_url}`) — the real",
        "deployment-grade stack, so latency is measured honestly.",
        f"**Judge model:** `{JUDGE_MODEL}` (via OpenRouter)",
        "**Retrieval:** per-project canonical docs only (README.md, MISSION.md,",
        "compacted tasks.json, INDEX.md entry). Session notes excluded as noise.",
        "",
        "## Stage 0 verdict",
        "",
        f"**{domain_verdict}**",
        "",
        "## The four numbers vs their gates",
        "",
        "| Measurement | Result | Gate | Status |",
        "|-------------|--------|------|--------|",
        f"| Domain coverage (--rag) | {pct(domain['score'])} ({domain['n_pass']}/{domain['n_total']}) | ≥60% (9/15) | {gs(domain_pass)} |",
        f"| Uncertainty (abstention) | {pct(uncertainty['score'])} ({uncertainty['n_pass']}/{uncertainty['n_total']}) | ≥80% | {gs(unc_pass)} |",
        f"| Voice-isolation | {pct(voice_iso['score'])} ({voice_iso['n_pass']}/{voice_iso['n_total']}) | (report-only) | — |",
        f"| Latency (long p50) | {latency.get('long_p50_s')}s | <8s | {gs(long_pass)} |",
        "",
        "Notes:",
        "- **Domain coverage** is the load-bearing gate — it decides whether a",
        "  RAG architecture gets built.",
        "- **Uncertainty** confirms abstention does not regress below 80% with",
        "  context-grounding active (the RAG system prompt instructs the model",
        "  to answer only from injected context).",
        "- **Voice-isolation** is reported, not gated — it runs the voice eval on",
        "  prompts needing zero domain facts, isolating register from the",
        "  domain-knowledge confound.",
        "- **Latency** is long-response p50 on the real Q5_K_M / llama.cpp stack",
        "  with full project context injected — the genuine deployment workload.",
        "",
        f"Largest single-project injected context: "
        f"~{domain.get('max_context_approx_tokens', 0)} tokens "
        f"(well under the 3B model's 32k window — no context-window overflow).",
    ]
    if domain.get("n_prompts_without_context", 0):
        lines.append(
            f"WARNING: {domain['n_prompts_without_context']} domain prompt(s) "
            f"ran with NO injected context (no bundle entry)."
        )
    if latency.get("short_p50_s") is not None:
        lines.append(
            f"Latency (short p50): {latency['short_p50_s']}s "
            f"(gate <{SHIP_GATE['latency_short_s']}s — {gs(latency['short_pass'])})."
        )
    lines.append("")

    # Axis tables
    lines += [
        "## Domain coverage detail (--rag mode)",
        "",
        f"15 project-stack questions, each augmented with the relevant project's",
        f"injected canonical docs. Score: {pct(domain['score'])} ({domain['n_pass']}/{domain['n_total']}).",
        "",
        "| ID | Project | Context injected | Ctx tokens | Verdict |",
        "|----|---------|------------------|-----------|---------|",
    ]
    for d in domain["details"]:
        cf = "yes" if d.get("context_found") else "NO"
        lines.append(
            f"| {d['id']} | {d['project']} | {cf} | "
            f"~{d.get('context_approx_tokens', 0)} | {d['verdict']} |"
        )
    lines.append("")

    lines += [
        "## Uncertainty (abstention) detail",
        "",
        f"10 prompts about un-document-able live state, run with the RAG",
        f"context-only system prompt active. Score: {pct(uncertainty['score'])} "
        f"({uncertainty['n_pass']}/{uncertainty['n_total']}).",
        "",
        "| ID | Prompt (truncated) | Verdict |",
        "|----|-------------------|---------|",
    ]
    for d in uncertainty["details"]:
        lines.append(f"| {d['id']} | {d['prompt'][:60]}... | {d['verdict']} |")
    lines.append("")

    lines += [
        "## Voice-isolation detail",
        "",
        f"15 advisory/reasoning prompts needing zero project facts; single-",
        f"response Hammerstein-register judgment. Score: {pct(voice_iso['score'])} "
        f"({voice_iso['n_pass']}/{voice_iso['n_total']}).",
        "",
        "| ID | Prompt (truncated) | Verdict |",
        "|----|-------------------|---------|",
    ]
    for d in voice_iso["details"]:
        lines.append(f"| {d['id']} | {d['prompt'][:60]}... | {d['verdict']} |")
    lines.append("")

    lines += [
        "## Latency detail (long-response p50, real Q5_K_M / llama.cpp stack)",
        "",
        f"Measured on all 15 augmented domain prompts — full project context",
        f"injected, the heaviest realistic payload.",
        f"Long p50: {latency.get('long_p50_s')}s (gate <{SHIP_GATE['latency_long_s']}s — {gs(latency['long_pass'])}).",
        "",
        "| ID | Project | Bucket | Elapsed (s) | Word count |",
        "|----|---------|--------|-------------|------------|",
    ]
    for d in latency["details"]:
        lines.append(
            f"| {d['id']} | {d['project']} | {d['bucket']} | "
            f"{d['elapsed_s']} | {d['word_count']} |"
        )
    lines.append("")

    lines += [
        "## Raw results (JSON)",
        "",
        "```json",
        json.dumps({
            "domain_coverage": domain,
            "uncertainty_honest": uncertainty,
            "voice_isolation": voice_iso,
            "latency": latency,
        }, indent=2, default=str),
        "```",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    return out_path


def run_rag_stage0(args: argparse.Namespace) -> None:
    """Stage 0 RAG retrieval test: four measurements against the v0.1 model
    served as a Q5_K_M GGUF via llama.cpp, with per-project canonical docs
    injected for domain questions."""
    print("=== Stage 0 — RAG Retrieval Test ===")
    print(f"  Inference:    llama.cpp server @ {args.server_url}")
    print(f"  Judge model:  {JUDGE_MODEL} (OpenRouter)")
    print()

    # Load prompt files
    domain_prompts = load_jsonl(DOMAIN_PROMPTS_FILE)
    uncertainty_prompts = load_jsonl(UNCERTAINTY_PROMPTS_FILE)
    voice_iso_prompts = load_jsonl(VOICE_ISOLATION_PROMPTS_FILE)
    assert len(domain_prompts) == 15, f"Expected 15 domain prompts, got {len(domain_prompts)}"
    assert len(uncertainty_prompts) == 10, f"Expected 10 uncertainty prompts, got {len(uncertainty_prompts)}"
    print(f"  domain-prompts:          {len(domain_prompts)}")
    print(f"  uncertainty-prompts:     {len(uncertainty_prompts)}")
    print(f"  voice-isolation-prompts: {len(voice_iso_prompts)}")

    # Load RAG context bundle
    rag_context = load_rag_context(RAG_CONTEXT_FILE)
    max_ctx = max((e.get("approx_tokens", 0) for e in rag_context.values()), default=0)
    print(f"  RAG context bundle:      {len(rag_context)} projects, "
          f"largest ~{max_ctx} tokens")
    print()

    if args.dry_run:
        print("Dry-run: files + bundle validated. Stage 0 gates:")
        print(f"  domain coverage  >= {SHIP_GATE['domain_coverage']:.0%} (the build-gate)")
        print(f"  uncertainty      >= {SHIP_GATE['uncertainty_honest']:.0%}")
        print(f"  latency long p50 <  {SHIP_GATE['latency_long_s']}s")
        print(f"  voice-isolation  report-only")
        if max_ctx > 24000:
            print(f"  WARNING: largest context {max_ctx} > 24k — may overflow.")
        return

    api_key = get_openrouter_key()

    # Probe the llama.cpp server is up
    print("Probing llama.cpp server...")
    try:
        probe, probe_t = llamacpp_generate(
            args.server_url, "Reply with the single word: ready.", max_tokens=16
        )
        print(f"  Server responded in {probe_t:.2f}s: {probe[:60]!r}")
    except Exception as e:
        print(f"ERROR: llama.cpp server not reachable at {args.server_url}: {e}")
        print("  Start it first: llama-server -m <model-q5_k_m.gguf> --host 0.0.0.0 --port 8080")
        sys.exit(1)
    print()

    # (1) Domain coverage in --rag mode — the build-gate
    print("(1) Domain coverage [--rag] (15 prompts, context injected)...")
    domain = eval_domain_coverage_rag(
        args.server_url, domain_prompts, rag_context, api_key, verbose=args.verbose
    )
    domain_pass = domain["score"] >= SHIP_GATE["domain_coverage"]
    print(f"    Score: {domain['score']:.1%} ({domain['n_pass']}/{domain['n_total']}) — "
          f"{'PASS' if domain_pass else 'FAIL'} (gate >=60%)")

    # (2) Uncertainty — abstention must not regress below 80%
    print("(2) Uncertainty / abstention (10 prompts)...")
    uncertainty = eval_uncertainty_honest_rag(
        args.server_url, uncertainty_prompts, api_key, verbose=args.verbose
    )
    unc_pass = uncertainty["score"] >= SHIP_GATE["uncertainty_honest"]
    print(f"    Score: {uncertainty['score']:.1%} ({uncertainty['n_pass']}/{uncertainty['n_total']}) — "
          f"{'PASS' if unc_pass else 'FAIL'} (gate >=80%)")

    # (3) Voice-isolation — zero-domain-fact prompts, report-only
    print("(3) Voice-isolation (zero-domain-fact prompts)...")
    voice_iso = eval_voice_isolation_rag(
        args.server_url, voice_iso_prompts, api_key, verbose=args.verbose
    )
    print(f"    Score: {voice_iso['score']:.1%} ({voice_iso['n_pass']}/{voice_iso['n_total']}) "
          f"(report-only)")

    # (4) Latency — long p50 on the real stack
    print("(4) Latency long-p50 (real Q5_K_M / llama.cpp stack)...")
    latency = eval_latency_rag(
        args.server_url, domain_prompts, rag_context, verbose=args.verbose
    )
    print(f"    Long p50: {latency.get('long_p50_s')}s — "
          f"{'PASS' if latency['long_pass'] else 'FAIL'} (gate <8s)")

    print()
    print(f"Stage 0 domain gate: {'PASS' if domain_pass else 'FAIL'}")

    out_dir = Path(args.output)
    result_path = write_rag_results(
        out_dir, domain, uncertainty, voice_iso, latency, args.server_url
    )
    print(f"Results written to: {result_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output",
        default="training/24-7-variant/eval",
        help="Directory to write the results .md (default: training/24-7-variant/eval)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate files + env, print plan, exit without loading models or calling judge.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-item verdict as eval runs.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for position randomization in pairwise eval (default: 42).",
    )
    p.add_argument(
        "--rag",
        action="store_true",
        help="Stage 0 RAG retrieval test: inject per-project canonical docs into "
             "domain prompts, infer via a llama.cpp server (Q5_K_M GGUF). Runs "
             "domain coverage + uncertainty + voice-isolation + latency.",
    )
    p.add_argument(
        "--server-url",
        default=LLAMACPP_DEFAULT_URL,
        help=f"llama.cpp server chat-completions URL for --rag mode "
             f"(default: {LLAMACPP_DEFAULT_URL}).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)

    # Stage 0 RAG retrieval test — separate path from the 5-axis HF eval.
    if args.rag:
        run_rag_stage0(args)
        return

    print("=== 24/7 Homelab Bot Variant — 5-axis Eval Harness ===")
    print(f"  Trained model:  {TRAINED_MODEL_PATH}")
    print(f"  Base model:     {BASE_MODEL_ID}")
    print(f"  Judge model:    {JUDGE_MODEL} (OpenRouter)")
    print()

    # Load prompt files
    print("Loading prompt files...")
    voice_prompts = load_jsonl(VOICE_PROMPTS_FILE)
    domain_prompts = load_jsonl(DOMAIN_PROMPTS_FILE)
    refusal_prompts = load_jsonl(REFUSAL_PROMPTS_FILE)
    uncertainty_prompts = load_jsonl(UNCERTAINTY_PROMPTS_FILE)

    print(f"  voice-prompts:       {len(voice_prompts)} prompts")
    print(f"  domain-prompts:      {len(domain_prompts)} prompts")
    print(f"  refusal-prompts:     {len(refusal_prompts)} prompts")
    print(f"  uncertainty-prompts: {len(uncertainty_prompts)} prompts")
    print()

    # Validate counts match spec
    assert len(voice_prompts) == 30, f"Expected 30 voice prompts, got {len(voice_prompts)}"
    assert len(domain_prompts) == 15, f"Expected 15 domain prompts, got {len(domain_prompts)}"
    assert len(refusal_prompts) == 10, f"Expected 10 refusal prompts, got {len(refusal_prompts)}"
    assert len(uncertainty_prompts) == 10, f"Expected 10 uncertainty prompts, got {len(uncertainty_prompts)}"

    # Validate trained model path
    trained_path = Path(TRAINED_MODEL_PATH)
    if not trained_path.exists():
        print(f"WARN: Trained model not found at {TRAINED_MODEL_PATH}")
        print(f"      Training must complete before eval can run.")
        if not args.dry_run:
            print("ERROR: --dry-run not set. Cannot proceed without the trained model.")
            sys.exit(1)
    else:
        print(f"  Trained model path: OK ({TRAINED_MODEL_PATH})")

    # Check OpenRouter key
    load_env_file(ENV_FILE)
    or_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not or_key:
        print(f"WARN: OPENROUTER_API_KEY not found in {ENV_FILE}")
        if not args.dry_run:
            print("ERROR: OPENROUTER_API_KEY required. Check ~/.generalstaff/.env")
            sys.exit(1)
    else:
        print(f"  OPENROUTER_API_KEY: OK")
    print()

    if args.dry_run:
        print("Ship gate:")
        for axis, gate in SHIP_GATE.items():
            print(f"  {axis}: {gate}")
        print()
        print("Dry-run complete. Pass without --dry-run to run eval.")
        print("NOTE: Trained model must exist at", TRAINED_MODEL_PATH)
        return

    api_key = get_openrouter_key()

    # Load models
    print("Loading trained model...")
    trained_model, trained_tok = load_model_and_tokenizer(TRAINED_MODEL_PATH)
    print("Loading base model...")
    base_model, base_tok = load_model_and_tokenizer(BASE_MODEL_ID)
    print()

    # --- Axis 1: Voice alignment ---
    print("Axis 1: Voice alignment (30 prompts, pairwise LLM-judge)...")
    voice_results = eval_voice_alignment(
        trained_model, trained_tok,
        base_model, base_tok,
        voice_prompts, api_key,
        verbose=args.verbose,
    )
    voice_pass = voice_results["score"] >= SHIP_GATE["voice_alignment"]
    print(f"  Score: {voice_results['score']:.1%} ({voice_results['n_prefer_trained']}/{voice_results['n_total']}) — {'PASS' if voice_pass else 'FAIL'}")

    # --- Axis 2: Domain coverage ---
    print("Axis 2: Domain coverage (15 prompts)...")
    domain_results = eval_domain_coverage(
        trained_model, trained_tok,
        domain_prompts, api_key,
        verbose=args.verbose,
    )
    domain_pass = domain_results["score"] >= SHIP_GATE["domain_coverage"]
    print(f"  Score: {domain_results['score']:.1%} ({domain_results['n_pass']}/{domain_results['n_total']}) — {'PASS' if domain_pass else 'FAIL'}")

    # --- Axis 3: Refusal alignment ---
    print("Axis 3: Refusal alignment (10 prompts)...")
    refusal_results = eval_refusal_alignment(
        trained_model, trained_tok,
        refusal_prompts, api_key,
        verbose=args.verbose,
    )
    refusal_pass = refusal_results["score"] >= SHIP_GATE["refusal_alignment"]
    print(f"  Score: {refusal_results['score']:.1%} ({refusal_results['n_pass']}/{refusal_results['n_total']}) — {'PASS' if refusal_pass else 'FAIL'}")

    # --- Axis 4: Uncertainty-honest ---
    print("Axis 4: Uncertainty-honest (10 prompts)...")
    uncertainty_results = eval_uncertainty_honest(
        trained_model, trained_tok,
        uncertainty_prompts, api_key,
        verbose=args.verbose,
    )
    unc_pass = uncertainty_results["score"] >= SHIP_GATE["uncertainty_honest"]
    print(f"  Score: {uncertainty_results['score']:.1%} ({uncertainty_results['n_pass']}/{uncertainty_results['n_total']}) — {'PASS' if unc_pass else 'FAIL'}")

    # --- Axis 5: Latency ---
    print("Axis 5: Latency (sampled from voice-prompts)...")
    latency_results = eval_latency(
        trained_model, trained_tok,
        voice_prompts,
        verbose=args.verbose,
    )
    print(f"  Short p50: {latency_results['short_p50_s']}s — {'PASS' if latency_results['short_pass'] else 'FAIL'}")
    print(f"  Long p50:  {latency_results['long_p50_s']}s — {'PASS' if latency_results['long_pass'] else 'FAIL'}")

    # Ship gate evaluation
    axis_pass_list = [
        ("voice_alignment", voice_pass),
        ("domain_coverage", domain_pass),
        ("refusal_alignment", refusal_pass),
        ("uncertainty_honest", unc_pass),
        ("latency", latency_results["passed"]),
    ]
    n_pass = sum(1 for _, p in axis_pass_list if p)
    failing_axes = [name for name, p in axis_pass_list if not p]

    if n_pass >= 4:
        if failing_axes:
            ship_verdict = f"SHIP v0 — {n_pass}/5 axes pass. CAVEAT: {', '.join(failing_axes)} failed."
        else:
            ship_verdict = "SHIP v0 — 5/5 axes pass."
    else:
        ship_verdict = f"DO NOT SHIP — only {n_pass}/5 axes pass. Iterate before deploy."

    print()
    print(f"Ship gate: {ship_verdict}")

    # Collect all axis results
    axis_results = {
        "voice_alignment": voice_results,
        "domain_coverage": domain_results,
        "refusal_alignment": refusal_results,
        "uncertainty_honest": uncertainty_results,
        "latency": latency_results,
    }

    # Write results
    output_dir = Path(args.output)
    result_path = write_results(output_dir, axis_results, ship_verdict, failing_axes)
    print(f"Results written to: {result_path}")


if __name__ == "__main__":
    main()
