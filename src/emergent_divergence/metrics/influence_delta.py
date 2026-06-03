"""Cross-agent influence via counterfactual ablation (brief Appendix A).

The runner's influence probe logs, per measured round, a *factual* set of
continuations for each target agent (every other agent visible) and, for each
source ``i != target``, an *ablated* set where source ``i`` is removed from the
target's context. This module turns those logged samples into an **influence
matrix** and its derived structure.

Two influence-delta signals per (source -> target) pair:

* ``id_sem`` — semantic delta: cosine distance between the centroid embedding of
  the factual continuations and the centroid of the source-ablated continuations
  (shared :class:`Embedder`, so Ollama/Claude are comparable).
* ``id_tok`` — token delta: Jensen-Shannon divergence (base 2, in ``[0, 1]``)
  between the pooled word-frequency distribution of the factual vs. ablated
  continuations.

Aggregated over measured rounds these give matrices ``M[source, target]``. From a
matrix we derive:

* **row sums** = total outgoing influence of a source;
* **hub** = source with the largest row sum (H-I2 hub formation);
* **asymmetry** ``A = M - Mᵀ`` and its row sums = *net* directed influence;
* **concentration** = Gini coefficient of the row-sum distribution (0 = uniform,
  ``-> 1`` = one dominant hub).

**Honesty (carry into the report):** this measures *influence* — how much one
agent's presence changes another's output — **not manipulation or intent**.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial.distance import jensenshannon

_TOKEN_RE = re.compile(r"\b\w+\b")


# ── math primitives (unit-tested directly) ──────────────────────────────────


def gini(values: np.ndarray | list[float]) -> float:
    """Gini coefficient of a non-negative vector, in ``[0, 1]``.

    ``0`` when all entries are equal (perfectly uniform influence); approaches
    ``1`` as mass concentrates on a single source (a hub). Returns ``0`` for an
    all-zero or empty vector.
    """
    x = np.asarray(values, dtype=np.float64).ravel()
    if x.size == 0:
        return 0.0
    x = np.clip(x, 0.0, None)
    total = x.sum()
    if total <= 0:
        return 0.0
    # Mean absolute difference / (2 * mean): O(n^2) but n is tiny (agents).
    diffs = np.abs(x[:, None] - x[None, :]).sum()
    g = diffs / (2.0 * x.size * total)
    return float(np.clip(g, 0.0, 1.0))


def jsd_distributions(p: np.ndarray, q: np.ndarray) -> float:
    """Jensen-Shannon divergence (base 2) between two distributions, in ``[0, 1]``.

    ``0`` iff identical, ``1`` for disjoint support. Inputs are normalised
    defensively; ``scipy.jensenshannon`` returns the *distance* (sqrt of the
    divergence) so we square it to land in ``[0, 1]``.
    """
    p = np.asarray(p, dtype=np.float64).ravel()
    q = np.asarray(q, dtype=np.float64).ravel()
    if p.size != q.size or p.size == 0:
        return 0.0
    ps, qs = p.sum(), q.sum()
    if ps <= 0 or qs <= 0:
        return 0.0
    dist = jensenshannon(p / ps, q / qs, base=2)
    if not np.isfinite(dist):
        return 0.0
    return float(np.clip(dist * dist, 0.0, 1.0))


def _word_distributions(a_texts: list[str], b_texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Build matched word-frequency vectors over the shared vocabulary of A∪B."""
    def toks(texts: list[str]) -> list[str]:
        out: list[str] = []
        for t in texts:
            out.extend(_TOKEN_RE.findall(t.lower()))
        return out

    a_tok, b_tok = toks(a_texts), toks(b_texts)
    vocab = sorted(set(a_tok) | set(b_tok))
    if not vocab:
        return np.zeros(1), np.zeros(1)
    index = {w: i for i, w in enumerate(vocab)}
    pa = np.zeros(len(vocab), dtype=np.float64)
    pb = np.zeros(len(vocab), dtype=np.float64)
    for w in a_tok:
        pa[index[w]] += 1.0
    for w in b_tok:
        pb[index[w]] += 1.0
    return pa, pb


def jsd_tokens(a_texts: list[str], b_texts: list[str]) -> float:
    """Token-distribution JSD between two pools of text (base 2, ``[0, 1]``)."""
    pa, pb = _word_distributions(a_texts, b_texts)
    return jsd_distributions(pa, pb)


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 1.0
    return float(np.clip(1.0 - np.dot(a, b) / (na * nb), 0.0, 2.0))


