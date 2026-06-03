"""Embedding-based semantic divergence metrics.

Supplements the keyword-based behavioral classification (Metric B) with
dense vector representations that capture semantic trajectory over time.

Requires: pip install sentence-transformers  (or install with [analysis] extra)
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np


# ── Log Loading (mirrors divergence.py helpers) ─────────────────────────────

def _load_agent_responses(log_path: Path) -> dict[str, list[dict]]:
    """Load agent responses grouped by agent_id, sorted by round.

    Each entry: {"round_id": int, "text": str}
    """
    agents: dict[str, list[dict]] = defaultdict(list)
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            event = json.loads(line.strip())
            if event.get("event_type") != "agent_message":
                continue
            data = event.get("data", {})
            agent_id = data.get("agent_id") or event.get("agent_id")
            round_id = data.get("round_id") or event.get("round_id")
            text = data.get("response_text", "")
            if agent_id and text:
                agents[agent_id].append({"round_id": round_id, "text": text})

    # Sort by round
    for aid in agents:
        agents[aid].sort(key=lambda x: x["round_id"] or 0)
    return dict(agents)


# ── Embedding ────────────────────────────────────────────────────────────────

def _get_embedder():
    """Load sentence-transformers model (cached after first call)."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers is required for semantic analysis. "
            "Install with: pip install sentence-transformers"
        )
    return SentenceTransformer("all-MiniLM-L6-v2")


def compute_embeddings(
    agent_responses: dict[str, list[dict]],
) -> dict[str, np.ndarray]:
    """Compute embeddings for all agent responses.

    Returns dict of agent_id -> (N, D) array where N = number of messages.
    """
    model = _get_embedder()
    result = {}
    for aid, responses in agent_responses.items():
        texts = [r["text"] for r in responses]
        if texts:
            result[aid] = model.encode(texts, show_progress_bar=False)
        else:
            result[aid] = np.empty((0, 384))
    return result


# ── Pairwise Cosine Distance ────────────────────────────────────────────────

