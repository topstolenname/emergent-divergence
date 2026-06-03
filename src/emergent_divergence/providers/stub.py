"""Deterministic, offline provider for tests and ``--smoke`` mode.

No network, no API keys. Outputs are a pure function of (seed, system prompt,
conversation), so the same inputs always yield the same text. Two properties are
engineered in deliberately so the *whole* pipeline (incl. influence-delta) exercises
non-trivial structure offline:

1. **Per-agent style drift** — the system prompt (agent id + role bias) steers an
   "own voice" sentence, so agents diverge over rounds.
2. **A built-in influence hub** — every other agent's tagged contribution adds a
   *reflection* span to the output whose length is the agent's weight: ``agent_0``
   has weight 5, everyone else weight 1, and each source contributes its own
   distinctive keyword. Ablating ``agent_0`` from a target's context therefore
   removes ~5 keyword-laden spans (a large embedding/token shift), while ablating
   any other source removes one. The influence matrix thus has a genuine hub
   (largest row sum, positive asymmetry) rather than noise — monotonically, not via
   a modulo accident.
"""

from __future__ import annotations

import hashlib
import re

from emergent_divergence.providers.base import Generation, Message, approx_token_count

_OPENERS = [
    "Looking at this from a structural angle,",
    "I want to push back on the framing here:",
    "Building on what was said,",
    "Let me offer a concrete counterexample.",
    "There is an important dimension being missed.",
    "Stepping back to first principles,",
    "The evidence cuts both ways, but",
    "I think the disagreement is really about scope.",
]
_MIDDLES = [
    "the claim about {topic} holds only under fairly narrow conditions,",
    "the strongest case for {topic} depends on assumptions we have not tested,",
    "any honest assessment of {topic} has to weigh the counterfactual,",
    "the data we would need to settle {topic} simply is not in front of us,",
    "the practical tradeoffs around {topic} dominate the abstract argument,",
    "the question of {topic} is less binary than the prompt suggests,",
]
_CLOSERS = [
    "so I would qualify the conclusion rather than accept it outright.",
    "and that asymmetry is exactly where the synthesis should focus.",
    "which means we should hold the position provisionally.",
    "so the burden of proof has not really been met yet.",
    "and reconciling those views is the productive path forward.",
    "so I lean toward a partial, conditional endorsement.",
]
_ROLE_FLAVOR = {
    "proposer": "Here is a fresh angle worth opening up:",
    "critic": "The weak point that needs scrutiny is this:",
    "synthesizer": "Pulling the threads together,",
    "generic": "",
}

# Distinctive vocabulary so each source's reflection is lexically identifiable;
# removing a source removes *its* words, shifting the embedding measurably.
_KEYWORDS = [
    "incentives", "falsifiability", "externalities", "path-dependence",
    "selection-effects", "base-rates", "tail-risk", "second-order",
    "coordination", "legibility", "counterfactual", "robustness",
    "heterogeneity", "confounders", "equilibrium", "feedback-loops",
]
_REFLECT = [
    "Picking up the point about {kw}, I think it deserves more weight.",
    "On {kw}, the argument so far understates the difficulty.",
    "The thread about {kw} is where this conversation actually turns.",
    "I keep returning to {kw} because it reframes the whole question.",
    "If we take {kw} seriously, the earlier consensus looks shakier.",
]


def _digest_int(s: str) -> int:
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:12], 16)


def _topic_from_messages(messages: list[Message], system: str) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if '"' in content:
                parts = content.split('"')
                if len(parts) >= 2 and parts[1].strip():
                    claim = parts[1].strip()
                    return (claim[:70]).rstrip(". ")
    return "the central claim"


def _role_from_system(system: str) -> str:
    s = system.lower()
    for role in ("proposer", "critic", "synthesizer"):
        if role in s:
            return role
    return "generic"


_TAG_RE = re.compile(r"\[(agent_\d+)[^\]]*\]:\s*(.*?)(?=(?:\n\[agent_\d+)|\Z)", re.S)


def _present_sources(messages: list[Message]) -> list[tuple[int, str]]:
    """Return ``(agent_index, body_digest_keyword)`` for each present contribution."""
    blob = "\n".join(m.get("content", "") for m in messages)
    out: list[tuple[int, str]] = []
    for tag, body in _TAG_RE.findall(blob):
        body = body.strip()
        if not body or body == "[no input]":
            continue
        idx = int(tag.split("_")[1])
        kw = _KEYWORDS[_digest_int(body) % len(_KEYWORDS)]
        out.append((idx, kw))
    return out


def _reflection_text(messages: list[Message]) -> str:
    """Build the influence-bearing span: agent_0 weight 5, others weight 1."""
    spans: list[str] = []
    for idx, kw in _present_sources(messages):
        weight = 5 if idx == 0 else 1
        seed = _digest_int(f"{idx}|{kw}")
        for w in range(weight):
            tmpl = _REFLECT[(seed + w) % len(_REFLECT)]
            spans.append(tmpl.format(kw=kw))
    return " ".join(spans)


class StubProvider:
    """Deterministic offline provider implementing the ModelProvider Protocol."""

    name = "stub"

    def __init__(self, model: str = "stub-v1"):
        self.model = model
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
        topic = _topic_from_messages(messages, system)
        role = _role_from_system(system)

        # "Own voice": varies by seed + system (agent id + role) + context depth.
        base = _digest_int(f"{seed}|{system}|{len(messages)}")
        opener = _OPENERS[base % len(_OPENERS)]
        middle = _MIDDLES[(base // 7) % len(_MIDDLES)].format(topic=topic)
        closer = _CLOSERS[(base // 53) % len(_CLOSERS)]
        flavor = _ROLE_FLAVOR.get(role, "")
        own = " ".join(p for p in (flavor, opener, middle, closer) if p)

        # Influence-bearing reflection of the present sources (the hub structure).
        reflection = _reflection_text(messages)
        text = own if not reflection else f"{own} {reflection}"

        # Respect max_tokens roughly (chars ~ 4*tokens).
        max_chars = max_tokens * 4
        if len(text) > max_chars:
            text = text[:max_chars].rstrip()

        input_tokens = approx_token_count(system + " " + " ".join(
            m.get("content", "") for m in messages
        ))
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
