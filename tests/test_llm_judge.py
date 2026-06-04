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


def test_parse_handles_trailing_brace_block():
    # A greedy {.*} would capture through the second brace block and fail to
    # parse; raw_decode stops at the first complete object.
    raw = ('{"proposal": 0.3, "critique": 0.3, "synthesis": 0.3, '
           '"verification": 0.3, "recall": 0.3, "clarification": 0.3}\n'
           "Note: scores are independent {see rubric}.")
    scores = llm_judge.parse_judge_response(raw)
    assert scores is not None
    assert scores["proposal"] == 0.3


def test_parse_skips_leading_non_object_brace():
    # First "{...}" is not a dict of scores; parser should find the real one.
    raw = '{not valid} then {"proposal": 0.1, "critique": 0.1, "synthesis": 0.1, ' \
          '"verification": 0.1, "recall": 0.1, "clarification": 0.1}'
    scores = llm_judge.parse_judge_response(raw)
    assert scores is not None
    assert scores["critique"] == 0.1


def test_parse_skips_leading_offschema_object():
    # A valid JSON object that doesn't match the schema must not mask a later
    # schema-compliant score object.
    raw = ('{"status": "ok", "note": "scores follow"} '
           '{"proposal": 0.4, "critique": 0.4, "synthesis": 0.4, '
           '"verification": 0.4, "recall": 0.4, "clarification": 0.4}')
    scores = llm_judge.parse_judge_response(raw)
    assert scores is not None
    assert scores["proposal"] == 0.4


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


def test_classify_message_empty_text_skips_api_call():
    provider = FakeJudgeProvider(scores={c: 0.9 for c in llm_judge.CATEGORIES})
    scores = llm_judge.classify_message(provider, "   \n  ")
    assert scores == {c: 0.0 for c in llm_judge.CATEGORIES}
    assert provider.calls == 0  # no tokens spent on an empty message


class _RaisingProvider:
    name = "raising"
    model = "raising-judge"

    def __init__(self):
        self.calls = 0

    def generate(self, messages, *, seed, temperature, max_tokens, system=""):
        self.calls += 1
        raise RuntimeError("simulated API failure")


def test_classify_message_provider_exception_is_failure_not_crash():
    provider = _RaisingProvider()
    assert llm_judge.classify_message(provider, "real text") is None
    assert provider.calls == 2  # both attempts tried, then recorded as failure


def test_classify_run_survives_provider_exceptions(tmp_path):
    log_path = _write_log(tmp_path, {"agent_0": ["a", "b"]})
    # All calls raise -> failures hit the cap and the run bails out cleanly
    # (no crash) on the first failure rather than judging everything.
    result = llm_judge.classify_run(log_path, _RaisingProvider(), max_failure_rate=0.1)
    assert "error" in result
    assert result["classification_failures"] == 1


def test_classify_run_aborts_early_on_unrecoverable_failures(tmp_path):
    # 10 messages, 10% cap -> max 1 failure tolerated. With every call failing,
    # the run must bail out before judging all 10 (each costs 2 attempts).
    log_path = _write_log(tmp_path, {"agent_0": [f"m{i}" for i in range(10)]})
    provider = _RaisingProvider()
    result = llm_judge.classify_run(log_path, provider, max_failure_rate=0.1)
    assert "error" in result
    assert "aborted early" in result["error"]
    # Stopped after the 2nd failure (cap=1.0), not after all 10 messages.
    assert result["classification_failures"] == 2
    assert provider.calls == 4  # 2 messages x 2 attempts


def test_event_field_preserves_falsy_round_id_and_turn(tmp_path):
    # round_id=0 / turn=0 are valid first-round values and must survive.
    log_path = tmp_path / "events.jsonl"
    event = {
        "event_type": "agent_message", "round_id": 0, "task_id": "task_0",
        "agent_id": "agent_0",
        "data": {"agent_id": "agent_0", "turn": 0, "response_text": "hello"},
    }
    log_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    provider = FakeJudgeProvider(scores={c: 0.5 for c in llm_judge.CATEGORIES})
    result = llm_judge.classify_run(log_path, provider)
    rec = result["classifications"]["agent_0"][0]
    assert rec["round_id"] == 0
    assert rec["turn"] == 0


def test_event_field_handles_null_data():
    # A "data" field explicitly set to null must not raise AttributeError.
    assert llm_judge._event_field({"data": None}, "round_id") is None
    assert llm_judge._event_field({"round_id": 5, "data": None}, "round_id") == 5
    assert llm_judge._event_field({"data": {"turn": 2}}, "turn") == 2
    assert llm_judge._get_text({"data": None}) == ""


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
    # 5 messages, cap 0.1 -> tolerates <1 failure, so it bails on the first.
    assert result["classification_failures"] == 1


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


def test_report_rejects_unknown_classifier(tmp_path):
    import pytest
    log_path = _write_log(tmp_path, {"agent_0": ["hello world"]})
    with pytest.raises(ValueError, match="Unknown classifier"):
        generate_analysis_report(log_path, classifier="bogus")


# ── Integration: classify_run over mixed judge replies ────────────────────────

def test_classify_run_mixed_quality_replies(tmp_path):
    """End-to-end run where the judge returns a realistic mix of replies:
    clean JSON, garbage-then-retry, an off-schema leading block, and one
    message that fails both attempts (tolerated under a relaxed cap)."""
    good = ('{"proposal": 0.6, "critique": 0.2, "synthesis": 0.1, '
            '"verification": 0.1, "recall": 0.0, "clarification": 0.0}')
    fenced = ("```json\n"
              '{"proposal": 0.1, "critique": 0.7, "synthesis": 0.1, '
              '"verification": 0.1, "recall": 0.0, "clarification": 0.0}\n```')
    offschema_then_good = (
        '{"status": "ok"} then the scores: '
        '{"proposal": 0.0, "critique": 0.0, "synthesis": 0.9, '
        '"verification": 0.1, "recall": 0.0, "clarification": 0.0}')

    log_path = _write_log(tmp_path, {"agent_0": ["m1", "m2", "m3", "m4"]})
    # Call order: m1(1) -> m2(2, retry) -> m3(1) -> m4(2, both fail).
    provider = FakeJudgeProvider(replies=[
        good,                  # m1: clean
        "garbage", fenced,     # m2: bad, then retry succeeds (markdown fence)
        offschema_then_good,   # m3: leading off-schema object, then real scores
        "nope", "still nope",  # m4: both attempts fail
    ])

    # 4 messages, cap 0.5 -> tolerates up to 2 failures, so the single failure
    # does not abort the run.
    result = llm_judge.classify_run(log_path, provider, max_failure_rate=0.5)

    assert "error" not in result
    assert result["total_classifications"] == 4
    assert result["classification_failures"] == 1
    # Three successful classifications contribute to the profile.
    prof = result["profiles"]["agent_0"]
    assert set(prof) == set(llm_judge.CATEGORIES)
    # m3's synthesis-heavy scores were recovered despite the leading block.
    assert prof["synthesis"] > 0
    # The failed message is recorded with null scores in the classifications.
    null_scores = [m for m in result["classifications"]["agent_0"] if m["scores"] is None]
    assert len(null_scores) == 1
