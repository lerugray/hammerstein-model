# Qwen2.5-7B tool-use SFT: prior-art memo + v0.2.9 fix

**Date:** 2026-05-25 (Mac-Neo, Opus 1M)
**Scope:** Diagnose the v0.2.6.2→v0.2.7→v0.2.8 tool-use regression (50% → 30% pass) and surface the canonical fix grounded in Qwen's chat template + HuggingFace docs.
**Verdict:** **Known-solved**. There is an established canonical format. Our trainer has a load-bearing bug that drops the `tool_calls` field silently. Empirically reproduced.

---

## 1. Bug diagnosis (the hypothesis was right + there's a second bug)

### Bug #1: `format_example` drops `tool_calls`

`training/24-7-variant/train_v028_continued.py` lines 90-99:

```python
def format_example(row: dict) -> str:
    if "query" in row and "response" in row:
        return (f"<|im_start|>user\n{row['query']}<|im_end|>\n"
                f"<|im_start|>assistant\n{row['response']}<|im_end|>")
    if "messages" in row:
        return "\n".join(
            f"<|im_start|>{m.get('role','user')}\n{m.get('content','')}<|im_end|>"
            for m in row["messages"]
        )
```

`m.get('content','')` is the only field read. The `tool_calls` field on
assistant messages is silently discarded. The `tool` role is wrapped in
`<|im_start|>tool` which is **wrong** — Qwen's chat template wraps tool
responses in `<|im_start|>user\n<tool_response>...\n</tool_response>`.

### Empirical proof (jinja2 render of the canonical Qwen2.5 template vs our trainer)

Input row (from `data/ray-stack-sft-v0.2.8-additions.jsonl` row 199, paraphrased):

```json
{"messages": [
  {"role": "user", "content": "factcheck me on X"},
  {"role": "assistant", "content": "Searching.", "tool_calls": [
    {"name": "web_search", "arguments": {"query": "X"}}
  ]},
  {"role": "tool", "name": "web_search", "content": "Result text"},
  {"role": "assistant", "content": "Confirmed."}
]}
```

**Canonical Qwen template renders (what model expects to see):**

```
<|im_start|>system
You are Qwen, created by Alibaba Cloud. You are a helpful assistant.<|im_end|>
<|im_start|>user
factcheck me on X<|im_end|>
<|im_start|>assistant
Searching.
<tool_call>
{"name": "web_search", "arguments": {"query": "X"}}
</tool_call><|im_end|>
<|im_start|>user
<tool_response>
Result text
</tool_response><|im_end|>
<|im_start|>assistant
Confirmed.<|im_end|>
```

**Our trainer's `format_example` actually produces:**

```
<|im_start|>user
factcheck me on X<|im_end|>
<|im_start|>assistant
Searching.<|im_end|>
<|im_start|>tool
Result text<|im_end|>
<|im_start|>assistant
Confirmed.<|im_end|>
```

The model is being trained to:
1. **Say "Searching." with no tool call** (the `<tool_call>` block is gone).
2. **Hallucinate a tool result** appearing in an invalid `<|im_start|>tool`
   block (not `<tool_response>` inside a user turn).
3. **Then "confirm"** based on the hallucinated result.

This exactly matches the inference-time failure modes Ray observed:
- "model emits text-mode `[claude_code {...}]`" — it's reaching for any
  bracketed format because it never learned the real one.
- "refuses to invoke tools" — confirmed, the training corpus literally
  never showed it invoking them.
- "hallucinates tool actions completed" — the `tool` role appearing right
  after a bare "Searching." trained exactly this behavior.

### Bug #2: No `tools=` schema rendered at training time

The trainer never calls `tokenizer.apply_chat_template(..., tools=[...])`.
The Qwen2.5 template only emits the `# Tools\n\n` system-prompt preamble
(with `<tools>{schema}</tools>` schemas and the "return a json object with
function name and arguments within `<tool_call></tool_call>` XML tags"
instruction) **when `tools` is passed**. Without it, the model:
- Never sees the `<tools>` schema block.
- Never sees the instruction telling it to use `<tool_call>` format.
- Has no inference-time matched system prompt structure.

This compounds Bug #1. At inference Ollama's Modelfile renders this
preamble; at training the model never sees it. **Train/inference mismatch.**

