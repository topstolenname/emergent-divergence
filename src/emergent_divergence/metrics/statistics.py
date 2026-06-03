"""Inferential statistics and per-hypothesis verdicts (brief §4.4).

Consumes the *flat* per-cell summaries produced by
:func:`emergent_divergence.metrics.cell.analyze_cell` (one dict per matrix cell)
and produces, **per backend**:

* bootstrap 95% CIs on headline metrics aggregated over seeds;
* A-vs-B contrasts (memory on vs off) with an effect size (Cohen's d) and a
  bootstrap CI on the mean difference;
* a verdict table for H1-H5 and H-I1..H-I3 — each ``Supported`` / ``Mixed`` /
  ``Not supported`` with the numbers that drove it;
* a cross-backend comparison of the same headline metrics.

Verdicts are derived from the data, never hard-coded. The rule of thumb:
*Supported* when the relevant bootstrap CI excludes 0 in the hypothesised
direction, *Mixed* when the point estimate points the right way but the CI
straddles 0, *Not supported* otherwise.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

SUPPORTED = "Supported"
MIXED = "Mixed"
NOT_SUPPORTED = "Not supported"
INSUFFICIENT = "Insufficient data"

# Concentration above this Gini is treated as meaningful hub structure (H-I2).
_GINI_HUB_THRESHOLD = 0.20


# ── primitives ───────────────────────────────────────────────────────────────


def bootstrap_ci(
    values: list[float],
    *,
    statistic: Callable[[np.ndarray], float] = np.mean,
    n_boot: int = 5000,
    ci: float = 0.95,
    seed: int = 0,
) -> dict[str, Any]:
    """Percentile bootstrap CI for ``statistic`` over ``values``."""
    arr = np.asarray([v for v in values if v is not None], dtype=np.float64)
    n = arr.size
    if n == 0:
        return {"n": 0, "mean": None, "ci_low": None, "ci_high": None}
    point = float(statistic(arr))
    if n == 1:
        return {"n": 1, "mean": point, "ci_low": point, "ci_high": point}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    boot = np.array([statistic(arr[row]) for row in idx])
    alpha = (1.0 - ci) / 2.0
    lo, hi = np.quantile(boot, [alpha, 1.0 - alpha])
    return {
        "n": int(n),
        "mean": round(point, 6),
        "ci_low": round(float(lo), 6),
        "ci_high": round(float(hi), 6),
        "std": round(float(arr.std(ddof=1)) if n > 1 else 0.0, 6),
    }


def cohens_d(a: list[float], b: list[float]) -> float | None:
    """Cohen's d for the difference of means (pooled SD). ``a`` minus ``b``."""
    av = np.asarray([v for v in a if v is not None], dtype=np.float64)
    bv = np.asarray([v for v in b if v is not None], dtype=np.float64)
    if av.size < 2 or bv.size < 2:
        return None
    na, nb = av.size, bv.size
    sp2 = ((na - 1) * av.var(ddof=1) + (nb - 1) * bv.var(ddof=1)) / (na + nb - 2)
    sp = np.sqrt(sp2)
    if sp == 0:
        return 0.0
    return round(float((av.mean() - bv.mean()) / sp), 4)


def diff_ci(
    a: list[float], b: list[float], *, n_boot: int = 5000, ci: float = 0.95, seed: int = 0
) -> dict[str, Any]:
    """Bootstrap CI on the mean difference ``mean(a) - mean(b)``."""
    av = np.asarray([v for v in a if v is not None], dtype=np.float64)
    bv = np.asarray([v for v in b if v is not None], dtype=np.float64)
    if av.size == 0 or bv.size == 0:
        return {"diff": None, "ci_low": None, "ci_high": None, "n_a": int(av.size),
                "n_b": int(bv.size)}
    point = float(av.mean() - bv.mean())
    rng = np.random.default_rng(seed)
    bi = rng.integers(0, av.size, size=(n_boot, av.size))
    bj = rng.integers(0, bv.size, size=(n_boot, bv.size))
    boot = av[bi].mean(axis=1) - bv[bj].mean(axis=1)
    alpha = (1.0 - ci) / 2.0
    lo, hi = np.quantile(boot, [alpha, 1.0 - alpha])
    return {
        "diff": round(point, 6),
        "ci_low": round(float(lo), 6),
        "ci_high": round(float(hi), 6),
        "cohens_d": cohens_d(a, b),
        "n_a": int(av.size),
        "n_b": int(bv.size),
    }


