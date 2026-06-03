"""LLM-as-a-judge behavioral classifier (analysis-side, parallel to keywords).

Closes the "LLM-judge behavioral classifier" gap from
``docs/superpowers/specs/2026-03-10-pre-control-gap-closure-design.md`` (§6).

Design contract (kept deliberately narrow so it cannot perturb experiments):

* **Analysis only.** Runs as a post-processing step over a completed run's
  ``events.jsonl``. It never touches the runner loop or the log format.
* **Blind judge.** The judge prompt contains ONLY the message text — no agent
  ID, role bias, condition, run label, generating model, or round number. This
  is what makes the score a measurement rather than a restatement of the prior
  we are trying to detect.
* **Shared schema.** The six categories are identical to the keyword classifier
  in :mod:`emergent_divergence.metrics.divergence`, so the two classifiers
  produce the same output shape and can be compared message-for-message.
* **Backend reuse.** It calls the existing synchronous ``ModelProvider``
  abstraction (the Claude arm by default), so authentication, retry, and cost
  accounting are the ones already used by the agents. No async, no new SDK.

Note on the *rejected* alternative: a separately proposed variant injected the
agent's assigned role into the prompt and scored a ``role_rigidity`` dimension
on a 1-5 scale. That was not adopted — telling the judge the role it is meant to
find defeats blindness, and the 5-dimension/1-5 schema breaks parallelism with
the keyword classifier. See the design spec and the decision record under
``docs/superpowers/specs/`` for the full rationale.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from emergent_divergence.metrics.divergence import (
    classify_message_behavior,
    compute_behavioral_divergence,
    load_agent_messages,
)

if TYPE_CHECKING:
    from emergent_divergence.providers.base import ModelProvider

logger = logging.getLogger(__name__)

# Low-cost, fast default. Overridable via the ``--judge-model`` analyze flag.
DEFAULT_JUDGE_MODEL = "claude-haiku-4-5-20251001"

# Fixed, hardcoded category set — MUST stay aligned with ``BEHAVIOR_KEYWORDS`` in
# divergence.py. Changing it means updating both classifiers simultaneously.
CATEGORIES: tuple[str, ...] = (
    "proposal",
    "critique",
    "synthesis",
    "verification",
    "recall",
    "clarification",
)

# Definitions are embedded verbatim in the judge prompt (spec §6).
CATEGORY_DEFINITIONS: dict[str, str] = {
    "proposal": "generating ideas, suggesting solutions, introducing new framings",
    "critique": "evaluating critically, identifying weaknesses, pushing for rigor",
    "synthesis": "integrating perspectives, finding common ground, reconciling viewpoints",
    "verification": "citing evidence, referencing data, demanding specifics",
    "recall": "referencing prior rounds, memory, past discussions",
    "clarification": "requesting definitions, asking for elaboration",
}

_JUDGE_SYSTEM = "You are a precise message classifier. Output only a JSON object, nothing else."

# Failure cap (spec §6): if more than this fraction of messages fail to classify
# after a retry, abort rather than report a degraded profile.
DEFAULT_MAX_FAILURE_RATE = 0.10

# Present/absent threshold for per-category agreement (spec §4.4 / §6).
_PRESENCE_THRESHOLD = 0.3


# ── Prompt ────────────────────────────────────────────────────────────────────

def build_judge_prompt(message_text: str) -> str:
    """Build the blind judge prompt for a single message (spec §6).

    The prompt carries the message text and the fixed category definitions and
    nothing else — no agent identity, role, condition, or model.
    """
    cats = "\n".join(f"- {c}: {CATEGORY_DEFINITIONS[c]}" for c in CATEGORIES)
    schema = ", ".join(f'"{c}": 0.0' for c in CATEGORIES)
    return (
        "Classify this message from a multi-agent discussion.\n\n"
        "Assign a confidence score (0.0 to 1.0) for each category.\n"
        "Scores are independent — a message can score high on multiple categories.\n\n"
        f"Categories:\n{cats}\n\n"
        'Message:\n"""\n'
        f"{message_text}\n"
        '"""\n\n'
        "Respond with ONLY a JSON object, no other text:\n"
        f"{{{schema}}}"
    )


# ── Response parsing ──────────────────────────────────────────────────────────

def _extract_json_object(text: str) -> dict | None:
    """Recover the first valid top-level JSON object embedded in ``text``.

    Scans from each ``{`` and uses ``raw_decode`` so trailing prose, markdown
    fences, or extra brace blocks after the object don't defeat parsing (a
    greedy ``{.*}`` match would over-capture to the last ``}`` and fail).
    """
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text, start)
        except (json.JSONDecodeError, ValueError):
            start = text.find("{", start + 1)
            continue
        if isinstance(obj, dict):
            return obj
        start = text.find("{", start + 1)
    return None


