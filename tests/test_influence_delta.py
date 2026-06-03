"""Unit tests for the influence-delta math (brief §9, Appendix A).

These pin the numeric guarantees the report relies on: JSD bounds and symmetry,
Gini bounds, hub detection by row sum, asymmetry, and the lagged-correlation
"influence precedes divergence" signal.
"""

from __future__ import annotations

import numpy as np
import pytest

from emergent_divergence.embeddings import get_embedder
from emergent_divergence.metrics.influence_delta import (
    gini,
    influence_hub,
    jsd_distributions,
    jsd_tokens,
    lagged_correlation,
    matrix_summary,
    semantic_delta,
)

# ── gini ──────────────────────────────────────────────────────────────────────


def test_gini_empty_and_all_zero_is_zero():
    assert gini([]) == 0.0
    assert gini([0.0, 0.0, 0.0]) == 0.0


def test_gini_all_equal_is_zero():
    assert gini([3.0, 3.0, 3.0]) == pytest.approx(0.0)


def test_gini_single_hub():
    # One unit on one of three sources: maximally concentrated -> (n-1)/n.
    assert gini([0.0, 0.0, 1.0]) == pytest.approx(2.0 / 3.0, abs=1e-4)


def test_gini_in_unit_interval():
    rng = np.random.default_rng(0)
    for _ in range(20):
        v = np.abs(rng.normal(size=5))
        g = gini(v)
        assert 0.0 <= g <= 1.0


def test_gini_negatives_clipped():
    # Negative entries are clipped to 0, so this is the single-hub case.
    assert gini([-5.0, 0.0, 1.0]) == pytest.approx(2.0 / 3.0, abs=1e-4)


# ── jsd_distributions ───────────────────────────────────────────────────────────


def test_jsd_identical_is_zero():
    p = np.array([0.2, 0.3, 0.5])
    assert jsd_distributions(p, p) == pytest.approx(0.0, abs=1e-9)


def test_jsd_disjoint_is_one():
    p = np.array([1.0, 0.0])
    q = np.array([0.0, 1.0])
    assert jsd_distributions(p, q) == pytest.approx(1.0, abs=1e-6)


def test_jsd_symmetry():
    p = np.array([0.1, 0.6, 0.3])
    q = np.array([0.5, 0.2, 0.3])
    assert jsd_distributions(p, q) == pytest.approx(jsd_distributions(q, p), abs=1e-9)


def test_jsd_in_unit_interval():
    rng = np.random.default_rng(1)
    for _ in range(20):
        p = np.abs(rng.normal(size=6)) + 1e-6
        q = np.abs(rng.normal(size=6)) + 1e-6
        d = jsd_distributions(p, q)
        assert 0.0 <= d <= 1.0


def test_jsd_mismatched_or_empty_is_zero():
    assert jsd_distributions(np.array([1.0, 2.0]), np.array([1.0])) == 0.0
    assert jsd_distributions(np.array([]), np.array([])) == 0.0


def test_jsd_zero_sum_is_zero():
    assert jsd_distributions(np.array([0.0, 0.0]), np.array([1.0, 1.0])) == 0.0


# ── jsd_tokens ──────────────────────────────────────────────────────────────────


def test_jsd_tokens_identical_pools_zero():
    a = ["the cat sat on the mat", "the dog ran"]
    assert jsd_tokens(a, list(a)) == pytest.approx(0.0, abs=1e-9)


def test_jsd_tokens_disjoint_vocab_is_one():
    assert jsd_tokens(["alpha beta"], ["gamma delta"]) == pytest.approx(1.0, abs=1e-6)


def test_jsd_tokens_empty_is_zero():
    assert jsd_tokens([], []) == 0.0


# ── semantic_delta ──────────────────────────────────────────────────────────────


def test_semantic_delta_identical_pools_zero():
    emb = get_embedder()
    texts = ["a structural point about incentives", "a second remark"]
    assert semantic_delta(texts, list(texts), emb) == pytest.approx(0.0, abs=1e-6)


def test_semantic_delta_empty_pool_zero():
    emb = get_embedder()
    assert semantic_delta([], ["something"], emb) == 0.0
    assert semantic_delta(["something"], [], emb) == 0.0


def test_semantic_delta_differing_pools_positive():
    emb = get_embedder()
    a = ["incentives and falsifiability dominate the argument"]
    b = ["the weather today is cloudy with rain"]
    assert semantic_delta(a, b, emb) > 0.0


# ── matrices / hub ──────────────────────────────────────────────────────────────


def test_influence_hub_is_argmax_row_sum():
    # source 1 has the largest outgoing influence (row sum).
    M = np.array([
        [0.0, 0.1, 0.1],
        [0.4, 0.0, 0.5],
        [0.0, 0.1, 0.0],
    ])
    assert influence_hub(M) == 1


def test_influence_hub_empty():
    assert influence_hub(np.empty((0, 0))) == -1


def test_matrix_summary_hub_and_bounds():
    agents = ["agent_0", "agent_1", "agent_2"]
    # agent_0 a clear hub (large outgoing, asymmetric).
    M = np.array([
        [0.0, 0.6, 0.7],
        [0.05, 0.0, 0.05],
        [0.05, 0.05, 0.0],
    ])
    s = matrix_summary(M, agents)
    assert s["hub"] == "agent_0"
    assert 0.0 <= s["gini_outgoing"] <= 1.0
    assert isinstance(s["hub_net_positive"], bool)
    assert s["hub_net_positive"] is True
    # Asymmetry is M - M^T: diagonal zero, antisymmetric.
    asym = np.array(s["asymmetry_matrix"])
    assert np.allclose(asym, -asym.T)


def test_matrix_summary_empty():
    s = matrix_summary(np.empty((0, 0)), [])
    assert s["hub"] is None
    assert s["gini_outgoing"] == 0.0


# ── lagged correlation (H-I3) ────────────────────────────────────────────────────


def test_lagged_correlation_insufficient_points():
    out = lagged_correlation({0: 0.1, 1: 0.2}, {0: 0.1, 1: 0.2})
    assert "error" in out


def test_lagged_correlation_influence_precedes_divergence():
    # Influence at round t maps monotonically to divergence at round t+1.
    influence = {r: 0.1 * (r + 1) for r in range(7)}
    divergence = {r + 1: 0.1 * (r + 1) for r in range(7)}
    out = lagged_correlation(influence, divergence, max_lag=3)
    assert "error" not in out
    assert out["best_lag"] >= 1
    assert out["best_rho"] > 0
    assert out["precedes"] is True
