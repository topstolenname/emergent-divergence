"""Tests for the LLM-as-a-judge behavioral classifier.

All tests run offline: the ``ModelProvider`` is a fake that returns canned JSON,
so no API key or network is required.
"""

from __future__ import annotations

import json

from emergent_divergence.metrics import llm_judge
from emergent_divergence.metrics.divergence import generate_analysis_report
from emergent_divergence.providers.base import Generation


class FakeJudgeProvider:
    """Offline ModelProvider returning a fixed (or scripted) score vector."""

    name = "fake"
    model = "fake-judge"

    def __init__(self, scores=None, replies=None):
        self._scores = scores
        self._replies = list(replies) if replies else None
        self.calls = 0

    def generate(self, messages, *, seed, temperature, max_tokens, system=""):
        self.calls += 1
        if self._replies is not None:
            text = self._replies.pop(0)
        else:
            text = json.dumps(self._scores)
        return Generation(
            text=text, input_tokens=1, output_tokens=1,
            provider=self.name, model=self.model, seed=seed,
        )


def _write_log(tmp_path, agents):
    """Write a minimal events.jsonl with agent_message events; return its path."""
    log_path = tmp_path / "events.jsonl"
    with open(log_path, "w", encoding="utf-8") as f:
        for aid, texts in agents.items():
            for i, text in enumerate(texts):
                event = {
                    "event_type": "agent_message",
                    "round_id": i,
                    "task_id": f"task_{i:04d}",
                    "agent_id": aid,
                    "data": {"agent_id": aid, "round_id": i, "turn": 0,
                             "response_text": text},
                }
                f.write(json.dumps(event) + "\n")
    return log_path


# ── Prompt blindness ──────────────────────────────────────────────────────────

def test_prompt_is_blind_to_identity():
    prompt = llm_judge.build_judge_prompt("Some message text about a claim.")
    lower = prompt.lower()
    # The blind contract: no agent id, role-prior framing, or condition leaks in.
    # (Category names like "critique" are part of the schema and are expected;
    # what must NOT appear is the agent's identity or its assigned role.)
    for forbidden in ("agent_", "assigned role", "role prior", "role bias",
                      "proposer", "synthesizer", "condition", "memory_enabled"):
        assert forbidden not in lower, f"blindness leak: {forbidden!r}"
    assert "Some message text about a claim." in prompt
    # All six categories appear.
    for cat in llm_judge.CATEGORIES:
        assert cat in prompt


def test_categories_match_keyword_classifier():
    from emergent_divergence.metrics.divergence import BEHAVIOR_KEYWORDS
    assert set(llm_judge.CATEGORIES) == set(BEHAVIOR_KEYWORDS.keys())


# ── Response parsing ──────────────────────────────────────────────────────────

def test_parse_valid_json():
    raw = ('{"proposal": 0.9, "critique": 0.1, "synthesis": 0.0, '
           '"verification": 0.2, "recall": 0.0, "clarification": 0.0}')
    scores = llm_judge.parse_judge_response(raw)
    assert scores is not None
    assert scores["proposal"] == 0.9
    assert set(scores) == set(llm_judge.CATEGORIES)


def test_parse_tolerates_surrounding_text():
    raw = ('Here you go:\n```json\n{"proposal": 0.5, "critique": 0.5, '
           '"synthesis": 0.5, "verification": 0.5, "recall": 0.5, '
           '"clarification": 0.5}\n```')
    assert llm_judge.parse_judge_response(raw) is not None


def test_parse_clamps_out_of_range():
    raw = ('{"proposal": 2.0, "critique": -1.0, "synthesis": 0.5, '
           '"verification": 0.5, "recall": 0.5, "clarification": 0.5}')
    scores = llm_judge.parse_judge_response(raw)
    assert scores["proposal"] == 1.0
    assert scores["critique"] == 0.0


def test_parse_rejects_incomplete_schema():
    assert llm_judge.parse_judge_response('{"proposal": 0.5}') is None
    assert llm_judge.parse_judge_response("not json at all") is None


# ── Retry behavior ────────────────────────────────────────────────────────────