def semantic_delta(factual_texts: list[str], ablated_texts: list[str], embedder) -> float:
    """Cosine distance between centroid embeddings of two continuation pools."""
    if not factual_texts or not ablated_texts:
        return 0.0
    f = embedder.embed(factual_texts).mean(axis=0)
    a = embedder.embed(ablated_texts).mean(axis=0)
    return _cosine_distance(f, a)


# ── log loading ──────────────────────────────────────────────────────────────


def load_influence_probes(log_path: Path) -> dict[int, dict[str, Any]]:
    """Group probe events by round.

    Returns ``{round_id: {"factual": {target: [texts]},
    "ablated": {(target, source): [texts]}}}``.
    """
    by_round: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"factual": {}, "ablated": {}}
    )
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            et = ev.get("event_type")
            if et not in ("influence_probe_factual", "influence_probe_ablated"):
                continue
            rid = ev.get("round_id")
            data = ev.get("data", {})
            samples = data.get("samples", []) or []
            if et == "influence_probe_factual":
                target = ev.get("agent_id") or data.get("agent_id")
                if target is not None:
                    by_round[rid]["factual"][target] = samples
            else:
                target = data.get("target")
                source = data.get("source")
                if target is not None and source is not None:
                    by_round[rid]["ablated"][(target, source)] = samples
    return dict(by_round)


def _agent_ids(probes: dict[int, dict[str, Any]]) -> list[str]:
    ids: set[str] = set()
    for r in probes.values():
        ids.update(r["factual"].keys())
        for (t, s) in r["ablated"].keys():
            ids.add(t)
            ids.add(s)
    return sorted(ids, key=lambda a: (len(a), a))


# ── matrix construction ──────────────────────────────────────────────────────


