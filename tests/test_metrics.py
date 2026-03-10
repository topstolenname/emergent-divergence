"""Tests for divergence metrics."""

from emergent_divergence.metrics.divergence import (
    classify_message_behavior,
    compute_behavioral_divergence,
    compute_behavioral_profiles,
    compute_lexical_uniqueness,
    compute_pairwise_jsd,
    word_frequency_distribution,
)


def _make_messages(agent_id: str, texts: list[str]) -> list[dict]:
    return [
        {"event_type": "agent_message", "agent_id": agent_id, "round_id": i,
         "data": {"response_text": t, "agent_id": agent_id, "round_id": i}}
        for i, t in enumerate(texts)
    ]


def test_word_frequency_distribution():
    dist, vocab = word_frequency_distribution(["the cat sat on the mat"])
    assert len(vocab) > 0
    assert abs(sum(dist) - 1.0) < 0.001


def test_pairwise_jsd_basic():
    messages = {
        "agent_0": _make_messages("agent_0", [
            "I suggest we approach this analytically",
            "Let me propose a framework for analysis",
        ]),
        "agent_1": _make_messages("agent_1", [
            "However I disagree with that approach completely",
            "The flaw in this reasoning is obvious",
        ]),
    }
    jsd = compute_pairwise_jsd(messages)
    assert "agent_0_vs_agent_1" in jsd
    assert jsd["agent_0_vs_agent_1"] > 0


def test_classify_message_behavior():
    scores = classify_message_behavior("I suggest we consider a new approach to this problem")
    assert scores["proposal"] > 0


def test_behavioral_profiles():
    messages = {
        "agent_0": _make_messages("agent_0", [
            "I suggest we try a different approach",
            "What if we considered an alternative solution",
        ]),
        "agent_1": _make_messages("agent_1", [
            "I disagree, the flaw is clear",
            "However this has a major weakness",
        ]),
    }
    profiles = compute_behavioral_profiles(messages)
    assert "agent_0" in profiles
    assert "agent_1" in profiles
    # Proposer should score higher on proposal
    assert profiles["agent_0"]["proposal"] > profiles["agent_1"]["proposal"]
    # Critic should score higher on critique
    assert profiles["agent_1"]["critique"] > profiles["agent_0"]["critique"]


def test_behavioral_divergence():
    profiles = {
        "agent_0": {"proposal": 0.8, "critique": 0.1, "synthesis": 0.1},
        "agent_1": {"proposal": 0.1, "critique": 0.8, "synthesis": 0.1},
    }
    div = compute_behavioral_divergence(profiles)
    assert div > 0


def test_lexical_uniqueness():
    messages = {
        "a": _make_messages("a", ["alpha beta gamma"]),
        "b": _make_messages("b", ["delta epsilon gamma"]),
    }
    uniq = compute_lexical_uniqueness(messages)
    assert uniq["a"] > 0  # alpha, beta are unique to a
    assert uniq["b"] > 0  # delta, epsilon are unique to b
