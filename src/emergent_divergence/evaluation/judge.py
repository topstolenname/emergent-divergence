"""Optional LLM-as-judge evaluation hooks.

Not required for v1 but the interface is defined here so it can be
wired in later without restructuring.
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