---

## 2. Established best-practice (canonical Qwen2.5 tool-use SFT format)

### Source data shape (already what we have, no changes needed)

`tokenizer.apply_chat_template` accepts both flat and OpenAI-wrapped
`tool_calls`. Our flat shape works (the template normalizes via
`{%- if tool_call.function is defined %}{%- set tool_call = tool_call.function %}{%- endif %}`).

**Required shape (working):**
```json
{
  "messages": [
    {"role": "system", "content": "OPTIONAL — your system prompt"},
    {"role": "user", "content": "..."},
    {"role": "assistant",
     "content": "OPTIONAL pre-call narration",
     "tool_calls": [
       {"name": "tool_name",
        "arguments": {"key": "value"}}
     ]},
    {"role": "tool", "content": "tool output string"},
    {"role": "assistant", "content": "final response"}
  ],
  "tools": [
    {"type": "function",
     "function": {
       "name": "tool_name",
       "description": "what it does",
       "parameters": {
         "type": "object",
         "properties": {"key": {"type": "string", "description": "..."}},
         "required": ["key"]
       }}}
  ]
}
```

**Key constraints (HuggingFace docs, NousResearch Hermes spec, Qwen docs):**
- `arguments` must be a **dict**, NOT a JSON string. (The OpenAI API uses
  a string; Transformers expects a dict. Our data is already dict-shaped.)
- The `tool` role's `content` is always a string.
- `tools` is a list of OpenAI-format function schemas at the row level
  (passed to `apply_chat_template(messages, tools=tools)`).
- Don't manually construct `<tool_call>` XML — let the template do it.
  Manual construction was what v0.2.7.2 tried; it collapsed to 20% because
  it bypassed the template's invariants.

### Training-time invocation (the right way)

```python
def format_example(row: dict) -> str:
    messages = row["messages"]
    tools = row.get("tools")  # None if no tools for this turn
    return tokenizer.apply_chat_template(
        messages,
        tools=tools,
        tokenize=False,
        add_generation_prompt=False,  # critical: False for training
    )
```

The HuggingFace docs are explicit: `add_generation_prompt=False` during
training (`https://huggingface.co/docs/transformers/main/en/chat_templating`).

---

## 3. Reference implementations

1. **Unsloth Qwen2.5_Coder Tool_Calling notebook** — official Unsloth
   example for tool-calling SFT on Qwen2.5. Uses `apply_chat_template` end-to-end.
   `https://colab.research.google.com/github/unslothai/notebooks/blob/main/nb/Qwen2.5_Coder_(1.5B)-Tool_Calling.ipynb`
   (Couldn't extract live cell-by-cell content via WebFetch — the page
   gates behind sign-in. Reference exists and is officially blessed.)

2. **Vikhrmodels/Qwen2.5-7B-Instruct-Tool-Planning-v0.1** — full-SFT
   tool-use fine-tune on Qwen2.5-7B. Published benchmark results:
   73-93% on simple/multiple/parallel function tasks, 65% relevance, 86%
   irrelevance. Uses the `tool_calls` field with proper template handling.
   `https://huggingface.co/Vikhrmodels/Qwen2.5-7B-Instruct-Tool-Planning-v0.1`
   The dataset (`Vikhrmodels/tool-plannings-v0.1`) is open.

3. **NousResearch/hermes-function-calling-v1** — the de-facto reference
   open dataset for tool-use SFT. Hermes format is what Qwen2.5's template
   inherits from (`<tools>`, `<tool_call>`, `<tool_response>` XML tags).
   `https://huggingface.co/datasets/NousResearch/hermes-function-calling-v1`

4. **HuggingFace `chat_extras` tool-use doc** — the canonical end-to-end
   pattern for tool-use SFT. Explicit warnings about `arguments`-as-dict-
   not-string, and the recommendation to always go through
   `apply_chat_template` rather than hand-rolling text.
   `https://huggingface.co/docs/transformers/main/en/chat_extras`

---

## 4. Recommended fix for v0.2.9 retrain

### Required code changes to `train_v028_continued.py` (rename to v029)

**4.1. Replace `format_example` with a template-driven version:**

