"""Agent instances that wrap a shared base model with per-agent role bias + memory.

Key design principles (unchanged from v1):
- All agents in a cell share the SAME base model (no model heterogeneity).
- Role priors are *weak* biases, not hard-scripted pipelines.
- The model is the sole driver of behaviour — no cognitive engine, no
  personality-vector math, no message-type pre-selection.

v2 change: agents drive a synchronous ``ModelProvider`` (``generate -> Generation``)
instead of the old async ``LLMBackend.complete -> str``. This gives clean
token/cost accounting and makes ablation replay (counterfactual re-generation of a
single agent's turn) straightforward.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from emergent_divergence.memory.store import MemoryStore
from emergent_divergence.providers.base import Generation, Message, ModelProvider

# ── Role Bias Definitions ─────────────────────────────────────────────────────

ROLE_BIASES: dict[str, str] = {
    "proposer": (
        "You tend to generate initial ideas, propose solutions, and introduce "
        "new framings. You enjoy opening up the solution space."
    ),
    "critic": (
        "You tend to evaluate proposals critically, identify weaknesses, and "
        "push for rigor. You value precision and skepticism."
    ),
    "synthesizer": (
        "You tend to integrate perspectives, find common ground, and build "
        "composite solutions. You value coherence and completeness."
    ),
    "generic": "",  # No role bias — used by Condition C (zero_role_bias).
}


@dataclass
class AgentConfig:
    agent_id: str
    role_bias: str  # key into ROLE_BIASES
    memory_enabled: bool = True


class Agent:
    """A single agent instance with role bias, optional memory, shared provider."""

    def __init__(
        self,
        config: AgentConfig,
        provider: ModelProvider,
        memory: MemoryStore | None = None,
        *,
        temperature: float = 1.0,
        max_tokens: int = 400,
        memory_read_limit: int = 10,
    ):
        self.agent_id = config.agent_id
        self.role_bias = config.role_bias
        self.role_bias_text = ROLE_BIASES.get(config.role_bias, "")
        self.memory_enabled = config.memory_enabled
        self.provider = provider
        self.memory = memory if config.memory_enabled else None
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_read_limit = memory_read_limit

        self.total_messages_sent = 0
        self.total_tokens_generated = 0

    def build_system_prompt(self, round_id: int) -> str:
        """Construct the system prompt: weak role bias + recent memory context."""
        parts = [
            f"You are Agent {self.agent_id}, participating in round {round_id} "
            f"of a collaborative, multi-turn deliberation with other agents.",
        ]
        if self.role_bias_text:
            parts += [
                "",
                f"Your natural tendency: {self.role_bias_text}",
                "",
                "This is a slight inclination, not a rigid rule. Respond naturally "
                "based on the conversation.",
            ]
        else:
            parts += [
                "",
                "Respond naturally based on the conversation.",
            ]

        if self.memory is not None and self.memory_enabled:
            memories = self.memory.get_recent(limit=self.memory_read_limit)
            if memories:
                parts.append("")
                parts.append("Your notes from prior rounds:")
                for m in memories:
                    parts.append(
                        f"  [Round {m.get('round_id', '?')}] {m.get('content', '')}"
                    )

        return "\n".join(parts)

    def respond(
        self,
        conversation: list[Message],
        round_id: int,
        task_id: str,
        *,
        seed: int | None,
        turn: int = 0,
        system_override: str | None = None,
    ) -> dict[str, Any]:
        """Generate one turn. Returns logging metadata plus the raw ``Generation``.

        ``system_override`` lets the influence probe pin a canonical system prompt;
        normal rounds pass ``None`` and use ``build_system_prompt``.
        """
        system = (
            system_override
            if system_override is not None
            else self.build_system_prompt(round_id)
        )
        memory_reads = 0
        if self.memory is not None and self.memory_enabled:
            memory_reads = len(self.memory.get_recent(limit=self.memory_read_limit))

        t0 = time.time()
        gen: Generation = self.provider.generate(
            conversation,
            seed=seed,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            system=system,
        )
        latency = time.time() - t0

        self.total_messages_sent += 1
        self.total_tokens_generated += gen.output_tokens

        return {
            "agent_id": self.agent_id,
            "role_bias": self.role_bias,
            "response_text": gen.text,
            "round_id": round_id,
            "task_id": task_id,
            "turn": turn,
            "latency_s": round(latency, 3),
            "input_tokens": gen.input_tokens,
            "output_tokens": gen.output_tokens,
            "model": gen.model,
            "provider": gen.provider,
            "seed": seed,
            "generation": gen,
        }

    def write_memory(self, round_id: int, content: str, source: str = "self") -> None:
        """Store a memory entry if memory is enabled."""
        if self.memory is not None and self.memory_enabled:
            self.memory.add(
                {
                    "round_id": round_id,
                    "content": content,
                    "source": source,
                    "agent_id": self.agent_id,
                    "timestamp": time.time(),
                }
            )
