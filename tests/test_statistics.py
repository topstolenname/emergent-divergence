"""Unit tests for inferential statistics and verdict logic (brief §4.4)."""

from __future__ import annotations

from emergent_divergence.metrics.statistics import (
    NOT_SUPPORTED,
    SUPPORTED,
    bootstrap_ci,
    cohens_d,
    diff_ci,
    run_statistics,
)


# ── bootstrap_ci ────────────────────────────────────────────────────────────────


def test_bootstrap_ci_empty():
    out = bootstrap_ci([])
    assert out["n"] == 0
    assert out["mean"] is None
    assert out["ci_low"] is None and out["ci_high"] is None


def test_bootstrap_ci_single_value():
    out = bootstrap_ci([0.5])
    assert out["n"] == 1
    assert out["mean"] == 0.5
    assert out["ci_low"] == out["ci_high"] == 0.5


def test_bootstrap_ci_constant_is_tight():
    out = bootstrap_ci([0.4, 0.4, 0.4, 0.4])
    assert out["mean"] == 0.4
    assert out["ci_low"] == 0.4 and out["ci_high"] == 0.4


def test_bootstrap_ci_drops_none():
    out = bootstrap_ci([1.0, None, 1.0, None])
    assert out["n"] == 2


def test_bootstrap_ci_ordering():
    out = bootstrap_ci([0.1, 0.2, 0.3, 0.4, 0.5])
    assert out["ci_low"] <= out["mean"] <= out["ci_high"]


# ── cohens_d ────────────────────────────────────────────────────────────────────


def test_cohens_d_too_few():
    assert cohens_d([1.0], [2.0, 3.0]) is None
    assert cohens_d([1.0, 2.0], [3.0]) is None


def test_cohens_d_identical_is_zero():
    assert cohens_d([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 0.0


def test_cohens_d_sign():
    # a clearly greater than b -> positive d.
    d = cohens_d([5.0, 6.0, 7.0], [1.0, 2.0, 3.0])
    assert d is not None and d > 0


# ── diff_ci ─────────────────────────────────────────────────────────────────────


def test_diff_ci_positive_difference():
    out = diff_ci([0.6, 0.7, 0.8, 0.9], [0.1, 0.2, 0.3, 0.4])
    assert out["diff"] > 0
    assert out["ci_low"] > 0  # well-separated -> CI excludes zero
    assert out["n_a"] == 4 and out["n_b"] == 4


def test_diff_ci_empty():
    out = diff_ci([], [1.0])
    assert out["diff"] is None


# ── run_statistics ──────────────────────────────────────────────────────────────


def _cell(backend, condition, seed, **overrides):
    base = {
        "cell_id": f"{backend}_{condition}_seed{seed}",
        "backend": backend,
        "condition": condition,
        "seed": seed,
        "linguistic_mean_jsd": 0.3,
        "h1_jsd_rho": 0.5,
        "behavioral_divergence": 0.5,
        "semantic_mean": 0.4,
        "semantic_rho": 0.5,
        "semantic_trend": 0.1,
        "influence_mean_sem": 0.3,
        "influence_gini": 0.4,
        "influence_hub_net_positive": True,
        "influence_precedes": True,
        "influence_lag_rho": 0.5,
    }
    base.update(overrides)
    return base


def test_run_statistics_shape():
    cells = [_cell("stub", "A", s) for s in (42, 43, 44, 45)]
    stats = run_statistics(cells)
    assert stats["n_cells_total"] == 4
    assert stats["backends"] == ["stub"]
    assert "stub" in stats["per_backend"]
    assert "cross_backend_conditionA" in stats
    pb = stats["per_backend"]["stub"]
    assert pb["n_cells"] == 4
    assert "hypotheses" in pb and "H1" in pb["hypotheses"]
    assert "headline_cis" in pb


def test_run_statistics_supported_verdicts():
    # Four condition-A seeds, all strongly positive -> CI excludes zero.
    cells = [
        _cell("stub", "A", 42, h1_jsd_rho=0.6, behavioral_divergence=0.5, semantic_rho=0.55),
        _cell("stub", "A", 43, h1_jsd_rho=0.5, behavioral_divergence=0.6, semantic_rho=0.5),
        _cell("stub", "A", 44, h1_jsd_rho=0.7, behavioral_divergence=0.55, semantic_rho=0.6),
        _cell("stub", "A", 45, h1_jsd_rho=0.55, behavioral_divergence=0.5, semantic_rho=0.5),
    ]
    hyps = run_statistics(cells)["per_backend"]["stub"]["hypotheses"]
    assert hyps["H1"]["verdict"] == SUPPORTED
    assert hyps["H2"]["verdict"] == SUPPORTED
    assert hyps["H3"]["verdict"] == SUPPORTED


def test_run_statistics_h4_memory_amplifies():
    # A clearly > B on semantic mean -> H4 supported.
    cells = []
    for s in (42, 43, 44, 45):
        cells.append(_cell("stub", "A", s, semantic_mean=0.7))
        cells.append(_cell("stub", "B", s, semantic_mean=0.2))
    hyps = run_statistics(cells)["per_backend"]["stub"]["hypotheses"]
    assert hyps["H4"]["verdict"] == SUPPORTED


def test_run_statistics_hi3_not_supported_when_never_precedes():
    cells = [_cell("stub", "A", s, influence_precedes=False) for s in (42, 43, 44, 45)]
    hyps = run_statistics(cells)["per_backend"]["stub"]["hypotheses"]
    assert hyps["H-I3"]["verdict"] == NOT_SUPPORTED