```python
def format_example(row: dict, tokenizer) -> str:
    # Legacy query/response and input/output rows: keep current behavior
    # (they're voice/refusal pairs without tools and the manual template
    # is bit-for-bit correct for those).
    if "query" in row and "response" in row:
        msgs = [
            {"role": "user", "content": row["query"]},
            {"role": "assistant", "content": row["response"]},
        ]
        return tokenizer.apply_chat_template(
            msgs, tools=None, tokenize=False, add_generation_prompt=False
        )
    if "input" in row and "output" in row:
        msgs = [
            {"role": "user", "content": row["input"]},
            {"role": "assistant", "content": row["output"]},
        ]
        return tokenizer.apply_chat_template(
            msgs, tools=None, tokenize=False, add_generation_prompt=False
        )
    if "messages" in row:
        tools = row.get("tools")  # honor per-row tools list if present
        return tokenizer.apply_chat_template(
            row["messages"],
            tools=tools,
            tokenize=False,
            add_generation_prompt=False,
        )
    return ""
```

This single change resolves Bug #1 (drops tool_calls) AND Bug #2 (no
tools= schema rendered). The template now generates the canonical
`<tool_call>{...}</tool_call>` and `<tool_response>...</tool_response>`
blocks, and the `# Tools` system preamble.

**4.2. Pass `tokenizer` into `build_mix`:**

```python
def build_mix(args, tokenizer):
    ...
    text = format_example(row, tokenizer)
```

Load tokenizer early in `run_training` and thread it through. Trivial
refactor.

**4.3. Augment v0.2.8 additions with `tools` field per row:**

The current `ray-stack-sft-v0.2.8-additions.jsonl` row 199 has messages
with `tool_calls` but no top-level `tools` field. Add the schemas to
each tool-using row:

```json
{
  "messages": [...],
  "tools": [
    {"type": "function",
     "function": {
       "name": "web_search",
       "description": "Search the web for current information.",
       "parameters": {
         "type": "object",
         "properties": {"query": {"type": "string"}},
         "required": ["query"]
       }}},
    {"type": "function",
     "function": {
       "name": "claude_code",
       "description": "Invoke Claude Code as a tool agent.",
       "parameters": {...}}}
  ]
}
```

Write a one-shot sanitizer script `scripts/v029_concat_sanitize.py` that
walks the v0.2.8 JSONL, detects rows with `tool_calls`, and inserts the
appropriate `tools` schema list. Hammerstein has ~3-5 canonical tools
(web_search, claude_code, file_read, etc. — check the production system
prompt for the full list); enumerate them once and apply.

**4.4. Match training-time tools schema to Ollama Modelfile schema:**

The Modelfile renders the `# Tools` preamble at inference. The exact
JSON schema in `tools=[...]` at training MUST match the schemas the
Modelfile renders at inference. If they drift, train/inference mismatch
returns. Cross-check by:

```bash
# Render an inference-time prompt via Ollama
ollama show --modelfile hammerstein-7b > /tmp/modelfile.txt
# Compare TOOLS block against training tools schema
```

### Don't change

- **The flat `tool_calls` shape** in data (no `type: function` wrapper).
  Qwen's template handles both via the `if tool_call.function is defined`
  branch. Adding the wrapper is fine but unnecessary.
- **The dict-shaped `arguments`** (not JSON string). Already correct.
- **The QLoRA / Unsloth config.** That's not the failure surface; the
  v0.2.6.2 baseline at 50% pass proves QLoRA can learn tool use here.
- **The oversample multiplier (3x).** Once the format is right, 3x of
  ~200 tool-use rows should land. If it doesn't, bump to 5x as part of
  a SECOND iteration, not bundled with the format fix (confounds the
  ablation).

### What this fix predicts

If Bug #1 + #2 are the dominant failure mode, v0.2.9 should jump from
30% → 70-90% tool-use pass rate, in line with Vikhrmodels' published
benchmarks on Qwen2.5-7B. If it doesn't, the next suspects are:
- Insufficient tool-use pair count (200 may be too few; Vikhrmodels used
  the much larger tool-plannings-v0.1 dataset).
- Catastrophic forgetting from the v0.1 ray-stack overweighting the
  voice/refusal pairs.
