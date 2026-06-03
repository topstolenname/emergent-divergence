"""Dual-backend model provider layer.

A single ``ModelProvider`` abstraction (sync ``generate -> Generation``) with
implementations selected by config:

- ``OllamaProvider`` -> ``llama3.2:3b`` via local Ollama HTTP API (free arm).
- ``ClaudeProvider`` -> Claude Sonnet via the Anthropic SDK (paid arm).
- ``StubProvider``   -> deterministic, offline; used for tests and ``--smoke``.

Embeddings are intentionally *not* a provider concern: all semantic computations
use the shared local MiniLM ``Embedder`` so cross-backend numbers are comparable.
"""

from __future__ import annotations

from emergent_divergence.providers.base import (
    Generation,
    ModelProvider,
    approx_token_count,
)
from emergent_divergence.providers.stub import StubProvider

__all__ = [
    "Generation",
    "ModelProvider",
    "approx_token_count",
    "StubProvider",
    "build_provider",
]


def build_provider(backend: str, cfg: dict | None = None) -> ModelProvider:
    """Factory: construct a provider by backend name from a config dict.

    ``cfg`` is the per-backend mapping (e.g. the ``backends.ollama`` block).
    Imports of the real backends are deferred so the stub path needs no network
    libraries installed.
    """
    cfg = cfg or {}
    backend = backend.lower()
    if backend == "stub":
        return StubProvider(model=cfg.get("model", "stub-v1"))
    if backend == "ollama":
        from emergent_divergence.providers.ollama import OllamaProvider

        return OllamaProvider(
            model=cfg.get("model", "llama3.2:3b"),
            host=cfg.get("host", "http://localhost:11434"),
        )
    if backend == "claude":
        from emergent_divergence.providers.claude import ClaudeProvider

        return ClaudeProvider(model=cfg.get("model", "claude-sonnet-4-6"))
    raise ValueError(
        f"Unknown backend {backend!r}. Use 'ollama', 'claude', or 'stub'."
    )
