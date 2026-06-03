"""Per-cell metric aggregation: the bridge from one cell's log to statistics.

:func:`analyze_cell` reads a single cell's ``events.jsonl`` and returns:

* ``report`` — the rich nested analysis (linguistic, behavioral, semantic,
  influence) for the per-cell appendix; and
* ``summary`` — a *flat* dict of headline scalars (one row of ``results.csv``)
  with the exact keys :mod:`emergent_divergence.metrics.statistics` expects.

This is where the three metric families are combined per cell and where the
two per-round series (semantic divergence and influence magnitude) are joined
for the lagged-correlation test (H-I3).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from emergent_divergence.logging_.events import load_events
from emergent_divergence.metrics.divergence import (
    compute_jsd_over_time,
    compute_temporal_correlation,
    generate_analysis_report,
    load_agent_messages,
)
from emergent_divergence.metrics.influence_delta import analyze_influence, lagged_correlation
from emergent_divergence.metrics.semantic_divergence import (
    _load_agent_responses,
    compute_embeddings,
    compute_per_round_cosine_distances,
)


def _load_config(log_path: Path) -> dict[str, Any]:
    for ev in load_events(log_path):
        if ev.get("event_type") == "experiment_config":
            return ev.get("data", {})
    return {}


def _per_round_semantic(log_path: Path, embedder=None) -> tuple[dict[int, float], dict[str, Any]]:
    """Per-round mean pairwise cosine distance + a trend summary (H3 series)."""
    responses = _load_agent_responses(log_path)
    if len(responses) < 2:
        return {}, {"available": False}
    embeddings = compute_embeddings(responses)
    rows = compute_per_round_cosine_distances(responses, embeddings, window_size=10)
    by_round: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        by_round[r["round"]].append(r["cosine_distance"])
    series = {rid: float(np.mean(v)) for rid, v in by_round.items()}

    rho = p = None
    if len(series) >= 5:
        from scipy.stats import spearmanr

        rounds = sorted(series)
        vals = [series[r] for r in rounds]
        if len(set(vals)) > 1:
            rr, pp = spearmanr(rounds, vals)
            if np.isfinite(rr):
                rho, p = round(float(rr), 4), float(pp)

    mean_cos = float(np.mean(list(series.values()))) if series else 0.0
    rounds_sorted = sorted(series)
    third = max(1, len(rounds_sorted) // 3)
    early = np.mean([series[r] for r in rounds_sorted[:third]]) if rounds_sorted else 0.0
    late = np.mean([series[r] for r in rounds_sorted[-third:]]) if rounds_sorted else 0.0
    summary = {
        "available": bool(series),
        "mean_cosine": round(mean_cos, 6),
        "spearman_rho": rho,
        "spearman_p": p,
        "early_mean": round(float(early), 6),
        "late_mean": round(float(late), 6),
        "trend": round(float(late - early), 6),
        "n_rounds": len(series),
    }
    return series, summary


def analyze_cell(run_dir: Path, embedder=None) -> dict[str, Any]:
    """Analyze one matrix cell. Returns ``{"summary": {...}, "report": {...}}``."""
    run_dir = Path(run_dir)
    log_path = run_dir / "events.jsonl"
    if not log_path.exists():
        return {"summary": {"error": f"no log at {log_path}"}, "report": {}}

    if embedder is None:
        from emergent_divergence.embeddings import get_embedder

        embedder = get_embedder()

    cfg = _load_config(log_path)
    ling = generate_analysis_report(log_path)
    sem_series, sem_summary = _per_round_semantic(log_path, embedder)
    infl = analyze_influence(run_dir, embedder)

    # H1: Spearman ρ of windowed pairwise JSD over rounds. Use an adaptive window
    # so the trend is estimable below the default 50-round run (needs ≥5 windows).
    h1_rho = None
    agent_messages = load_agent_messages(log_path)
    n_rounds = int(cfg.get("num_rounds") or 0)
    window = min(10, max(2, n_rounds // 5)) if n_rounds else 10
    jsd_over_time = compute_jsd_over_time(agent_messages, window_size=window)
    temporal = compute_temporal_correlation(jsd_over_time)
    if isinstance(temporal, dict) and "rho" in temporal:
        h1_rho = temporal["rho"]

    # H-I3: lag influence (per measured round) against divergence (same rounds).
    lag = {"error": "no influence series"}
    influence_precedes = None
    influence_lag_rho = None
    if infl.get("available") and sem_series:
        lag = lagged_correlation(infl.get("per_round_influence", {}), sem_series, max_lag=3)
        if "best_rho" in lag:
            influence_precedes = lag.get("precedes")
            influence_lag_rho = lag.get("best_rho")

    summary = {
        "cell_id": run_dir.name,
        "backend": cfg.get("backend"),
        "condition": cfg.get("condition"),
        "seed": cfg.get("seed"),
        "provider": cfg.get("provider"),
        "model": cfg.get("model"),
        "rounds": cfg.get("num_rounds"),
        # H1 linguistic
        "linguistic_mean_jsd": ling.get("linguistic_divergence", {}).get("mean_jsd"),
        "h1_jsd_rho": h1_rho,
        # H2 behavioral
        "behavioral_divergence": ling.get("behavioral_specialization", {}).get(
            "divergence_score"
        ),
        # H3 semantic
        "semantic_mean": sem_summary.get("mean_cosine"),
        "semantic_rho": sem_summary.get("spearman_rho"),
        "semantic_trend": sem_summary.get("trend"),
        # Influence (H-I1, H-I2, H-I3)
        "influence_available": infl.get("available", False),
        "influence_mean_sem": infl.get("mean_influence_sem") if infl.get("available") else None,
        "influence_gini": infl.get("gini_sem") if infl.get("available") else None,
        "influence_hub": infl.get("hub") if infl.get("available") else None,
        "influence_hub_net_positive": (
            infl.get("hub_net_positive") if infl.get("available") else None
        ),
        "influence_precedes": influence_precedes,
        "influence_lag_rho": influence_lag_rho,
        "embedder_backend": embedder.info().get("backend"),
    }

    report = {
        "config": cfg,
        "linguistic": ling,
        "h1_temporal_correlation": temporal,
        "semantic": sem_summary,
        "influence": infl,
        "lagged_influence_divergence": lag,
    }
    return {"summary": summary, "report": report}
