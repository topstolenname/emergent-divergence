"""Metrics layer: linguistic/behavioral divergence, semantic divergence,
counterfactual influence-delta, per-cell aggregation, and cross-cell statistics.
"""

from __future__ import annotations

from emergent_divergence.metrics.cell import analyze_cell
from emergent_divergence.metrics.influence_delta import (
    analyze_influence,
    compute_influence_matrices,
    gini,
    influence_hub,
    jsd_distributions,
    jsd_tokens,
    lagged_correlation,
    matrix_summary,
    semantic_delta,
)
from emergent_divergence.metrics.statistics import (
    bootstrap_ci,
    cohens_d,
    diff_ci,
    evaluate_backend,
    run_statistics,
)

__all__ = [
    "analyze_cell",
    "analyze_influence",
    "compute_influence_matrices",
    "gini",
    "influence_hub",
    "jsd_distributions",
    "jsd_tokens",
    "lagged_correlation",
    "matrix_summary",
    "semantic_delta",
    "bootstrap_ci",
    "cohens_d",
    "diff_ci",
    "evaluate_backend",
    "run_statistics",
]