def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine distance between two vectors."""
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 1.0
    return 1.0 - dot / norm


def compute_per_round_cosine_distances(
    agent_responses: dict[str, list[dict]],
    embeddings: dict[str, np.ndarray],
    window_size: int = 10,
) -> list[dict]:
    """Compute per-round pairwise cosine distances with sliding-window mean.

    Returns list of dicts with: round, pair, cosine_distance, window_mean_cosine_distance
    """
    agent_ids = sorted(agent_responses.keys())
    if len(agent_ids) < 2:
        return []

    # Build round -> embedding index per agent
    agent_round_map: dict[str, dict[int, int]] = {}
    for aid in agent_ids:
        round_map = {}
        for idx, resp in enumerate(agent_responses[aid]):
            r = resp["round_id"]
            if r is not None:
                round_map[r] = idx
        agent_round_map[aid] = round_map

    # Find common rounds
    all_rounds = set()
    for aid in agent_ids:
        all_rounds.update(agent_round_map[aid].keys())
    rounds_sorted = sorted(all_rounds)

    # Compute per-round distances for each pair
    pair_labels = [f"{a1}_vs_{a2}" for a1, a2 in combinations(agent_ids, 2)]
    rows = []

    for pair_a1, pair_a2 in combinations(agent_ids, 2):
        pair_label = f"{pair_a1}_vs_{pair_a2}"
        distances_for_pair = []

        for r in rounds_sorted:
            idx1 = agent_round_map[pair_a1].get(r)
            idx2 = agent_round_map[pair_a2].get(r)
            if idx1 is None or idx2 is None:
                continue

            dist = _cosine_distance(
                embeddings[pair_a1][idx1],
                embeddings[pair_a2][idx2],
            )
            distances_for_pair.append((r, dist))

        # Compute sliding window mean
        for i, (r, dist) in enumerate(distances_for_pair):
            window_start = max(0, i - window_size + 1)
            window_vals = [d for _, d in distances_for_pair[window_start:i + 1]]
            window_mean = float(np.mean(window_vals))

            rows.append({
                "round": r,
                "pair": pair_label,
                "cosine_distance": round(dist, 6),
                "window_mean_cosine_distance": round(window_mean, 6),
            })

    return rows


def save_cosine_csv(rows: list[dict], output_path: Path) -> None:
    """Write cosine distance rows to CSV."""
    if not rows:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["round", "pair", "cosine_distance",
                                                "window_mean_cosine_distance"])
        writer.writeheader()
        writer.writerows(rows)


# ── Visualization ────────────────────────────────────────────────────────────

def plot_semantic_trajectories(
    agent_responses: dict[str, list[dict]],
    embeddings: dict[str, np.ndarray],
    output_path: Path,
) -> None:
    """2D PCA projection of agent embeddings, color-coded by agent ID."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.decomposition import PCA

    agent_ids = sorted(embeddings.keys())

    # Stack all embeddings
    all_vecs = []
    labels = []
    round_ids = []
    for aid in agent_ids:
        n = embeddings[aid].shape[0]
        all_vecs.append(embeddings[aid])
        labels.extend([aid] * n)
        round_ids.extend([r["round_id"] for r in agent_responses[aid][:n]])

    if not all_vecs:
        return

    X = np.vstack(all_vecs)
    if X.shape[0] < 2:
        return

    pca = PCA(n_components=2)
    X_2d = pca.fit_transform(X)

    fig, ax = plt.subplots(figsize=(10, 8))
    colors = ["#e63946", "#457b9d", "#2a9d8f"]

    offset = 0
    for i, aid in enumerate(agent_ids):
        n = embeddings[aid].shape[0]
        pts = X_2d[offset:offset + n]
        rnds = round_ids[offset:offset + n]
        color = colors[i % len(colors)]

        ax.scatter(pts[:, 0], pts[:, 1], c=color, alpha=0.4, s=20, label=aid)

        # Draw trajectory line
        if n > 1:
            ax.plot(pts[:, 0], pts[:, 1], c=color, alpha=0.2, linewidth=0.8)

        # Annotate early, mid, late
        if n >= 3:
            for idx, label_text in [(0, "early"), (n // 2, "mid"), (n - 1, "late")]:
                ax.annotate(
                    f"R{rnds[idx]}",
                    (pts[idx, 0], pts[idx, 1]),
                    fontsize=7, color=color, fontweight="bold",
                    xytext=(4, 4), textcoords="offset points",
                )

        offset += n

    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%} var)")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%} var)")
    ax.set_title("Semantic Trajectories (PCA of Response Embeddings)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_cosine_over_time(
    cosine_rows: list[dict],
    output_path: Path,
) -> None:
    """Line chart of cosine distance over rounds, one line per pair."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not cosine_rows:
        return

    # Group by pair
    pair_data: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for row in cosine_rows:
        pair_data[row["pair"]].append((
            row["round"],
            row["cosine_distance"],
            row["window_mean_cosine_distance"],
        ))

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = ["#e63946", "#457b9d", "#2a9d8f"]

    for i, (pair, data) in enumerate(sorted(pair_data.items())):
        data.sort()
        rounds = [d[0] for d in data]
        raw = [d[1] for d in data]
        windowed = [d[2] for d in data]
        color = colors[i % len(colors)]

        ax.plot(rounds, raw, c=color, alpha=0.25, linewidth=0.8)
        ax.plot(rounds, windowed, c=color, linewidth=2, label=f"{pair} (window=10)")

    ax.set_xlabel("Round")
    ax.set_ylabel("Cosine Distance")
    ax.set_title("Pairwise Semantic Distance Over Time")
    ax.legend()
    ax.grid(True, alpha=0.3)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ── Top-Level Analysis Function ──────────────────────────────────────────────

def run_semantic_analysis(run_dir: Path) -> dict[str, Any]:
    """Run full semantic divergence analysis on a completed experiment run.

    Args:
        run_dir: Path to the run directory containing events.jsonl

    Returns:
        Summary dict suitable for inclusion in analysis_report.json
    """
    log_path = run_dir / "events.jsonl"
    if not log_path.exists():
        return {"error": f"Log file not found: {log_path}"}

    print("  Loading agent responses...")
    agent_responses = _load_agent_responses(log_path)
    if not agent_responses:
        return {"error": "No agent messages found"}

    print("  Computing embeddings...")
    embeddings = compute_embeddings(agent_responses)

    print("  Computing cosine distances...")
    cosine_rows = compute_per_round_cosine_distances(
        agent_responses, embeddings, window_size=10
    )

    # Save CSV
    csv_path = run_dir / "semantic_cosine_distances.csv"
    save_cosine_csv(cosine_rows, csv_path)
    print(f"  Saved: {csv_path}")

    # Generate plots
    print("  Generating trajectory plot...")
    plot_semantic_trajectories(
        agent_responses, embeddings,
        run_dir / "semantic_trajectories.png",
    )
    print(f"  Saved: {run_dir / 'semantic_trajectories.png'}")

    print("  Generating cosine distance plot...")
    plot_cosine_over_time(
        cosine_rows,
        run_dir / "semantic_cosine_over_time.png",
    )
    print(f"  Saved: {run_dir / 'semantic_cosine_over_time.png'}")

    # Compute summary statistics
    if cosine_rows:
        all_distances = [r["cosine_distance"] for r in cosine_rows]
        # Early vs late comparison
        pairs = sorted(set(r["pair"] for r in cosine_rows))
        pair_summaries = {}
        for pair in pairs:
            pair_dists = [r["cosine_distance"] for r in cosine_rows if r["pair"] == pair]
            n = len(pair_dists)
            early = pair_dists[:n // 3] if n >= 3 else pair_dists
            late = pair_dists[-(n // 3):] if n >= 3 else pair_dists
            pair_summaries[pair] = {
                "mean": round(float(np.mean(pair_dists)), 6),
                "std": round(float(np.std(pair_dists)), 6),
                "early_mean": round(float(np.mean(early)), 6),
                "late_mean": round(float(np.mean(late)), 6),
                "trend": round(float(np.mean(late)) - float(np.mean(early)), 6),
            }

        summary = {
            "mean_cosine_distance": round(float(np.mean(all_distances)), 6),
            "std_cosine_distance": round(float(np.std(all_distances)), 6),
            "pairwise_summaries": pair_summaries,
            "csv_path": str(csv_path),
            "trajectory_plot": str(run_dir / "semantic_trajectories.png"),
            "distance_plot": str(run_dir / "semantic_cosine_over_time.png"),
        }
    else:
        summary = {"error": "No cosine distances computed"}

    return summary
