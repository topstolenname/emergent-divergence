"""Task generation for the experiment.

Uses a single task family: collaborative claim analysis.
Tasks require multiple turns, partial disagreement, refinement, and synthesis.
Each task presents a debatable claim and asks agents to analyze it collaboratively.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any


# ── Claim Bank ────────────────────────────────────────────────────────────────
# Claims are designed to be non-trivial, requiring genuine deliberation.
# They span domains to prevent task-specific overfitting.

CLAIM_BANK: list[dict[str, Any]] = [
    {
        "claim": "Automated code review tools will replace human code reviewers within 5 years.",
        "domain": "technology",
        "difficulty": "medium",
    },
    {
        "claim": "Universal basic income would reduce innovation by lowering economic pressure to work.",
        "domain": "economics",
        "difficulty": "hard",
    },
    {
        "claim": "The replication crisis in psychology has been largely resolved by pre-registration mandates.",
        "domain": "science",
        "difficulty": "medium",
    },
    {
        "claim": "Decentralized social networks will never achieve mainstream adoption.",
        "domain": "technology",
        "difficulty": "medium",
    },
    {
        "claim": "Teaching critical thinking skills is more effective than teaching domain-specific knowledge.",
        "domain": "education",
        "difficulty": "hard",
    },
    {
        "claim": "Remote work leads to measurably lower team cohesion compared to in-office work.",
        "domain": "organizational",
        "difficulty": "medium",
    },
    {
        "claim": "Open source software development produces higher quality code than proprietary development.",
        "domain": "technology",
        "difficulty": "medium",
    },
    {
        "claim": "Carbon capture technology is a distraction from emissions reduction efforts.",
        "domain": "environment",
        "difficulty": "hard",
    },
    {
        "claim": "Standardized testing is the most reliable predictor of academic success.",
        "domain": "education",
        "difficulty": "medium",
    },
    {
        "claim": "Microservices architecture is overused and monoliths are better for most organizations.",
        "domain": "technology",
        "difficulty": "medium",
    },
    {
        "claim": "Peer review as currently practiced is fundamentally broken and should be replaced.",
        "domain": "science",
        "difficulty": "hard",
    },
    {
        "claim": "Emotional intelligence is a better predictor of leadership effectiveness than IQ.",
        "domain": "organizational",
        "difficulty": "medium",
    },
    {
        "claim": "Most cybersecurity breaches are caused by human error rather than technical vulnerabilities.",
        "domain": "technology",
        "difficulty": "easy",
    },
    {
        "claim": "Agile methodology is unsuitable for safety-critical software development.",
        "domain": "engineering",
        "difficulty": "hard",
    },
    {
        "claim": "The scientific community systematically undervalues negative results.",
        "domain": "science",
        "difficulty": "medium",
    },
    {
        "claim": "Competitive markets always produce better outcomes than regulated alternatives.",
        "domain": "economics",
        "difficulty": "hard",
    },
    {
        "claim": "Sleep deprivation is a larger public health crisis than obesity.",
        "domain": "health",
        "difficulty": "medium",
    },
    {
        "claim": "Programming language choice has minimal impact on software project success.",
        "domain": "technology",
        "difficulty": "medium",
    },
    {
        "claim": "Democratic decision-making leads to worse outcomes than expert-driven decisions in technical domains.",
        "domain": "governance",
        "difficulty": "hard",
    },
    {
        "claim": "Most organizational meetings could be replaced by asynchronous communication without productivity loss.",
        "domain": "organizational",
        "difficulty": "easy",
    },
]


@dataclass
class Task:
    """A single claim analysis task."""

    task_id: str
    claim: str
    domain: str
    difficulty: str
    round_id: int
    instructions: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "claim": self.claim,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "round_id": self.round_id,
            "instructions": self.instructions,
        }


class TaskGenerator:
    """Generates tasks for experiment rounds."""

    def __init__(self, claims: list[dict[str, Any]] | None = None, seed: int | None = None):
        self.claims = claims or CLAIM_BANK
        self.rng = random.Random(seed)
        self._used_indices: list[int] = []

    def generate(self, round_id: int) -> Task:
        """Generate a task for a given round, cycling through claims."""
        # Cycle through claims, reshuffling when exhausted
        if not self._used_indices:
            self._used_indices = list(range(len(self.claims)))
            self.rng.shuffle(self._used_indices)

        idx = self._used_indices.pop(0)
        claim_data = self.claims[idx]

        task_id = f"task_{round_id:04d}_{uuid.uuid4().hex[:6]}"

        instructions = (
            f"Analyze the following claim collaboratively:\n\n"
            f'"{claim_data["claim"]}"\n\n'
            f"Your group should:\n"
            f"1. Evaluate the claim's validity with evidence and reasoning\n"
            f"2. Identify the strongest arguments for and against\n"
            f"3. Note key uncertainties or missing information\n"
            f"4. Arrive at a nuanced group assessment\n\n"
            f"Engage with each other's points. Disagree where warranted. "
            f"Build on good ideas. Challenge weak reasoning."
        )

        return Task(
            task_id=task_id,
            claim=claim_data["claim"],
            domain=claim_data["domain"],
            difficulty=claim_data["difficulty"],
            round_id=round_id,
            instructions=instructions,
        )