def parse_judge_response(text: str) -> dict[str, float] | None:
    """Parse a judge reply into a clamped 6-category score dict.

    Tolerant of stray prose or markdown fences around the JSON object. Returns
    ``None`` when no valid object with the full category set can be recovered.
    """
    if not text:
        return None
    raw = _extract_json_object(text)
    if raw is None:
        return None

    scores: dict[str, float] = {}
    for cat in CATEGORIES:
        if cat not in raw:
            return None  # Incomplete schema — treat as a parse failure.
        try:
            val = float(raw[cat])
        except (TypeError, ValueError):
            return None
        scores[cat] = max(0.0, min(1.0, val))
    return scores


# ── Single-message classification ─────────────────────────────────────────────

def classify_message(
    provider: ModelProvider,
    message_text: str,
    *,
    max_tokens: int = 128,
) -> dict[str, float] | None:
    """Classify one message, retrying once on a failure (spec §6).

    Returns the score dict, or ``None`` if both attempts fail to parse. An empty
    or whitespace-only message carries no behavioral signal, so it is scored as
    all-zeros without spending an API call (parity with the keyword classifier).

    Provider exceptions (e.g. a hard API failure after the backend's own
    retries) are caught and treated as a failed attempt, so one bad message
    cannot crash the whole run — it is recorded as a classification failure and
    counts against ``DEFAULT_MAX_FAILURE_RATE``.
    """
    if not message_text or not message_text.strip():
        return {cat: 0.0 for cat in CATEGORIES}

    prompt = build_judge_prompt(message_text)
    for _ in range(2):  # initial attempt + one retry
        try:
            gen = provider.generate(
                [{"role": "user", "content": prompt}],
                seed=None,
                temperature=0.0,  # deterministic judging
                max_tokens=max_tokens,
                system=_JUDGE_SYSTEM,
            )
        except Exception as exc:  # noqa: BLE001 — any provider error is a failed attempt
            logger.warning("Judge provider call failed: %s", exc)
            continue
        scores = parse_judge_response(gen.text)
        if scores is not None:
            return scores
    return None


# ── Run-level classification ──────────────────────────────────────────────────

def _get_text(event: dict) -> str:
    return event.get("data", {}).get("response_text", "")


def _event_field(event: dict, key: str) -> Any:
    """Read ``key`` from the event top level or its ``data`` block.

    Uses an explicit ``is not None`` check rather than ``or`` so falsy-but-valid
    values (notably ``round_id``/``turn`` of ``0``) are preserved instead of
    falling through to the other location.
    """
    top = event.get(key)
    if top is not None:
        return top
    return event.get("data", {}).get(key)


def classify_run(
    log_path: Path,
    provider: ModelProvider,
    *,
    judge_model: str | None = None,
    max_failure_rate: float = DEFAULT_MAX_FAILURE_RATE,
) -> dict[str, Any]:
    """Classify every ``agent_message`` in a run with the LLM judge (spec §4.3).

    Args:
        log_path: Path to the run's ``events.jsonl``.
        provider: A ``ModelProvider`` (the Claude arm by default) used for
            judging. Injected so tests can run fully offline.
        judge_model: Model id recorded in the report. Falls back to the
            provider's ``model`` attribute, then to the module default.
        max_failure_rate: Abort if the share of unparseable classifications
            exceeds this fraction.

    Returns the ``behavioral_specialization_llm_judge`` section. Carries an
    internal ``_per_message`` list (round_id, agent_id, turn, text, scores) for
    agreement computation; callers strip it before serialising the report.
    """
    agent_messages = load_agent_messages(log_path)
    if not agent_messages:
        return {"error": "No agent messages found in log"}

    model_name = judge_model or getattr(provider, "model", None) or DEFAULT_JUDGE_MODEL

    # Total message count is known upfront, so we can stop the moment the failure
    # cap becomes unrecoverable instead of judging every message first — this
    # avoids burning hundreds of provider calls on a misconfigured backend.
    total_messages = sum(len(msgs) for msgs in agent_messages.values())
    max_failures = max_failure_rate * total_messages

    classifications: dict[str, list[dict]] = defaultdict(list)
    per_message: list[dict] = []
    failures = 0
    total = 0
    aborted = False

    # Deterministic, sequential pass over messages (spec §6: no parallelism).
    for aid in sorted(agent_messages.keys()):
        for event in agent_messages[aid]:
            total += 1
            text = _get_text(event)
            round_id = _event_field(event, "round_id")
            turn = _event_field(event, "turn")
            task_id = _event_field(event, "task_id")

            scores = classify_message(provider, text)
            if scores is None:
                failures += 1
                classifications[aid].append({
                    "round_id": round_id,
                    "turn": turn,
                    "task_id": task_id,
                    "scores": None,
                })
                # Once failures exceed the cap, later successes cannot bring the
                # final rate back under it — bail out early.
                if failures > max_failures:
                    aborted = True
                    break
                continue

            classifications[aid].append({
                "round_id": round_id,
                "turn": turn,
                "task_id": task_id,
                "scores": scores,
            })
            per_message.append({
                "round_id": round_id,
                "agent_id": aid,
                "turn": turn,
                "text": text,
                "scores": scores,
            })
        if aborted:
            break

    if aborted or (total and failures / total > max_failure_rate):
        return {
            "error": (
                f"Judge failure rate {failures}/{total} "
                f"({failures / total:.1%}) exceeds cap of {max_failure_rate:.0%}"
                + (" — aborted early" if aborted else "")
            ),
            "judge_model": model_name,
            "total_classifications": total,
            "classification_failures": failures,
        }

    profiles = _profiles_from_classifications(classifications)
    divergence = compute_behavioral_divergence(profiles)

    return {
        "classifications": {aid: msgs for aid, msgs in classifications.items()},
        "profiles": profiles,
        "divergence_score": divergence,
        "judge_model": model_name,
        "total_classifications": total,
        "classification_failures": failures,
        "_per_message": per_message,
    }


