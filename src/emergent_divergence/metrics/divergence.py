"""Divergence metrics computed from experiment logs.

Implements the core metric set from the experiment brief:
A. Linguistic divergence (JSD, embedding distance, lexical uniqueness)
B. Behavioral specialization (message classification, role proportions)
C. Memory usage patterns
D. Coordination structure (interaction graph properties)
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial.distance import jensenshannon
from scipy.stats import entropy


# ── Log Loading ───────────────────────────────────────────────────────────────

def load_agent_messages(log_path: Path) -> dict[str, list[dict]]:
    """Load all agent_message events, grouped by agent_id."""
    agents: dict[str, list[dict]] = defaultdict(list)
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            event = json.loads(line.strip())
            if event.get("event_type") == "agent_message":
                agent_id = event["data"].get("agent_id") or event.get("agent_id")
                if agent_id:
                    agents[agent_id].append(event)
    return dict(agents)


def load_events_by_type(log_path: Path, event_type: str) -> list[dict]:
    """Load all events of a given type."""
    events = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            event = json.loads(line.strip())
            if event.get("event_type") == event_type:
                events.append(event)
    return events


# ── A. Linguistic Divergence ──────────────────────────────────────────────────

def _get_text(event: dict) -> str:
    """Extract response text from an agent_message event."""
    return event.get("data", {}).get("response_text", "")


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r'\b\w+\b', text.lower())


def word_frequency_distribution(texts: list[str], vocab: list[str] | None = None) -> np.ndarray:
    """Compute word frequency distribution over a shared vocabulary."""
    all_tokens = []
    for t in texts:
        all_tokens.extend(_tokenize(t))

    if vocab is None:
        counter = Counter(all_tokens)
        vocab = sorted(counter.keys())

    counts = np.zeros(len(vocab))
    token_set = Counter(all_tokens)
    for i, word in enumerate(vocab):
        counts[i] = token_set.get(word, 0)

    # Add smoothing and normalize
    counts += 1e-10
    return counts / counts.sum(), vocab


def compute_pairwise_jsd(agent_messages: dict[str, list[dict]],
                         window: tuple[int, int] | None = None) -> dict[str, float]:
    """Compute pairwise Jensen-Shannon divergence between agents.

    Args:
        agent_messages: Dict of agent_id -> list of message events
        window: Optional (start_round, end_round) to restrict analysis

    Returns:
        Dict with keys like "agent_0_vs_agent_1" -> JSD value
    """
    agent_ids = sorted(agent_messages.keys())
    if len(agent_ids) < 2:
        return {}

    # Collect texts per agent within window
    agent_texts: dict[str, list[str]] = {}
    for aid in agent_ids:
        texts = []
        for msg in agent_messages[aid]:
            round_id = msg.get("round_id") or msg.get("data", {}).get("round_id")
            if window and round_id is not None:
                if round_id < window[0] or round_id > window[1]:
                    continue
            texts.append(_get_text(msg))
        agent_texts[aid] = texts

    # Build shared vocabulary
    all_tokens = []
    for texts in agent_texts.values():
        for t in texts:
            all_tokens.extend(_tokenize(t))
    vocab = sorted(set(all_tokens))

    if not vocab:
        return {}

    # Compute distributions
    distributions = {}
    for aid, texts in agent_texts.items():
        dist, _ = word_frequency_distribution(texts, vocab)
        distributions[aid] = dist

    # Pairwise JSD
    results = {}
    for i, a1 in enumerate(agent_ids):
        for a2 in agent_ids[i + 1:]:
            jsd = float(jensenshannon(distributions[a1], distributions[a2]))
            results[f"{a1}_vs_{a2}"] = round(jsd, 6)

    return results


def compute_lexical_uniqueness(agent_messages: dict[str, list[dict]],
                                window: tuple[int, int] | None = None) -> dict[str, float]:
    """For each agent, compute the ratio of unique words not used by others."""
    agent_ids = sorted(agent_messages.keys())
    agent_vocabs: dict[str, set[str]] = {}

    for aid in agent_ids:
        tokens = set()
        for msg in agent_messages[aid]:
            round_id = msg.get("round_id") or msg.get("data", {}).get("round_id")
            if window and round_id is not None:
                if round_id < window[0] or round_id > window[1]:
                    continue
            tokens.update(_tokenize(_get_text(msg)))
        agent_vocabs[aid] = tokens

    results = {}
    for aid in agent_ids:
        others = set()
        for other_aid in agent_ids:
            if other_aid != aid:
                others.update(agent_vocabs[other_aid])
        unique = agent_vocabs[aid] - others
        total = len(agent_vocabs[aid]) if agent_vocabs[aid] else 1
        results[aid] = round(len(unique) / total, 4)

    return results


def compute_jsd_over_time(agent_messages: dict[str, list[dict]],
                           window_size: int = 10) -> list[dict]:
    """Compute JSD in sliding windows to track divergence over time."""
    # Find round range
    all_rounds = set()
    for msgs in agent_messages.values():
        for msg in msgs:
            r = msg.get("round_id") or msg.get("data", {}).get("round_id")
            if r is not None:
                all_rounds.add(r)

    if not all_rounds:
        return []

    min_round, max_round = min(all_rounds), max(all_rounds)
    results = []

    for start in range(min_round, max_round - window_size + 2):
        end = start + window_size - 1
        jsd = compute_pairwise_jsd(agent_messages, window=(start, end))
        if jsd:
            mean_jsd = np.mean(list(jsd.values()))
            results.append({
                "window_start": start,
                "window_end": end,
                "mean_jsd": round(float(mean_jsd), 6),
                "pairwise_jsd": jsd,
            })

    return results


# ── B. Behavioral Specialization ─────────────────────────────────────────────

BEHAVIOR_KEYWORDS: dict[str, list[str]] = {
    "proposal": ["suggest", "propose", "idea", "what if", "consider", "approach",
                  "solution", "let's try", "we could", "one option"],
    "critique": ["disagree", "however", "but", "flaw", "weakness", "problem",
                 "issue", "concern", "incorrect", "overlook", "miss"],
    "synthesis": ["combining", "integrate", "overall", "together", "summary",
                  "consensus", "both points", "building on", "merge", "reconcile"],
    "verification": ["evidence", "data", "study", "research shows", "according",
                     "specifically", "fact", "source", "citation", "empirically"],
    "recall": ["earlier", "previously", "as we discussed", "remember", "last round",
               "noted before", "prior", "mentioned"],
    "clarification": ["what do you mean", "clarify", "elaborate", "specifically",
                      "define", "in other words", "meaning"],
}


def classify_message_behavior(text: str) -> dict[str, float]:
    """Classify a message into behavioral categories based on keyword density."""
    text_lower = text.lower()
    tokens = _tokenize(text_lower)
    total = len(tokens) if tokens else 1

    scores = {}
    for category, keywords in BEHAVIOR_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        scores[category] = round(count / len(keywords), 4)

    return scores


def compute_behavioral_profiles(agent_messages: dict[str, list[dict]]) -> dict[str, dict[str, float]]:
    """Compute per-agent behavioral profile as averaged category scores."""
    profiles = {}
    for aid, msgs in agent_messages.items():
        category_sums: dict[str, float] = defaultdict(float)
        n = len(msgs)
        if n == 0:
            profiles[aid] = {}
            continue

        for msg in msgs:
            scores = classify_message_behavior(_get_text(msg))
            for cat, score in scores.items():
                category_sums[cat] += score

        profiles[aid] = {cat: round(s / n, 4) for cat, s in category_sums.items()}

    return profiles


def compute_behavioral_divergence(profiles: dict[str, dict[str, float]]) -> float:
    """Compute overall behavioral divergence as mean pairwise L2 distance between profiles."""
    agent_ids = sorted(profiles.keys())
    if len(agent_ids) < 2:
        return 0.0

    categories = sorted(set().union(*[set(p.keys()) for p in profiles.values()]))

    vectors = {}
    for aid in agent_ids:
        vectors[aid] = np.array([profiles[aid].get(c, 0.0) for c in categories])

    distances = []
    for i, a1 in enumerate(agent_ids):
        for a2 in agent_ids[i + 1:]:
            d = float(np.linalg.norm(vectors[a1] - vectors[a2]))
            distances.append(d)

    return round(float(np.mean(distances)), 6) if distances else 0.0


# ── C. Memory Usage Patterns ─────────────────────────────────────────────────

def compute_memory_stats(log_path: Path) -> dict[str, dict[str, Any]]:
    """Compute per-agent memory usage statistics."""
    writes = load_events_by_type(log_path, "memory_write")
    reads_by_agent: dict[str, list[int]] = defaultdict(list)
    writes_by_agent: dict[str, int] = defaultdict(int)

    for w in writes:
        aid = w.get("agent_id") or w.get("data", {}).get("agent_id")
        if aid:
            writes_by_agent[aid] += 1

    # Extract memory reads from agent_message events
    messages = load_events_by_type(log_path, "agent_message")
    for msg in messages:
        aid = msg.get("agent_id") or msg.get("data", {}).get("agent_id")
        reads = msg.get("data", {}).get("memory_reads", 0)
        if aid:
            reads_by_agent[aid].append(reads)

    stats = {}
    all_agents = set(list(writes_by_agent.keys()) + list(reads_by_agent.keys()))
    for aid in sorted(all_agents):
        r = reads_by_agent.get(aid, [])
        stats[aid] = {
            "total_writes": writes_by_agent.get(aid, 0),
            "total_reads": sum(r),
            "mean_reads_per_msg": round(np.mean(r), 2) if r else 0,
            "max_reads": max(r) if r else 0,
        }

    return stats


# ── D. Coordination Structure ─────────────────────────────────────────────────

def compute_turn_order_stats(agent_messages: dict[str, list[dict]]) -> dict[str, Any]:
    """Analyze who speaks when and basic coordination patterns."""
    agent_ids = sorted(agent_messages.keys())

    # Count messages per agent
    msg_counts = {aid: len(msgs) for aid, msgs in agent_messages.items()}

    # Analyze first-mover frequency (who speaks first in rounds)
    round_firsts: dict[str, int] = defaultdict(int)
    round_messages: dict[int, list[tuple[int, str]]] = defaultdict(list)

    for aid, msgs in agent_messages.items():
        for msg in msgs:
            r = msg.get("round_id") or msg.get("data", {}).get("round_id")
            turn = msg.get("data", {}).get("turn", 0)
            if r is not None:
                round_messages[r].append((turn, aid))

    for r, entries in round_messages.items():
        entries.sort()
        if entries:
            round_firsts[entries[0][1]] += 1

    return {
        "message_counts": msg_counts,
        "first_speaker_counts": dict(round_firsts),
        "total_rounds": len(round_messages),
    }


# ── Summary Report ────────────────────────────────────────────────────────────

def generate_analysis_report(log_path: Path) -> dict[str, Any]:
    """Generate a complete analysis report from a single run's log file."""
    agent_messages = load_agent_messages(log_path)

    if not agent_messages:
        return {"error": "No agent messages found in log"}

    # A. Linguistic divergence
    jsd = compute_pairwise_jsd(agent_messages)
    jsd_over_time = compute_jsd_over_time(agent_messages, window_size=10)
    lexical_uniq = compute_lexical_uniqueness(agent_messages)

    # B. Behavioral specialization
    profiles = compute_behavioral_profiles(agent_messages)
    behav_div = compute_behavioral_divergence(profiles)

    # C. Memory
    memory_stats = compute_memory_stats(log_path)

    # D. Coordination
    coord_stats = compute_turn_order_stats(agent_messages)

    return {
        "linguistic_divergence": {
            "pairwise_jsd": jsd,
            "mean_jsd": round(float(np.mean(list(jsd.values()))), 6) if jsd else 0.0,
            "jsd_over_time": jsd_over_time,
            "lexical_uniqueness": lexical_uniq,
        },
        "behavioral_specialization": {
            "profiles": profiles,
            "divergence_score": behav_div,
        },
        "memory_usage": memory_stats,
        "coordination_structure": coord_stats,
        "agent_count": len(agent_messages),
        "total_messages": sum(len(msgs) for msgs in agent_messages.values()),
    }


def compare_conditions(report_a: dict, report_b: dict) -> dict[str, Any]:
    """Compare two condition reports (e.g., memory vs no-memory)."""
    return {
        "jsd_comparison": {
            "condition_a_mean_jsd": report_a.get("linguistic_divergence", {}).get("mean_jsd", 0),
            "condition_b_mean_jsd": report_b.get("linguistic_divergence", {}).get("mean_jsd", 0),
        },
        "behavioral_divergence_comparison": {
            "condition_a": report_a.get("behavioral_specialization", {}).get("divergence_score", 0),
            "condition_b": report_b.get("behavioral_specialization", {}).get("divergence_score", 0),
        },
        "message_counts": {
            "condition_a": report_a.get("total_messages", 0),
            "condition_b": report_b.get("total_messages", 0),
        },
    }
