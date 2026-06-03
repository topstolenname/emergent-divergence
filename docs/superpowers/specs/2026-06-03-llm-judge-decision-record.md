# LLM-as-a-Judge — Model Selection & Proposal Review (Decision Record)

**Date**: 2026-06-03
**Status**: Implemented
**Scope**: Close the "LLM-judge behavioral classifier" gap from
`2026-03-10-pre-control-gap-closure-design.md` (§6) before executing Condition B.
**Branch**: `claude/judge-llm-behavioral-classifier`

---

## 1. Decisions

### 1.1 Judge model

**Selected: `claude-haiku-4-5-20251001` (Claude Haiku 4.5), default; overridable
via `--judge-model`.**

Rationale: the judge runs one cheap call per message (~300 messages/run, ~200
input + ~50 output tokens each). Haiku is the lowest-cost, fastest Anthropic
model adequate for a constrained 6-way scoring task at temperature 0.0, costing
~$0.02 per full run. A larger model (Sonnet/Opus) is available behind
`--judge-model` for spot-checking calibration, but is not the default. This
matches the approved design spec (§6) and the existing model-naming convention
in the codebase (`claude-sonnet-4-6`, etc.).

### 1.2 The external (Gemini) proposal: **rejected as-is; aligned ideas salvaged**

A separately supplied proposal ("LLM-as-a-Judge Behavioral Classifier
Specification") was reviewed against the project's own approved design spec and
the existing keyword classifier. It was **not** adopted in its proposed form.
The one sound idea it shares with the spec — structured per-category scores
normalized into a behavioral vector for pairwise L2 distance — is already how
the keyword classifier and the spec compute `divergence_score`, and is preserved.

| Axis | External proposal | Decision | Reason |
|---|---|---|---|
| **Judge blindness** | Injects `agent_id` **and** the agent's `assigned_role` into the prompt ("initialized with the weak role prior: '{assigned_role}'") | **Reject** | The spec *requires* the judge be blind to identity, role, condition, and model. Naming the role the judge is supposed to detect makes the score a restatement of the prior, not an independent measurement — a confound that invalidates the divergence metric. This was the decisive issue. |
| **Category schema** | 5 dimensions incl. `role_rigidity`, scored 1–5 (integers) | **Reject** | The keyword classifier and spec use 6 categories (`proposal, critique, synthesis, verification, recall, clarification`) scored 0.0–1.0. The two classifiers must share schema so agreement / Spearman can be computed message-for-message. |
| **Model** | `claude-3-5-sonnet-20241022` | **Reject** | Older and pricier than necessary for the task; spec default is Haiku 4.5. |
| **Location** | `src/evaluation/` | **Reject** | Placed in `src/emergent_divergence/metrics/llm_judge.py`, parallel to the keyword classifier, per spec §2.7. |
| **Execution strategy** | Optionally `async` *inside* the `ExperimentRunner` loop | **Reject** | Analysis-side post-processing of `events.jsonl` only. Touching the runner risks crashing the loop and changing the log format — both explicit non-goals (spec §11). |
| **Plumbing** | `async` + raw `AsyncAnthropic`; adds a `pydantic` dependency | **Reject** | Reuses the existing synchronous `ModelProvider` / `ClaudeProvider` (auth, retry, cost already handled). No new dependency; `pydantic` is not in the project. |
| **Code defects** | f-string uses `{{formatted_messages}}` / `{{agent_id}}` → these render as the literal text `{formatted_messages}` / `{agent_id}`, never interpolated | **Reject** | The message text would never reach the prompt and log lines would be wrong. |
| **Normalized vector → L2 distance** | Proposed | **Adopt (already in spec)** | Implemented by averaging per-message scores into per-agent profiles and reusing `compute_behavioral_divergence` (mean pairwise L2). |

---

## 2. What was implemented

* **`src/emergent_divergence/metrics/llm_judge.py`** — blind, six-category
  classifier. Builds the spec §6 prompt (message text only), parses/validates
  JSON (tolerant of fences, clamps to 0–1, retries once then records a failure),
  classifies every `agent_message` sequentially, builds per-agent profiles and a
  divergence score, and aborts if failures exceed 10%. Also provides
  keyword-vs-judge agreement (top-1 match rate, per-category present/absent
  agreement at a 0.3 threshold, Spearman rank correlation, disagreement
  examples).
* **`metrics/divergence.py`** — `generate_analysis_report(...)` gains a
  `classifier` parameter (`keyword` default / `llm_judge` / `both`) plus optional
  `judge_provider` (injectable for offline tests) and `judge_model`. Keyword
  output is unchanged when the default is used.
* **`cli/runner.py`** — `analyze` gains `--classifier` and `--judge-model`
  flags, and prints a judge summary and agreement stats when present.
* **`tests/test_llm_judge.py`** — fully offline coverage (fake provider): prompt
  blindness, schema parity with the keyword classifier, parsing/clamping/retry,
  run-level profiles + failure cap, agreement shape, and an end-to-end
  `--classifier both` report.

### Backward compatibility

`analyze` with no `--classifier` flag is byte-for-byte the prior behavior
(verified against the archived pilot run: mean JSD 0.2935, behavioral divergence
0.1544). The judge is additive and analysis-side only — no runner or log-format
changes. Old runs can be (re)judged retroactively from their `events.jsonl`.

### Usage

```bash
# Keyword only (default, unchanged)
python -m emergent_divergence analyze --run-dir <run>

# LLM judge (Haiku default); requires ANTHROPIC_API_KEY
python -m emergent_divergence analyze --run-dir <run> --classifier llm_judge

# Both classifiers + agreement (Spearman); optional larger judge model
python -m emergent_divergence analyze --run-dir <run> --classifier both \
    --judge-model claude-sonnet-4-6
```