def _profiles_from_classifications(
    classifications: dict[str, list[dict]],
) -> dict[str, dict[str, float]]:
    """Average per-message scores into a per-agent profile (skips failures)."""
    profiles: dict[str, dict[str, float]] = {}
    for aid, msgs in classifications.items():
        sums: dict[str, float] = defaultdict(float)
        n = 0
        for m in msgs:
            scores = m.get("scores")
            if not scores:
                continue
            n += 1
            for cat in CATEGORIES:
                sums[cat] += scores.get(cat, 0.0)
        if n == 0:
            profiles[aid] = {cat: 0.0 for cat in CATEGORIES}
        else:
            profiles[aid] = {cat: round(sums[cat] / n, 4) for cat in CATEGORIES}
    return profiles


# ── Classifier agreement (keyword vs judge) ───────────────────────────────────

def compute_classifier_agreement(per_message: list[dict]) -> dict[str, Any]:
    """Compare the LLM judge against the keyword classifier (spec §4.4).

    For each judged message, the keyword classifier is run on the same text and
    the two 6-element score vectors are compared. Reports top-1 match rate,
    per-category present/absent agreement, and Spearman rank correlation.
    """
    from scipy.stats import spearmanr

    if not per_message:
        return {"error": "No classified messages available for agreement"}

    top1_matches = 0
    cat_agree = {cat: 0 for cat in CATEGORIES}
    spearmans: list[float] = []
    records: list[dict] = []

    for rec in per_message:
        judge = rec["scores"]
        keyword = classify_message_behavior(rec["text"])

        j_vec = [judge[c] for c in CATEGORIES]
        k_vec = [keyword.get(c, 0.0) for c in CATEGORIES]

        if _argmax_category(judge) == _argmax_category(keyword):
            top1_matches += 1

        for c in CATEGORIES:
            if (judge[c] >= _PRESENCE_THRESHOLD) == (keyword.get(c, 0.0) >= _PRESENCE_THRESHOLD):
                cat_agree[c] += 1

        # Spearman is undefined when either vector is constant; treat as 0.0.
        if len(set(j_vec)) == 1 or len(set(k_vec)) == 1:
            rho = 0.0
        else:
            rho_raw, _ = spearmanr(j_vec, k_vec)
            rho = 0.0 if rho_raw != rho_raw else float(rho_raw)  # NaN guard
        spearmans.append(rho)

        records.append({
            "round_id": rec.get("round_id"),
            "agent_id": rec.get("agent_id"),
            "keyword_top": _argmax_category(keyword),
            "llm_judge_top": _argmax_category(judge),
            "spearman": round(rho, 4),
            "text_preview": rec["text"][:80],
        })

    n = len(per_message)
    import numpy as np

    arr = np.array(spearmans, dtype=float)
    disagreements = sorted(records, key=lambda r: r["spearman"])[:10]

    return {
        "top_1_match_rate": round(top1_matches / n, 4),
        "per_category_agreement": {c: round(cat_agree[c] / n, 4) for c in CATEGORIES},
        "mean_spearman_rank_correlation": round(float(arr.mean()), 4),
        "per_message_spearman": {
            "mean": round(float(arr.mean()), 4),
            "std": round(float(arr.std()), 4),
            "min": round(float(arr.min()), 4),
            "max": round(float(arr.max()), 4),
        },
        "disagreement_examples": disagreements,
    }


def _argmax_category(scores: dict[str, float]) -> str:
    """Top-scoring category, ties broken by the fixed category order."""
    return max(CATEGORIES, key=lambda c: (scores.get(c, 0.0), -CATEGORIES.index(c)))
