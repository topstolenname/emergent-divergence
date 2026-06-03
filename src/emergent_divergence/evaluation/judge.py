"""Optional LLM-as-judge evaluation hooks (early sketch).

NOTE: The implemented LLM-judge *behavioral classifier* now lives in
:mod:`emergent_divergence.metrics.llm_judge` and is wired into ``analyze`` via
the ``--classifier`` flag. That module is the production path: a blind,
six-category classifier parallel to the keyword classifier. The rubric below is
a retained general-purpose sketch (consistency/quality/engagement scoring) and
is intentionally left unwired — prefer the metrics module for divergence work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class JudgeRubric:
    """Scoring rubric for LLM-judge evaluation."""

    dimensions: list[str]
    scale_min: int = 1
    scale_max: int = 5
    instructions: str = ""


DEFAULT_RUBRIC = JudgeRubric(
    dimensions=[
        "role_consistency",      # Does the agent maintain a consistent behavioral tendency?
        "distinctiveness",       # Is this agent distinguishable from the others?
        "contribution_quality",  # Does the agent add value to the discussion?
        "coherence",             # Is the response internally consistent?
        "engagement",            # Does the agent engage with others' points?
    ],
    instructions=(
        "You are evaluating agent messages from a multi-agent coordination experiment. "
        "Score each dimension from 1 (low) to 5 (high). "
        "Be calibrated: 3 means typical/average, not bad."
    ),
)


def build_judge_prompt(agent_id: str, messages: list[str],
                       rubric: JudgeRubric = DEFAULT_RUBRIC) -> str:
    """Build a prompt for LLM-judge scoring (to be called later)."""
    dims = "\n".join(f"  - {d}" for d in rubric.dimensions)
    msgs = "\n---\n".join(messages[-5:])  # last 5 messages

    return (
        f"{rubric.instructions}\n\n"
        f"Agent: {agent_id}\n"
        f"Recent messages:\n{msgs}\n\n"
        f"Evaluate on these dimensions (score {rubric.scale_min}-{rubric.scale_max}):\n{dims}\n\n"
        f"Respond as JSON: {{\"dimension_name\": score, ...}}"
    )


# Placeholder for actual judge execution — wire in when ready
def evaluate_agent(agent_id: str, messages: list[str],
                   rubric: JudgeRubric = DEFAULT_RUBRIC) -> dict[str, Any]:
    """Placeholder: call an LLM to score agent messages against rubric."""
    # TODO: Implement actual LLM call when ready for judge-based evaluation
    return {
        "agent_id": agent_id,
        "status": "not_implemented",
        "rubric_dimensions": rubric.dimensions,
    }
