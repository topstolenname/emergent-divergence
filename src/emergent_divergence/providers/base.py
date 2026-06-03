"""Provider interface: the ``Generation`` record and the ``ModelProvider`` Protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# A message is a {"role": "system"|"user"|"assistant", "content": str} mapping.
Message = dict[str, str]


@dataclass
class Generation:
    """The result of one model call, normalised across backends.

    ``token_ids`` / ``logprobs`` are populated only when the backend exposes them
    (Ollama *may*; Claude does not). ``input_tokens``/``output_tokens`` come from
    the backend's usage accounting when available, else a char-based estimate, and
    drive cost accounting.
    """

    text: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str
    seed: int | None = None
    token_ids: list[int] | None = None
    logprobs: list[float] | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "provider": self.provider,
            "model": self.model,
            "seed": self.seed,
            "has_token_ids": self.token_ids is not None,
            "has_logprobs": self.logprobs is not None,
        }


@runtime_checkable
class ModelProvider(Protocol):
    """Synchronous provider contract.

    All agents share one provider instance per cell (same base model). ``generate``
    must be deterministic given ``seed`` where the backend supports it (Ollama,
    Stub); Claude does not guarantee determinism and that is handled at the
    statistics layer (multiple seeds + CIs).
    """

    name: str
    model: str

    def generate(
        self,
        messages: list[Message],
        *,
        seed: int | None,
        temperature: float,
        max_tokens: int,
        system: str = "",
    ) -> Generation:
        ...


def approx_token_count(text: str) -> int:
    """Backend-agnostic token estimate (~4 chars/token), floored at 1 for non-empty."""
    if not text:
        return 0
    return max(1, len(text) // 4)