def _verdict_ci(ci_obj: dict[str, Any], *, direction: str = "positive") -> str:
    """Map a CI dict (``mean``/``ci_low``/``ci_high``) to a verdict string."""
    if ci_obj.get("mean") is None or ci_obj.get("n", 0) == 0:
        return INSUFFICIENT
    lo, hi, mean = ci_obj["ci_low"], ci_obj["ci_high"], ci_obj["mean"]
    if ci_obj.get("n", 0) < 2:
        # No CI possible with one seed: weak signal only.
        return MIXED if ((direction == "positive" and mean > 0) or
                         (direction == "negative" and mean < 0)) else NOT_SUPPORTED
    if direction == "positive":
        if lo > 0:
            return SUPPORTED
        return MIXED if mean > 0 else NOT_SUPPORTED
    else:
        if hi < 0:
            return SUPPORTED
        return MIXED if mean < 0 else NOT_SUPPORTED


def _proportion_verdict(flags: list[bool]) -> tuple[str, dict[str, Any]]:
    vals = [bool(f) for f in flags if f is not None]
    if not vals:
        return INSUFFICIENT, {"n": 0, "proportion": None}
    p = sum(vals) / len(vals)
    detail = {"n": len(vals), "n_true": sum(vals), "proportion": round(p, 3)}
    if p >= 0.5:
        return SUPPORTED, detail
    if p > 0.0:
        return MIXED, detail
    return NOT_SUPPORTED, detail


# ── per-backend hypothesis evaluation ────────────────────────────────────────


def _col(cells: list[dict], key: str) -> list[float]:
    return [c.get(key) for c in cells if c.get(key) is not None]


def evaluate_backend(cells: list[dict], *, seed: int = 0) -> dict[str, Any]:
    """Evaluate H1-H5 and H-I1..H-I3 for all cells of one backend.

    ``cells`` are flat per-cell summaries; conditions A/B/C are separated here.
    """
    by_cond: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
    for c in cells:
        by_cond.setdefault(c.get("condition"), []).append(c)
    A, B, C = by_cond.get("A", []), by_cond.get("B", []), by_cond.get("C", [])

    hyp: dict[str, Any] = {}

    # H1: linguistic divergence increases over rounds (Spearman ρ on JSD, cond A).
    h1 = bootstrap_ci(_col(A, "h1_jsd_rho"), seed=seed)
    hyp["H1"] = {
        "statement": "Linguistic divergence increases over rounds (Spearman ρ on pairwise JSD).",
        "metric": "per-cell Spearman ρ (condition A)",
        "ci": h1,
        "verdict": _verdict_ci(h1, direction="positive"),
    }

    # H2: behavioral role specialization (behavioral divergence > 0, cond A).
    h2 = bootstrap_ci(_col(A, "behavioral_divergence"), seed=seed)
    hyp["H2"] = {
        "statement": "Agents specialize behaviorally by role.",
        "metric": "behavioral divergence score (condition A)",
        "ci": h2,
        "verdict": _verdict_ci(h2, direction="positive"),
    }

    # H3: semantic divergence increases over rounds (Spearman ρ on cosine, cond A).
    h3 = bootstrap_ci(_col(A, "semantic_rho"), seed=seed)
    hyp["H3"] = {
        "statement": "Semantic divergence increases over rounds (Spearman ρ on MiniLM cosine).",
        "metric": "per-cell semantic Spearman ρ (condition A)",
        "ci": h3,
        "verdict": _verdict_ci(h3, direction="positive"),
    }

    # H4: memory amplifies divergence (A > B) on semantic mean cosine.
    h4 = diff_ci(_col(A, "semantic_mean"), _col(B, "semantic_mean"), seed=seed)
    hyp["H4"] = {
        "statement": "Memory amplifies divergence (condition A > condition B).",
        "metric": "mean semantic cosine distance, A minus B",
        "contrast": h4,
        "verdict": _verdict_ci(
            {"mean": h4["diff"], "ci_low": h4["ci_low"], "ci_high": h4["ci_high"],
             "n": min(h4["n_a"], h4["n_b"])}, direction="positive"),
    }

    # H5: divergence still occurs without role priors (condition C trend > 0).
    h5 = bootstrap_ci(_col(C, "semantic_rho"), seed=seed)
    hyp["H5"] = {
        "statement": "Divergence occurs even without role priors (condition C).",
        "metric": "per-cell semantic Spearman ρ (condition C)",
        "ci": h5,
        "verdict": _verdict_ci(h5, direction="positive"),
    }

    # H-I1: memory amplifies influence (A > B) on mean semantic influence-delta.
    hi1 = diff_ci(_col(A, "influence_mean_sem"), _col(B, "influence_mean_sem"), seed=seed)
    hyp["H-I1"] = {
        "statement": "Memory amplifies cross-agent influence (A > B).",
        "metric": "mean semantic influence-delta, A minus B",
        "contrast": hi1,
        "verdict": _verdict_ci(
            {"mean": hi1["diff"], "ci_low": hi1["ci_low"], "ci_high": hi1["ci_high"],
             "n": min(hi1["n_a"], hi1["n_b"])}, direction="positive"),
    }

    # H-I2: influence concentrates into a hub (Gini above threshold, cond A).
    gini_ci = bootstrap_ci(_col(A, "influence_gini"), seed=seed)
    hub_verdict, hub_detail = _proportion_verdict(
        [c.get("influence_hub_net_positive") for c in A]
    )
    gini_ok = (gini_ci.get("ci_low") is not None
               and gini_ci["ci_low"] > _GINI_HUB_THRESHOLD)
    if gini_ci.get("n", 0) == 0:
        hi2_verdict = INSUFFICIENT
    elif gini_ok and hub_verdict == SUPPORTED:
        hi2_verdict = SUPPORTED
    elif (gini_ci.get("mean") or 0) > _GINI_HUB_THRESHOLD or hub_verdict in (SUPPORTED, MIXED):
        hi2_verdict = MIXED
    else:
        hi2_verdict = NOT_SUPPORTED
    hyp["H-I2"] = {
        "statement": "Influence concentrates into a hub (Gini of outgoing influence).",
        "metric": f"Gini of row sums (condition A); hub net-positive proportion "
                  f"(threshold Gini>{_GINI_HUB_THRESHOLD})",
        "gini_ci": gini_ci,
        "hub_net_positive": hub_detail,
        "verdict": hi2_verdict,
    }

    # H-I3: influence precedes divergence (lagged correlation, cond A).
    hi3_verdict, hi3_detail = _proportion_verdict([c.get("influence_precedes") for c in A])
    best_rho_ci = bootstrap_ci(_col(A, "influence_lag_rho"), seed=seed)
    hyp["H-I3"] = {
        "statement": "Influence precedes divergence (lagged correlation, lag ≥ 1).",
        "metric": "proportion of cells with positive significant lagged ρ (condition A)",
        "precedes": hi3_detail,
        "best_lag_rho_ci": best_rho_ci,
        "verdict": hi3_verdict,
    }

    return {"by_condition_n": {k: len(v) for k, v in by_cond.items()}, "hypotheses": hyp}