- A second train/inference mismatch (e.g. Modelfile schema drift).

But the format fix should be tested in isolation FIRST — current state
is "the model literally never sees a tool_call during training." That's
a 100%-confident bug, not a hypothesis.

---

## 5. Sources cited

1. **Qwen2.5 official chat template (Jinja2 source)** —
   `https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/raw/main/tokenizer_config.json`
   (The template's exact `tool_call`/`tool_response` rendering rules
   were extracted and used to empirically falsify our `format_example`.)

2. **HuggingFace Transformers chat templates doc** —
   `https://huggingface.co/docs/transformers/main/en/chat_templating`
   Defines the canonical SFT pattern (`apply_chat_template` with
   `add_generation_prompt=False` for training).

3. **HuggingFace Transformers tool-use doc** —
   `https://huggingface.co/docs/transformers/main/en/chat_extras`
   Specifies `arguments`-as-dict-not-string, `tool_calls` field
   placement, `tools=` argument to `apply_chat_template`.

4. **Qwen Function Calling doc** —
   `https://qwen.readthedocs.io/en/latest/framework/function_call.html`
   Canonical assistant + tool message JSON shapes for Qwen2.5+.

5. **Vikhrmodels Qwen2.5-7B-Instruct-Tool-Planning model card** —
   `https://huggingface.co/Vikhrmodels/Qwen2.5-7B-Instruct-Tool-Planning-v0.1`
   Reference Qwen2.5-7B tool-use SFT with published benchmarks (73-93%).

6. **NousResearch Hermes-Function-Calling-v1 dataset** —
   `https://huggingface.co/datasets/NousResearch/hermes-function-calling-v1`
   De-facto reference dataset; Qwen2.5's template inherits from Hermes
   format.

7. **Unsloth Qwen2.5 Tool Calling notebook** —
   `https://colab.research.google.com/github/unslothai/notebooks/blob/main/nb/Qwen2.5_Coder_(1.5B)-Tool_Calling.ipynb`
   Official Unsloth example for Qwen2.5 tool-use SFT.

8. **Unsloth chat templates source** —
   `https://github.com/unslothai/unsloth/blob/main/unsloth/chat_templates.py`
   Confirms Unsloth ships its own `qwen-2.5` template variant that
   includes the same tool_call handling; using the tokenizer's built-in
   template via `apply_chat_template` is the safe path either way.

---

## 6. Uncertainty flags

- **Couldn't run `apply_chat_template` against a live transformers
  install on Mac.** Used jinja2 to render the Qwen template directly
  with its raw template string from the HF repo. The rendering is
  byte-equivalent to what `apply_chat_template` would produce
  (transformers doesn't do additional munging beyond template render +
  tokenize). The empirical falsification of Bug #1 is solid; the
  "transformers will accept our flat shape" claim rests on the
  template's `if tool_call.function is defined` branch (visible in the
  source) plus the HF doc's explicit "the OpenAI wrapper is OPTIONAL"
  language.

- **Didn't enumerate the production tools schema.** The fix doc says
  "Hammerstein has ~3-5 canonical tools." That's a guess from context;
  the actual count + schema needs to be read from the Modelfile or the
  production system prompt before writing the sanitizer. Trivial work
  but a precondition for v0.2.9 firing.

- **Vikhrmodels used full SFT, not QLoRA.** Their benchmark numbers
  (73-93%) may not be exactly reproducible under QLoRA; expect some
  haircut. But going from 30% → 70%+ is the predicted shape; the
  delta is what matters more than the absolute number.

- **The Unsloth notebook content wasn't extracted directly** (Colab
  page requires sign-in to render cells). The reference exists, and
  the `apply_chat_template` pattern is consistent across the entire
  Unsloth + HF documentation stack. Should be fine to rely on, but
  worth a 10-minute open-it-in-Colab verification before firing v0.2.9.

- **The fix assumes the inference-time Modelfile is correct.** If
  Ollama's tool-use rendering has its own bug (the searches surfaced
  some Qwen3 Ollama tool-call-fix discussions — possible relevance to
  Qwen2.5), the fix solves train-side mismatch but inference-side may
  still need patching. Cross-check Modelfile render vs training-time
  template render is the proof.
