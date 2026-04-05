"""Agent instances that wrap a shared base LLM with per-agent role bias and memory.

Key design principles:
- All agents use the SAME model (no model heterogeneity)
- Role priors are weak biases, not hard-scripted pipelines
- Every LLM call is captured for logging
- No cognitive engine, no personality vectors — the LLM is the sole driver of behavior
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from emergent_divergence.memory.store import MemoryStore


# ── LLM Backend Protocol ──────────────────────────────────────────────────────

@runtime_checkable
class LLMBackend(Protocol):
    """Protocol for swappable async LLM backends."""

    async def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Send messages and return the completion text."""
        ...

    @property
    def model_name(self) -> str: ...

    def token_count(self, text: str) -> int | None:
        """Optional token counting."""
        ...


# ── Anthropic Backend ─────────────────────────────────────────────────────────

class AnthropicBackend:
    """Claude API backend using the async client."""

    def __init__(self, model: str = "claude-sonnet-4-20250514",
                 max_tokens: int = 1024, temperature: float = 1.0):
        import anthropic
        self.client = anthropic.AsyncAnthropic()
        self._model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        system = kwargs.get("system", "")
        response = await self.client.messages.create(
            model=self._model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    def token_count(self, text: str) -> int | None:
        try:
            import tiktoken
            enc = tiktoken.encoding_for_model("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return None


# ── Claude Code Backend ──────────────────────────────────────────────────────

class ClaudeCodeBackend:
    """Backend that routes through Claude Code CLI, billed to a Max/Pro subscription.

    This avoids requiring separate API credits by using the `claude` CLI's
    `--print` mode, which authenticates via the user's claude.ai login.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514",
                 max_tokens: int = 1024, temperature: float = 1.0):
        import shutil
        # Find claude in common locations
        self._claude_path = (
            shutil.which("claude")
            or shutil.which("claude", path=f"{Path.home()}/.npm-global/bin")
        )
        if not self._claude_path:
            raise RuntimeError(
                "Claude Code CLI not found. Install with: "
                "npm install -g @anthropic-ai/claude-code"
            )
        self._model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        import asyncio

        system = kwargs.get("system", "")

        # Build a single prompt from the conversation history
        prompt_parts = []
        if system:
            prompt_parts.append(f"[System instructions]\n{system}\n")
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                prompt_parts.append(f"[User]: {content}")
            elif role == "assistant":
                prompt_parts.append(f"[Assistant]: {content}")
        prompt = "\n\n".join(prompt_parts)

        # Call claude CLI with --print for non-interactive single-shot mode
        # Use stdin piping to avoid arg length limits with long prompts
        cmd = [
            self._claude_path,
            "--print",
            "--output-format", "text",
            "--model", self._model,
            "--max-turns", "1",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=prompt.encode())

        if proc.returncode != 0:
            err = stderr.decode().strip() or stdout.decode().strip()
            raise RuntimeError(f"Claude Code CLI error (exit {proc.returncode}): {err[:500]}")

        return stdout.decode().strip()

    def token_count(self, text: str) -> int | None:
        # Rough approximation
        return max(1, len(text) // 4)


# ── Mock Backend ──────────────────────────────────────────────────────────────

class MockLLMBackend:
    """Deterministic mock backend for integration testing without API costs.

    Generates varied but reproducible responses based on a hash of the input
    messages, so the same conversation always produces the same output.
    No cognitive engine, no personality math — just stable fake text.
    """

    def __init__(self, model: str = "mock-v1", latency: float = 0.0):
        self._model = model
        self._latency = latency
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        self.call_count += 1
        system = kwargs.get("system", "")

        # Build a deterministic seed from the full input so repeated runs
        # with the same conversation produce identical outputs.
        hash_input = system + "||" + "||".join(
            f"{m.get('role', '')}:{m.get('content', '')}" for m in messages
        )
        digest = hashlib.sha256(hash_input.encode()).hexdigest()
        seed_int = int(digest[:8], 16)

        topic = self._topic_from_messages(messages)

        # Rotate through response templates keyed on seed
        templates = [
            (
                f"Looking at this from a different angle, I think the key issue is "
                f"whether we have sufficient evidence. The claim touches on "
                f"{topic}, which requires careful analysis. "
                f"I'd argue we need to consider both the empirical data and the "
                f"theoretical framework before reaching any conclusion."
            ),
            (
                f"I want to push back on some of what's been said. While the argument "
                f"has merit, it overlooks a critical factor: the context dependency of "
                f"{topic}. We should distinguish between "
                f"the general principle and the specific application being discussed here."
            ),
            (
                f"Building on the points raised so far, I see a way to reconcile the "
                f"different perspectives. The disagreement seems to center on scope — "
                f"whether {topic} applies universally or "
                f"only under certain conditions. I think both sides have valid elements."
            ),
            (
                f"Let me offer a concrete example that might clarify things. When we "
                f"look at real-world cases of {topic}, "
                f"we often see mixed results. This suggests the claim is partially true "
                f"but needs significant qualification."
            ),
            (
                f"I think we're missing an important dimension here. The question isn't "
                f"just whether {topic} is true, but under "
                f"what conditions and with what tradeoffs. The literature on this is "
                f"more nuanced than a simple yes-or-no framing suggests."
            ),
        ]

        response = templates[seed_int % len(templates)]

        # Simulate latency if configured
        if self._latency > 0:
            import asyncio
            await asyncio.sleep(self._latency)

        return response

    def token_count(self, text: str) -> int | None:
        # Rough approximation: ~4 chars per token
        return max(1, len(text) // 4)

    @staticmethod
    def _topic_from_messages(messages: list[dict[str, str]]) -> str:
        """Extract a short topic phrase from the first user message."""
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                # Grab the first clause after a quote mark, or first 60 chars
                if '"' in content:
                    parts = content.split('"')
                    if len(parts) >= 2:
                        claim = parts[1]
                        return claim[:80] if len(claim) > 80 else claim
                return content[:60].rstrip(". ")
        return "this topic"


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
}


# ── Agent ─────────────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    agent_id: str
    role_bias: str  # key into ROLE_BIASES
    memory_enabled: bool = True


class Agent:
    """A single LLM agent instance with role bias and optional memory.

    The LLM system prompt is the sole driver of behavior. There is no cognitive
    engine, no personality vector math, and no message-type pre-selection.
    """

    def __init__(self, config: AgentConfig, backend: LLMBackend,
                 memory: MemoryStore | None = None):
        self.agent_id = config.agent_id
        self.role_bias = config.role_bias
        self.role_bias_text = ROLE_BIASES.get(config.role_bias, "")
        self.memory_enabled = config.memory_enabled
        self.backend = backend
        self.memory = memory if config.memory_enabled else None

        # Interaction counters for logging
        self.total_messages_sent = 0
        self.total_tokens_generated = 0

    def build_system_prompt(self, round_id: int) -> str:
        """Construct the system prompt with weak role bias and memory context."""
        parts = [
            f"You are Agent {self.agent_id}, participating in round {round_id} "
            f"of a collaborative task with other agents.",
            "",
            f"Your natural tendency: {self.role_bias_text}" if self.role_bias_text else "",
            "",
            "This is a slight inclination, not a rigid rule. "
            "Respond naturally based on the conversation.",
        ]

        if self.memory and self.memory_enabled:
            memories = self.memory.get_recent(limit=10)
            if memories:
                parts.append("")
                parts.append("Your notes from prior rounds:")
                for m in memories:
                    parts.append(f"  [Round {m.get('round_id', '?')}] {m.get('content', '')}")

        return "\n".join(parts)

    async def respond(self, conversation: list[dict[str, str]], round_id: int,
                      task_id: str) -> dict[str, Any]:
        """Generate a response given the conversation context.

        Returns a dict with the response text and metadata for logging.
        """
        system = self.build_system_prompt(round_id)
        memory_reads = 0
        if self.memory and self.memory_enabled:
            memory_reads = len(self.memory.get_recent(limit=10))

        t0 = time.time()
        response_text = await self.backend.complete(conversation, system=system)
        latency = time.time() - t0

        token_count = self.backend.token_count(response_text)
        self.total_messages_sent += 1
        if token_count:
            self.total_tokens_generated += token_count

        return {
            "agent_id": self.agent_id,
            "role_bias": self.role_bias,
            "response_text": response_text,
            "round_id": round_id,
            "task_id": task_id,
            "latency_s": round(latency, 3),
            "token_count": token_count,
            "memory_reads": memory_reads,
            "model": self.backend.model_name,
        }

    def write_memory(self, round_id: int, content: str, source: str = "self") -> None:
        """Store a memory entry if memory is enabled."""
        if self.memory and self.memory_enabled:
            self.memory.add({
                "round_id": round_id,
                "content": content,
                "source": source,
                "agent_id": self.agent_id,
                "timestamp": time.time(),
            })
