"""Tests for the CoT qualitative judge (evaluation/judge.py).

Fully offline: the ``ModelProvider`` is a fake returning canned text.
"""

from __future__ import annotations

from emergent_divergence.evaluation import judge
from emergent_divergence.providers.base import Generation


class FakeProvider:
    name = "fake"
    model = "fake-judge"

    def __init__(self, reply: str = "", raise_exc: bool = False):
        self._reply = reply
        self._raise = raise_exc
        self.calls = 0
        self.last_system = None

    def generate(self, messages, *, seed, temperature, max_tokens, system=""):
        self.calls += 1
        self.last_system = system
        if self._raise:
            raise RuntimeError("simulated API failure")
        return Generation(
            text=self._reply, input_tokens=1, output_tokens=1,
            provider=self.name, model=self.model, seed=seed,
        )


_GOOD_REPLY = (
    "<thinking>\nrole_consistency: the agent kept proposing, citing \"let's try\".\n"
    "</thinking>\n"
    '{"role_consistency": 4, "distinctiveness": 3, "contribution_quality": 5, '
    '"coherence": 4, "engagement": 2}'
)


# ── Prompt ────────────────────────────────────────────────────────────────────

def test_prompt_requests_cot_and_lists_dimensions():
    prompt = judge.build_judge_prompt("agent_0", ["a message", "another"])
    assert "<thinking>" in prompt
    assert "<agent_id>agent_0</agent_id>" in prompt
    for dim in judge.DEFAULT_RUBRIC.dimensions:
        assert dim in prompt


# ── Parsing ───────────────────────────────────────────────────────────────────

def test_parse_scores_after_thinking_block():
    scores = judge.parse_judge_scores(_GOOD_REPLY)
    assert scores == {
        "role_consistency": 4, "distinctiveness": 3, "contribution_quality": 5,
        "coherence": 4, "engagement": 2,
    }


def test_parse_clamps_and_rounds_to_scale():
    raw = ('{"role_consistency": 9, "distinctiveness": 0, "contribution_quality": 3.4, '
           '"coherence": 3, "engagement": 3}')
    scores = judge.parse_judge_scores(raw)
    assert scores["role_consistency"] == 5   # clamped to scale_max
    assert scores["distinctiveness"] == 1    # clamped to scale_min
    assert scores["contribution_quality"] == 3  # rounded from 3.4


def test_parse_skips_thinking_braces_and_finds_scores():
    # Braces inside the thinking block must not be mistaken for the score object.
    raw = ('<thinking>consider the set {a, b}</thinking> '
           '{"role_consistency": 3, "distinctiveness": 3, "contribution_quality": 3, '
           '"coherence": 3, "engagement": 3}')
    assert judge.parse_judge_scores(raw) is not None


def test_parse_returns_none_on_incomplete_schema():
    assert judge.parse_judge_scores('{"role_consistency": 4}') is None
    assert judge.parse_judge_scores("no json here") is None


# ── evaluate_agent ────────────────────────────────────────────────────────────

def test_evaluate_agent_success_captures_scores_and_thinking():
    provider = FakeProvider(reply=_GOOD_REPLY)
    result = judge.evaluate_agent("agent_0", ["hello"], provider)
    assert result["status"] == "success"
    assert result["scores"]["contribution_quality"] == 5
    assert "role_consistency" in result["thinking"]
    assert result["judge_model"] == "fake-judge"
    # Greedy decoding for reproducible evals.
    assert "<thinking>" in provider.last_system


def test_evaluate_agent_empty_messages_skips_without_call():
    provider = FakeProvider(reply=_GOOD_REPLY)
    result = judge.evaluate_agent("agent_0", [], provider)
    assert result["status"] == "skipped"
    assert provider.calls == 0


def test_evaluate_agent_parse_error_keeps_raw_and_thinking():
    provider = FakeProvider(reply="<thinking>hmm</thinking> not json")
    result = judge.evaluate_agent("agent_0", ["hi"], provider)
    assert result["status"] == "parse_error"
    assert result["thinking"] == "hmm"
    assert "raw_response" in result


def test_evaluate_agent_provider_exception_is_reported_not_raised():
    provider = FakeProvider(raise_exc=True)
    result = judge.evaluate_agent("agent_0", ["hi"], provider)
    assert result["status"] == "api_error"
    assert "simulated API failure" in result["error"]


def test_evaluate_agent_custom_rubric():
    rubric = judge.JudgeRubric(dimensions={"clarity": "Is it clear?"}, scale_max=3)
    provider = FakeProvider(reply='{"clarity": 7}')  # over scale -> clamps to 3
    result = judge.evaluate_agent("agent_1", ["msg"], provider, rubric=rubric)
    assert result["status"] == "success"
    assert result["scores"] == {"clarity": 3}