# ── headline metric CIs (per backend × condition) ────────────────────────────

_HEADLINE_KEYS = [
    "linguistic_mean_jsd",
    "behavioral_divergence",
    "semantic_mean",
    "semantic_rho",
    "influence_mean_sem",
    "influence_gini",
]


def headline_cis(cells: list[dict], *, seed: int = 0) -> dict[str, Any]:
    """Bootstrap CIs for headline metrics, split by condition."""
    out: dict[str, Any] = {}
    by_cond: dict[str, list[dict]] = {}
    for c in cells:
        by_cond.setdefault(c.get("condition"), []).append(c)
    for cond, group in sorted(by_cond.items()):
        out[cond] = {k: bootstrap_ci(_col(group, k), seed=seed) for k in _HEADLINE_KEYS}
    return out


# ── top-level ────────────────────────────────────────────────────────────────


def run_statistics(all_cells: list[dict], *, seed: int = 0) -> dict[str, Any]:
    """Full statistical analysis across the whole matrix.

    Splits by backend, evaluates hypotheses per backend, and assembles a
    cross-backend comparison of headline metrics (condition A).
    """
    backends: dict[str, list[dict]] = {}
    for c in all_cells:
        backends.setdefault(c.get("backend"), []).append(c)

    per_backend: dict[str, Any] = {}
    for backend, cells in sorted(backends.items()):
        per_backend[backend] = {
            "n_cells": len(cells),
            "headline_cis": headline_cis(cells, seed=seed),
            **evaluate_backend(cells, seed=seed),
        }

    # Cross-backend: condition-A headline means side by side.
    cross: dict[str, Any] = {}
    for key in _HEADLINE_KEYS:
        cross[key] = {}
        for backend, cells in sorted(backends.items()):
            a_cells = [c for c in cells if c.get("condition") == "A"]
            cross[key][backend] = bootstrap_ci(_col(a_cells, key), seed=seed)

    return {
        "n_cells_total": len(all_cells),
        "backends": sorted(backends.keys()),
        "per_backend": per_backend,
        "cross_backend_conditionA": cross,
    }