def test_classify_message_retries_once_then_succeeds():
    good = ('{"proposal": 0.5, "critique": 0.5, "synthesis": 0.5, '
            '"verification": 0.5, "recall": 0.5, "clarification": 0.5}')
    provider = FakeJudgeProvider(replies=["garbage", good])
    scores = llm_judge.classify_message(provider, "text")
    assert scores is not None
    assert provider.calls == 2


def test_classify_message_returns_none_after_two_failures():
    provider = FakeJudgeProvider(replies=["bad", "still bad"])
    assert llm_judge.classify_message(provider, "text") is None
    assert provider.calls == 2


# ── Run-level classification ──────────────────────────────────────────────────

def test_classify_run_builds_profiles_and_divergence(tmp_path):
    log_path = _write_log(tmp_path, {
        "agent_0": ["m0", "m1"],
        "agent_1": ["m2", "m3"],
    })
    provider = FakeJudgeProvider(scores={
        "proposal": 0.8, "critique": 0.1, "synthesis": 0.0,
        "verification": 0.0, "recall": 0.0, "clarification": 0.0,
    })
    result = llm_judge.classify_run(log_path, provider)
    assert result["total_classifications"] == 4
    assert result["classification_failures"] == 0
    assert set(result["profiles"]) == {"agent_0", "agent_1"}
    assert result["profiles"]["agent_0"]["proposal"] == 0.8
    # Identical scores for both agents -> zero divergence.
    assert result["divergence_score"] == 0.0
    assert result["judge_model"] == "fake-judge"


def test_classify_run_aborts_above_failure_cap(tmp_path):
    log_path = _write_log(tmp_path, {"agent_0": ["a", "b", "c", "d", "e"]})
    provider = FakeJudgeProvider(replies=["bad"] * 20)  # every message fails
    result = llm_judge.classify_run(log_path, provider, max_failure_rate=0.1)
    assert "error" in result
    assert result["classification_failures"] == 5


# ── Agreement ─────────────────────────────────────────────────────────────────

def test_compute_classifier_agreement_shape():
    per_message = [
        {"round_id": 0, "agent_id": "agent_0", "turn": 0,
         "text": "I suggest we propose a new approach and consider options",
         "scores": {"proposal": 0.9, "critique": 0.0, "synthesis": 0.0,
                    "verification": 0.0, "recall": 0.0, "clarification": 0.0}},
        {"round_id": 1, "agent_id": "agent_1", "turn": 0,
         "text": "However I disagree, the flaw and weakness is a clear problem",
         "scores": {"proposal": 0.0, "critique": 0.9, "synthesis": 0.0,
                    "verification": 0.0, "recall": 0.0, "clarification": 0.0}},
    ]
    agreement = llm_judge.compute_classifier_agreement(per_message)
    assert 0.0 <= agreement["top_1_match_rate"] <= 1.0
    assert set(agreement["per_category_agreement"]) == set(llm_judge.CATEGORIES)
    assert "mean_spearman_rank_correlation" in agreement
    assert {"mean", "std", "min", "max"} == set(agreement["per_message_spearman"])
    assert len(agreement["disagreement_examples"]) <= 10


# ── End-to-end via generate_analysis_report ───────────────────────────────────

def test_report_classifier_both_offline(tmp_path):
    log_path = _write_log(tmp_path, {
        "agent_0": ["I suggest we propose and consider a new approach"],
        "agent_1": ["However the flaw and weakness is a clear problem"],
    })
    provider = FakeJudgeProvider(scores={
        "proposal": 0.7, "critique": 0.2, "synthesis": 0.1,
        "verification": 0.0, "recall": 0.0, "clarification": 0.0,
    })
    report = generate_analysis_report(
        log_path, classifier="both", judge_provider=provider,
    )
    # Keyword section always present (backward compatible).
    assert "behavioral_specialization" in report
    # Judge section added.
    assert "behavioral_specialization_llm_judge" in report
    # Agreement added under 'both'.
    assert "classifier_agreement" in report
    # Internal scratch field stripped before serialisation.
    assert "_per_message" not in report["behavioral_specialization_llm_judge"]


def test_report_default_keyword_has_no_judge(tmp_path):
    log_path = _write_log(tmp_path, {"agent_0": ["hello world"]})
    report = generate_analysis_report(log_path)
    assert "behavioral_specialization_llm_judge" not in report
    assert "classifier_agreement" not in report
