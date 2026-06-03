"""Claude backend: Claude Sonnet via the official Anthropic SDK (the paid arm).

We pin the model string in config (default ``claude-sonnet-4-6``; verify against
current Anthropic listings before a paid run) and capture ``usage`` so cost
accounting uses *real* input/output token counts rather than estimates. Claude
does not honour ``seed`` and is not guaranteed deterministic — that is handled at
the statistics layer (multiple seeds + CIs), and documented in the report.
``token_ids``/``logprobs`` are ``None``: the Messages API exposes no per-token
vocabulary distribution, so token-JSD influence-delta on Claude is Monte-Carlo
empirical (see Methods), not analytic.
"""

from __future__ import annotations

import os
import time

from emergent_divergence.providers.base import Generation, Message, approx_token_count


class ClaudeProvider:
    """Synchronous ``ModelProvider`` wrapping ``anthropic.Anthropic``."""

    name = "claude"

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        *,
        max_retries: int = 4,
        base_delay: float = 2.0,
    ):
        import anthropic

        self._anthropic = anthropic
        self.model = model
        self.max_retries = max_retries
        self.base_delay = base_delay
        # SDK reads ANTHROPIC_API_KEY from env; fail early if absent.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it or add it to .env "
                "before running the Claude (paid) arm."
            )
        self.client = anthropic.Anthropic()
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

        # The Messages API takes ``system`` separately and only user/assistant
        # turns in ``messages`` (no ``seed`` parameter — intentionally dropped).
        api_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("user", "assistant")
        ]

        resp = self._call_with_retry(
            system=system,
            messages=api_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        ).strip()

        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
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

    def _call_with_retry(self, *, system, messages, temperature, max_tokens):
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=messages,
                )
            except (
                self._anthropic.RateLimitError,
                self._anthropic.APIStatusError,
                self._anthropic.APIConnectionError,
            ) as e:
                last_exc = e
                if attempt == self.max_retries - 1:
                    break
                time.sleep(self.base_delay * (2 ** attempt))
        raise RuntimeError(
            f"Claude request failed after {self.max_retries} attempts: {last_exc}"
        ) from last_exc
