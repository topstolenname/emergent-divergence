"""Multi-agent coordination loop.

Manages the repeated task rounds: assigns tasks, passes messages between agents
in a structured turn order, logs everything, and handles memory writes.

Design: Each round consists of N turns where each agent speaks once per turn.
We run multiple turns per round to allow genuine multi-turn deliberation.
The starting agent rotates every round to eliminate positional bias.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from emergent_divergence.agents.agent import (
    Agent,
    AgentConfig,
    AnthropicBackend,
    ClaudeCodeBackend,
    LLMBackend,
    MockLLMBackend,
)
from emergent_divergence.logging_.events import ExperimentLogger, generate_run_id
from emergent_divergence.memory.store import MemoryStore
from emergent_divergence.tasks.generator import TaskGenerator


@dataclass
class ExperimentConfig:
    """Complete experiment configuration."""

    # Agents
    num_agents: int = 3
    role_biases: list[str] | None = None  # defaults to proposer/critic/synthesizer
    memory_enabled: bool = True
    memory_max_entries: int = 200

    # LLM
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
    temperature: float = 1.0
    backend: str = "anthropic"  # "anthropic" or "mock"

    # Experiment
    num_rounds: int = 30
    turns_per_round: int = 2  # each agent speaks this many times per round
    condition: str = "memory_enabled"
    seed: int | None = 42

    # Paths
    output_dir: str = "data/raw_logs"

    def validate(self) -> None:
        if self.num_agents < 2:
            raise ValueError("Need at least 2 agents")
        if self.role_biases and len(self.role_biases) != self.num_agents:
            raise ValueError("role_biases length must match num_agents")
        if self.backend not in ("anthropic", "claude-code", "mock"):
            raise ValueError(f"Unknown backend: {self.backend!r}. Use 'anthropic', 'claude-code', or 'mock'.")


DEFAULT_ROLES = ["proposer", "critic", "synthesizer"]


def _create_backend(config: ExperimentConfig) -> LLMBackend:
    """Factory: build the right LLM backend from config."""
    if config.backend == "mock":
        return MockLLMBackend(model="mock-v1")
    if config.backend == "claude-code":
        return ClaudeCodeBackend(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
    return AnthropicBackend(
        model=config.model,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )


class ExperimentRunner:
    """Runs the multi-agent coordination experiment."""

    def __init__(self, config: ExperimentConfig):
        config.validate()
        self.config = config
        self.run_id = generate_run_id()
        self.run_dir = Path(config.output_dir) / self.run_id

        # Initialize logger
        self.logger = ExperimentLogger(
            run_dir=self.run_dir,
            run_id=self.run_id,
            condition=config.condition,
        )

        # Initialize LLM backend (shared across all agents)
        self.backend: LLMBackend = _create_backend(config)

        # Initialize agents
        roles = config.role_biases or DEFAULT_ROLES[:config.num_agents]
        if len(roles) < config.num_agents:
            # Cycle roles if fewer than agents
            roles = [roles[i % len(roles)] for i in range(config.num_agents)]

        self.agents: list[Agent] = []
        for i in range(config.num_agents):
            agent_id = f"agent_{i}"
            agent_config = AgentConfig(
                agent_id=agent_id,
                role_bias=roles[i],
                memory_enabled=config.memory_enabled,
            )

            memory = None
            if config.memory_enabled:
                memory_path = self.run_dir / "memory" / f"{agent_id}.jsonl"
                memory = MemoryStore(
                    agent_id=agent_id,
                    persist_path=memory_path,
                    max_entries=config.memory_max_entries,
                )

            self.agents.append(Agent(agent_config, self.backend, memory))

        # Task generator
        self.task_gen = TaskGenerator(seed=config.seed)

        # Log experiment manifest
        self.logger.log("experiment_config", **{
            "num_agents": config.num_agents,
            "role_biases": roles,
            "memory_enabled": config.memory_enabled,
            "model": config.model,
            "backend": config.backend,
            "temperature": config.temperature,
            "num_rounds": config.num_rounds,
            "turns_per_round": config.turns_per_round,
            "seed": config.seed,
        })

    async def run_async(self) -> Path:
        """Execute the full experiment asynchronously. Returns the run directory."""
        print(f"Starting experiment: {self.run_id}")
        print(f"  Condition: {self.config.condition}")
        print(f"  Backend:   {self.config.backend}")
        print(f"  Agents: {self.config.num_agents}, Rounds: {self.config.num_rounds}")
        print(f"  Output: {self.run_dir}")

        try:
            for round_id in range(self.config.num_rounds):
                await self._run_round(round_id)
                print(f"  Round {round_id + 1}/{self.config.num_rounds} complete")
        except KeyboardInterrupt:
            print("\nExperiment interrupted by user.")
            self.logger.log("experiment_interrupted")
        except Exception as e:
            print(f"\nExperiment failed: {e}")
            self.logger.log("experiment_error", error=str(e))
            raise
        finally:
            self.logger.close()

        print(f"Experiment complete. Logs: {self.run_dir / 'events.jsonl'}")
        return self.run_dir

    def run(self) -> Path:
        """Synchronous wrapper for CLI convenience."""
        return asyncio.run(self.run_async())

    async def _run_round(self, round_id: int) -> None:
        """Execute a single round of multi-agent deliberation.

        Turn order rotation: the starting agent index is
        ``round_id % num_agents``, so every agent gets equal time as
        first speaker across the experiment.
        """
        task = self.task_gen.generate(round_id)

        self.logger.log("round_start", round_id=round_id, task_id=task.task_id,
                        claim=task.claim, domain=task.domain, difficulty=task.difficulty)

        # Build the conversation incrementally
        conversation: list[dict[str, str]] = [
            {"role": "user", "content": task.instructions}
        ]

        # ── Turn order rotation ───────────────────────────────────────────
        num_agents = len(self.agents)
        offset = round_id % num_agents
        rotated_agents = self.agents[offset:] + self.agents[:offset]
        # ──────────────────────────────────────────────────────────────────

        for turn in range(self.config.turns_per_round):
            for agent in rotated_agents:
                # Agent generates a response (async)
                result = await agent.respond(conversation, round_id, task.task_id)

                # Log the agent message
                self.logger.log(
                    "agent_message",
                    round_id=round_id,
                    task_id=task.task_id,
                    agent_id=agent.agent_id,
                    agent_role_bias=agent.role_bias,
                    turn=turn,
                    response_text=result["response_text"],
                    latency_s=result["latency_s"],
                    token_count=result["token_count"],
                    memory_reads=result["memory_reads"],
                    model=result["model"],
                )

                # Add to conversation as assistant then user (for next agent to see)
                # We prefix with agent ID so agents can distinguish speakers
                tagged_msg = f"[{agent.agent_id} ({agent.role_bias})]:\n{result['response_text']}"
                conversation.append({"role": "assistant", "content": tagged_msg})
                # Add a follow-up user prompt to continue
                conversation.append({"role": "user", "content": "Continue the discussion. Respond to what was said."})

                # Memory write: agent stores a summary of what happened
                if agent.memory and agent.memory_enabled:
                    # Store a compressed version of their own contribution
                    summary = result["response_text"][:300]
                    agent.write_memory(round_id, summary, source="self")

                    self.logger.log(
                        "memory_write",
                        round_id=round_id,
                        task_id=task.task_id,
                        agent_id=agent.agent_id,
                        content_preview=summary[:100],
                        memory_size=agent.memory.count(),
                    )

        # No-memory condition: clear memory after each round
        if not self.config.memory_enabled:
            for agent in self.agents:
                if agent.memory:
                    agent.memory.clear()

        self.logger.log("round_end", round_id=round_id, task_id=task.task_id,
                        messages_in_round=len(conversation))