def compute_influence_matrices(
    probes: dict[int, dict[str, Any]],
    embedder,
    agent_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build aggregate ``M_sem`` and ``M_tok`` matrices ``M[source, target]``.

    Each measured round contributes one ``id_sem``/``id_tok`` per ``(source,
    target)`` with ``source != target``; the matrix entry is the mean over rounds.
    Also returns per-round overall influence magnitude (mean off-diagonal id_sem)
    for the lagged-correlation test (H-I3).
    """
    agents = agent_ids or _agent_ids(probes)
    n = len(agents)
    idx = {a: i for i, a in enumerate(agents)}

    sum_sem = np.zeros((n, n), dtype=np.float64)
    sum_tok = np.zeros((n, n), dtype=np.float64)
    cnt = np.zeros((n, n), dtype=np.float64)
    per_round_sem: dict[int, float] = {}

    for rid in sorted(probes.keys()):
        factual = probes[rid]["factual"]
        ablated = probes[rid]["ablated"]
        round_vals: list[float] = []
        for (target, source), abl_texts in ablated.items():
            if target not in idx or source not in idx:
                continue
            fac_texts = factual.get(target, [])
            ds = semantic_delta(fac_texts, abl_texts, embedder)
            dt = jsd_tokens(fac_texts, abl_texts)
            i, j = idx[source], idx[target]
            sum_sem[i, j] += ds
            sum_tok[i, j] += dt
            cnt[i, j] += 1.0
            round_vals.append(ds)
        if round_vals:
            per_round_sem[rid] = float(np.mean(round_vals))

    m_sem = np.divide(sum_sem, cnt, out=np.zeros_like(sum_sem), where=cnt > 0)
    m_tok = np.divide(sum_tok, cnt, out=np.zeros_like(sum_tok), where=cnt > 0)
    return {
        "agents": agents,
        "M_sem": m_sem,
        "M_tok": m_tok,
        "counts": cnt,
        "per_round_influence": per_round_sem,
    }


def influence_hub(matrix: np.ndarray) -> int:
    """Index of the source with the largest outgoing (row-sum) influence."""
    if matrix.size == 0:
        return -1
    return int(np.argmax(matrix.sum(axis=1)))


def matrix_summary(matrix: np.ndarray, agent_ids: list[str]) -> dict[str, Any]:
    """Row/column sums, hub, asymmetry, and concentration for one matrix."""
    n = len(agent_ids)
    if n == 0 or matrix.size == 0:
        return {"agents": agent_ids, "hub": None, "gini_outgoing": 0.0}
    row_sums = matrix.sum(axis=1)
    col_sums = matrix.sum(axis=0)
    asym = matrix - matrix.T
    asym_row = asym.sum(axis=1)
    hub_i = int(np.argmax(row_sums))
    off = matrix[~np.eye(n, dtype=bool)]
    return {
        "agents": agent_ids,
        "matrix": matrix.round(6).tolist(),
        "row_sums": {agent_ids[i]: round(float(row_sums[i]), 6) for i in range(n)},
        "col_sums": {agent_ids[i]: round(float(col_sums[i]), 6) for i in range(n)},
        "hub": agent_ids[hub_i],
        "hub_row_sum": round(float(row_sums[hub_i]), 6),
        "asymmetry_matrix": asym.round(6).tolist(),
        "asymmetry_row_sums": {
            agent_ids[i]: round(float(asym_row[i]), 6) for i in range(n)
        },
        "hub_net_positive": bool(asym_row[hub_i] > 0),
        "gini_outgoing": round(gini(row_sums), 6),
        "mean_offdiagonal": round(float(off.mean()) if off.size else 0.0, 6),
        "max_offdiagonal": round(float(off.max()) if off.size else 0.0, 6),
    }


# ── lagged influence -> divergence (H-I3) ────────────────────────────────────


def lagged_correlation(
    influence_by_round: dict[int, float],
    divergence_by_round: dict[int, float],
    max_lag: int = 3,
) -> dict[str, Any]:
    """Spearman ρ between influence at round ``t`` and divergence at ``t + lag``.

    Reports the best (largest-magnitude significant) positive lag, supporting
    H-I3 ("influence precedes divergence") when the peak correlation is positive
    at ``lag >= 1``. Requires enough overlapping points; otherwise returns a
    diagnostic ``error``.
    """
    from scipy.stats import spearmanr

    rounds = sorted(set(influence_by_round) | set(divergence_by_round))
    results: list[dict[str, Any]] = []
    for lag in range(0, max_lag + 1):
        xs, ys = [], []
        for r in rounds:
            if r in influence_by_round and (r + lag) in divergence_by_round:
                xs.append(influence_by_round[r])
                ys.append(divergence_by_round[r + lag])
        if len(xs) >= 4 and len(set(xs)) > 1 and len(set(ys)) > 1:
            rho, p = spearmanr(xs, ys)
            if np.isfinite(rho):
                results.append(
                    {"lag": lag, "rho": round(float(rho), 4),
                     "p_value": float(p), "n": len(xs)}
                )
    if not results:
        return {"error": "insufficient overlapping (influence, divergence) points",
                "by_lag": []}
    positive = [r for r in results if r["lag"] >= 1]
    pool = positive or results
    best = max(pool, key=lambda d: d["rho"])
    return {
        "by_lag": results,
        "best_lag": best["lag"],
        "best_rho": best["rho"],
        "best_p_value": best["p_value"],
        "precedes": bool(best["lag"] >= 1 and best["rho"] > 0 and best["p_value"] < 0.05),
    }


# ── top-level per-cell analysis ──────────────────────────────────────────────


def analyze_influence(run_dir: Path, embedder=None) -> dict[str, Any]:
    """Full influence analysis for one completed/partial cell.

    Returns matrices, summaries (sem & tok), and the per-round influence series
    needed for the lagged-correlation test. Safe to call on cells with no probe
    events (returns ``available: False``).
    """
    run_dir = Path(run_dir)
    log_path = run_dir / "events.jsonl"
    if not log_path.exists():
        return {"available": False, "error": f"no log at {log_path}"}

    probes = load_influence_probes(log_path)
    if not probes:
        return {"available": False, "error": "no influence probe events"}

    if embedder is None:
        from emergent_divergence.embeddings import get_embedder

        embedder = get_embedder()

    mats = compute_influence_matrices(probes, embedder)
    agents = mats["agents"]
    sem_summary = matrix_summary(mats["M_sem"], agents)
    tok_summary = matrix_summary(mats["M_tok"], agents)

    return {
        "available": True,
        "agents": agents,
        "measured_rounds": sorted(probes.keys()),
        "embedder": embedder.info(),
        "semantic": sem_summary,
        "token": tok_summary,
        "per_round_influence": mats["per_round_influence"],
        # Headline scalars for the results table / hypotheses.
        "mean_influence_sem": sem_summary.get("mean_offdiagonal", 0.0),
        "gini_sem": sem_summary.get("gini_outgoing", 0.0),
        "hub": sem_summary.get("hub"),
        "hub_net_positive": sem_summary.get("hub_net_positive", False),
    }
