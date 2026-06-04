"""Optional LLM-as-judge *qualitative* evaluator (Chain-of-Thought + rubric).

This is a complementary tool, **not** the behavioral divergence classifier. For
the experiment's core metric (behavioral specialization), use the blind,
six-category classifier in :mod:`emergent_divergence.metrics.llm_judge`, which is
wired into ``analyze`` and is deliberately kept blind to agent identity, role,
and condition so its scores measure divergence rather than restate the prior.

This evaluator scores an agent's *qualitative* conduct (consistency,
distinctiveness, contribution quality, coherence, engagement) on a calibrated
1-5 rubric. It is identity-aware **on purpose** — it tracks one named agent over
a window — which is exactly why it must not be used as a divergence measurement.

Two deliberate techniques:

* **Chain-of-thought before scoring.** The judge reasons inside ``<thinking>``
  tags before emitting the JSON scores. Writing the rationale first improves
  calibration and reduces snap-judgement bias; the reasoning is captured for
  auditability rather than discarded.
* **Resilient structured output.** Scores are recovered by scanning every
  embedded JSON object and taking the first that satisfies the rubric, so the
  ``<thinking>`` preamble, prose, or markdown fences around the JSON do not
  defeat parsing.

It uses the shared synchronous ``ModelProvider`` (the Claude arm by default), so
authentication, retry, and cost accounting are the ones already used by agents.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from emergent_divergence.providers.base import ModelProvider

# Low-cost default, consistent with the behavioral classifier. Overridable.
DEFAULT_JUDGE_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class JudgeRubric:
    """An ordered scoring rubric: dimension name -> description, plus a scale."""

    dimensions: dict[str, str]
    scale_min: int = 1
    scale_max: int = 5
    instructions: str = (
        "You are an impartial, well-calibrated evaluator of an agent in a "
        "multi-agent coordination experiment. A score of 3 is the typical "
        "baseline (average), not a failure."
    )


DEFAULT_RUBRIC = JudgeRubric(
    dimensions={
        "role_consistency": "Keeps a consistent behavioral tendency without breaking character.",
        "distinctiveness": "Is behaviorally distinguishable from the other agents.",
        "contribution_quality": "Introduces novel, grounded points that advance the deliberation.",
        "coherence": "Responses are internally logically consistent.",
        "engagement": "Synthesizes or directly critiques others' points rather than monologuing.",
    },)

_JUDGE_SYSTEM = (
    "You are a meticulous evaluator. Reason step by step inside <thinking> tags, "
    "then output a single JSON object containing only the integer scores."
)

# Tolerates a missing closing tag: if the judge is truncated at max_tokens
# mid-reasoning, still capture the partial CoT (valuable for auditing).
_THINKING_RE = re.compile(r"<thinking>(.*?)(?:</thinking>|$)", re.DOTALL)


def build_judge_prompt(
    agent_id: str, messages: list[str], rubric: JudgeRubric = DEFAULT_RUBRIC
) -> str:
    """Build a CoT scoring prompt for one agent's recent messages."""
    dims = "\n".join(f"  - {name}: {desc}" for name, desc in rubric.dimensions.items())
    transcript = "\n---\n".join(messages[-5:])  # sliding window
    schema = ", ".join(f'"{name}": <int>' for name in rubric.dimensions)
    return (
        f"{rubric.instructions}\n\n"
        f"<agent_id>{agent_id}</agent_id>\n\n"
        f"<recent_transcript>\n{transcript}\n</recent_transcript>\n\n"
        f"<rubric>\nScore each dimension {rubric.scale_min}-{rubric.scale_max} "
        f"(3 = baseline average):\n{dims}\n</rubric>\n\n"
        "<instructions>\n"
        "1. First reason step by step about EACH dimension inside <thinking> "
        "tags, citing specific quotes from the transcript.\n"
        "2. Then output ONLY a JSON object of the integer scores.\n"
        "</instructions>\n\n"
        "Example:\n<thinking>\nrole_consistency: the agent said \"...\" which ...\n"
        f"</thinking>\n{{{schema}}}"
    )


def _extract_json_objects(text: str) -> Iterator[dict]:
    """Yield each valid top-level JSON object embedded in ``text``, in order.

    Mirrors the resilient scan in :mod:`emergent_divergence.metrics.llm_judge`,
    kept self-contained here so this evaluator carries no heavy (numpy/scipy)
    import chain.
    """
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, end = decoder.raw_decode(text, start)
        except (json.JSONDecodeError, ValueError):
            start = text.find("{", start + 1)
            continue
        if isinstance(obj, dict):
            yield obj
        start = text.find("{", max(end, start + 1))


def parse_judge_scores(
    text: str, rubric: JudgeRubric = DEFAULT_RUBRIC
) -> dict[str, int] | None:
    """Recover clamped integer scores for every rubric dimension, or ``None``."""
    if not text:
        return None
    for raw in _extract_json_objects(text):
        scores: dict[str, int] = {}
        valid = True
        for name in rubric.dimensions:
            if name not in raw:
                valid = False
                break
            # bool is an int subclass; reject it so a stray ``true``/``false``
            # is treated as malformed rather than silently coerced to 1/0.
            if isinstance(raw[name], bool):
                valid = False
                break
            try:
                val = int(round(float(raw[name])))
            except (TypeError, ValueError):
                valid = False
                break
            scores[name] = max(rubric.scale_min, min(rubric.scale_max, val))
        if valid:
            return scores
    return None


def evaluate_agent(
    agent_id: str,
    messages: list[str],
    provider: ModelProvider,
    *,
    rubric: JudgeRubric = DEFAULT_RUBRIC,
    judge_model: str | None = None,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Run the CoT qualitative judge over an agent's recent messages.

    Args:
        agent_id: Identifier of the agent being evaluated (intentionally shown
            to the judge — this is identity-aware tracking, not a blind metric).
        messages: The agent's recent message texts (last 5 are scored).
        provider: A ``ModelProvider`` (the Claude arm by default); injectable so
            tests run fully offline.
        rubric: Dimensions and scale to score against.
        judge_model: Model id recorded in the result; falls back to the
            provider's ``model``, then the module default.
        max_tokens: Generation budget (room for the CoT preamble + JSON).

    Returns a status dict: ``success`` with ``scores`` + ``thinking``, or one of
    ``skipped`` / ``api_error`` / ``parse_error`` with diagnostic context.
    """
    model_name = judge_model or getattr(provider, "model", None) or DEFAULT_JUDGE_MODEL

    if not messages:
        return {"agent_id": agent_id, "status": "skipped", "reason": "no_messages"}

    prompt = build_judge_prompt(agent_id, messages, rubric)
    try:
        gen = provider.generate(
            [{"role": "user", "content": prompt}],
            seed=None,
            temperature=0.0,  # greedy decoding for reproducible evals
            max_tokens=max_tokens,
            system=_JUDGE_SYSTEM,
        )
    except Exception as exc:  # noqa: BLE001 — surface any provider error, don't crash callers
        return {"agent_id": agent_id, "status": "api_error", "error": str(exc),
                "judge_model": model_name}

    thinking_match = _THINKING_RE.search(gen.text)
    thinking = thinking_match.group(1).strip() if thinking_match else ""
    scores = parse_judge_scores(gen.text, rubric)

    if scores is None:
        return {
            "agent_id": agent_id,
            "status": "parse_error",
            "thinking": thinking,
            "raw_response": gen.text,
            "judge_model": model_name,
        }

    return {
        "agent_id": agent_id,
        "status": "success",
        "scores": scores,
        "thinking": thinking,
        "judge_model": model_name,
    }
