"""Ollama backend: ``llama3.2:3b`` (default) via the local HTTP API.

This is the free arm of the matrix. We hit ``POST /api/chat`` on a locally
running Ollama daemon, pass ``seed`` and ``temperature`` through ``options`` for
reproducibility, and ask for ``num_predict`` (max tokens). Token counts come
from Ollama's ``prompt_eval_count`` / ``eval_count`` usage fields when present,
else a char-based estimate. ``token_ids``/``logprobs`` are left ``None`` — the
chat API does not expose per-token vocabulary distributions, so token-level
influence-delta is handled at the metrics layer the same way it is for Claude.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from emergent_divergence.providers.base import Generation, Message, approx_token_count


class OllamaProvider:
    """Synchronous ``ModelProvider`` for a local Ollama daemon."""

    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.2:3b",
        host: str = "http://localhost:11434",
        *,
        timeout: float = 120.0,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.call_count = 0

    def generate(
        self,
        messages: list[Message],
        *,
        seed: int | None,
        temperature: float,
        max_tokens: int,
        system: str = "",
    ) -> Generation:
        self.call_count += 1

        chat_messages: list[Message] = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        chat_messages.extend(messages)

        options: dict[str, object] = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
        if seed is not None:
            options["seed"] = seed

        payload = {
            "model": self.model,
            "messages": chat_messages,
            "stream": False,
            "options": options,
        }

        data = self._post("/api/chat", payload)

        text = (data.get("message", {}) or {}).get("content", "") or ""
        text = text.strip()

        input_tokens = data.get("prompt_eval_count")
        output_tokens = data.get("eval_count")
        if not isinstance(input_tokens, int):
            input_tokens = approx_token_count(
                system + " " + " ".join(m.get("content", "") for m in messages)
            )
        if not isinstance(output_tokens, int):
            output_tokens = approx_token_count(text)

        return Generation(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider=self.name,
            model=self.model,
            seed=seed,
            token_ids=None,
            logprobs=None,
        )

    def health_check(self) -> bool:
        """Return True if the daemon answers and the model tag is present."""
        try:
            data = self._get("/api/tags")
        except Exception:
            return False
        models = {m.get("name", "") for m in data.get("models", [])}
        # Accept exact tag or the bare name (Ollama may report ``llama3.2:3b``).
        return any(self.model == m or self.model == m.split(":")[0] for m in models)

    # ── HTTP plumbing ──────────────────────────────────────────────────────────

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.host + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Ollama request to {self.host + path} failed: {e}. "
                "Is the daemon running? Try `ollama serve`."
            ) from e

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(self.host + path, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
