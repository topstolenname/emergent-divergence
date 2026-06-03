"""Unit tests for the provider abstraction and the deterministic StubProvider."""

from __future__ import annotations

from emergent_divergence.providers.base import (
    Generation,
    ModelProvider,
    approx_token_count,
)
from emergent_divergence.providers.stub import StubProvider

_MESSAGES = [
    {"role": "user", "content": 'Analyze the claim "markets are efficient".'},
]
_SYSTEM = "You are agent_0. Role bias: proposer."


def test_stub_is_model_provider():
    assert isinstance(StubProvider(), ModelProvider)


def test_generation_fields():
    p = StubProvider()
    g = p.generate(_MESSAGES, seed=42, temperature=1.0, max_tokens=400, system=_SYSTEM)
    assert isinstance(g, Generation)
    assert isinstance(g.text, str) and g.text
    assert g.provider == "stub"
    assert g.model == "stub-v1"
    assert g.seed == 42
    assert g.input_tokens > 0
    assert g.output_tokens > 0


def test_stub_is_deterministic():
    p = StubProvider()
    a = p.generate(_MESSAGES, seed=42, temperature=1.0, max_tokens=400, system=_SYSTEM)
    b = p.generate(_MESSAGES, seed=42, temperature=1.0, max_tokens=400, system=_SYSTEM)
    assert a.text == b.text


def test_stub_varies_with_seed():
    p = StubProvider()
    a = p.generate(_MESSAGES, seed=1, temperature=1.0, max_tokens=400, system=_SYSTEM)
    b = p.generate(_MESSAGES, seed=2, temperature=1.0, max_tokens=400, system=_SYSTEM)
    assert a.text != b.text


def test_stub_varies_with_system():
    p = StubProvider()
    a = p.generate(_MESSAGES, seed=1, temperature=1.0, max_tokens=400,
                   system="You are agent_0. Role bias: proposer.")
    b = p.generate(_MESSAGES, seed=1, temperature=1.0, max_tokens=400,
                   system="You are agent_1. Role bias: critic.")
    assert a.text != b.text


def test_stub_respects_max_tokens():
    p = StubProvider()
    g = p.generate(_MESSAGES, seed=7, temperature=1.0, max_tokens=5, system=_SYSTEM)
    assert len(g.text) <= 5 * 4


def test_stub_call_count_increments():
    p = StubProvider()
    p.generate(_MESSAGES, seed=1, temperature=1.0, max_tokens=100)
    p.generate(_MESSAGES, seed=2, temperature=1.0, max_tokens=100)
    assert p.call_count == 2


def test_approx_token_count():
    assert approx_token_count("") == 0
    assert approx_token_count("hello world") >= 1
