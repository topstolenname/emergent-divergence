#!/usr/bin/env python3
"""Generate figures from emergent-divergence experiment results.

Usage:
    python scripts/generate_figures.py --run-dir data/raw_logs/<run_id>
    python scripts/generate_figures.py --analysis data/raw_logs/<run_id>/analysis_report.json

Outputs figures to data/reports/figures/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


AGENT_COLORS = {
    "agent_0": "#4C72B0",  # blue — Proposer
    "agent_1": "#DD8452",  # orange — Critic
    "agent_2": "#55A868",  # green — Synthesizer
}
AGENT_LABELS = {
    "agent_0": "Agent 0 (Proposer)",
    "agent_1": "Agent 1 (Critic)",
    "agent_2": "Agent 2 (Synthesizer)",
}
FIGURE_DIR = Path("data/reports/figures")


def load_report(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


# ── Figure 1: JSD Over Time ───────────────────────────────────────────────────

def fig_jsd_trajectories(report: dict, out_dir: Path, run_label: str = "") -> Path:
    """Line plot of sliding-window mean JSD over rounds."""
    jsd_over_time = report.get("linguistic_divergence", {}).get("jsd_over_time", [])
    if not jsd_over_time:
        print("  [skip] No jsd_over_time data found.")
        return None

    windows = [w["window_start"] for w in jsd_over_time]
    mean_jsd = [w["mean_jsd"] for w in jsd_over_time]

    # Extract per-pair trajectories if available
    pair_data: dict[str, list[float]] = {}
    for w in jsd_over_time:
        for pair, val in w.get("pairwise_jsd", {}).items():
            pair_data.setdefault(pair, []).append(val)

    fig, ax = plt.subplots(figsize=(10, 5))

    # Per-pair lines (light)
    pair_colors = ["#a8c4e0", "#f0b97a", "#96d4a8"]
    for i, (pair, vals) in enumerate(sorted(pair_data.items())):
        ax.plot(windows[:len(vals)], vals,
                alpha=0.4, linewidth=1.2, linestyle="--",
                color=pair_colors[i % len(pair_colors)],
                label=pair.replace("_vs_", " vs "))

    # Mean JSD (bold)
    ax.plot(windows, mean_jsd,
            color="#2d3a4a", linewidth=2.5, label="Mean JSD", zorder=5)

    # Trend annotation
    if len(mean_jsd) > 1:
        early = np.mean(mean_jsd[:5])
        peak = max(mean_jsd)
        ax.axhline(early, color="gray", linewidth=0.8, linestyle=":")
        ax.annotate(f"Early avg: {early:.3f}", xy=(windows[2], early),
                    xytext=(windows[2], early - 0.012),
                    fontsize=8, color="gray")

    ax.set_xlabel("Window Start (Round)", fontsize=11)
    ax.set_ylabel("Jensen-Shannon Divergence", fontsize=11)
    title = "Linguistic Divergence Over Time (Sliding Window, w=10)"
    if run_label:
        title += f"\n{run_label}"
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.legend(fontsize=8, loc="lower right")
    ax.set_ylim(0, max(mean_jsd) * 1.2)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()

    out_path = out_dir / "fig_jsd_trajectories.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")
    return out_path


# ── Figure 2: Behavioral Profile Radar ───────────────────────────────────────

def fig_behavioral_profiles(report: dict, out_dir: Path, run_label: str = "") -> Path:
    """Radar chart of per-agent behavioral category scores."""
    profiles = report.get("behavioral_specialization", {}).get("profiles", {})
    if not profiles:
        print("  [skip] No behavioral profile data found.")
        return None

    categories = ["proposal", "critique", "synthesis", "verification", "recall", "clarification"]
    N = len(categories)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]  # close the loop

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))

    for agent_id, profile in sorted(profiles.items()):
        values = [profile.get(cat, 0.0) for cat in categories]
        values += values[:1]
        color = AGENT_COLORS.get(agent_id, "#888888")
        label = AGENT_LABELS.get(agent_id, agent_id)
        ax.plot(angles, values, "o-", linewidth=2, color=color, label=label)
        ax.fill(angles, values, alpha=0.1, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([c.capitalize() for c in categories], fontsize=10)
    ax.set_ylim(0, max(
        max(p.get(c, 0) for c in categories)
        for p in profiles.values()
    ) * 1.3)

    title = "Behavioral Specialization Profiles by Agent"
    if run_label:
        title += f"\n{run_label}"
    ax.set_title(title, fontsize=12, fontweight="bold", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)
    fig.tight_layout()

    out_path = out_dir / "fig_behavioral_profiles.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")
    return out_path


# ── Figure 3: Pairwise JSD Heatmap ───────────────────────────────────────────

def fig_pairwise_jsd_heatmap(report: dict, out_dir: Path, run_label: str = "") -> Path:
    """Heatmap of pairwise JSD between all agent pairs."""
    pairwise = report.get("linguistic_divergence", {}).get("pairwise_jsd", {})
    if not pairwise:
        print("  [skip] No pairwise JSD data found.")
        return None

    # Parse agent IDs
    agent_ids = sorted(set(
        aid
        for pair in pairwise
        for aid in pair.split("_vs_")
    ))
    n = len(agent_ids)
    matrix = np.zeros((n, n))

    for pair, val in pairwise.items():
        parts = pair.split("_vs_")
        if len(parts) == 2:
            i = agent_ids.index(parts[0])
            j = agent_ids.index(parts[1])
            matrix[i][j] = val
            matrix[j][i] = val

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(matrix, cmap="YlOrRd", vmin=0, vmax=0.5)
    plt.colorbar(im, ax=ax, label="Jensen-Shannon Divergence")

    short_labels = [AGENT_LABELS.get(a, a).split(" ")[0] + "\n" +
                    AGENT_LABELS.get(a, a).split("(")[-1].rstrip(")")
                    for a in agent_ids]
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(short_labels, fontsize=9)
    ax.set_yticklabels(short_labels, fontsize=9)

    for i in range(n):
        for j in range(n):
            val = matrix[i][j]
            ax.text(j, i, f"{val:.3f}" if val > 0 else "—",
                    ha="center", va="center",
                    fontsize=10, fontweight="bold",
                    color="black" if val < 0.3 else "white")

    title = "Pairwise Linguistic Divergence (JSD)"
    if run_label:
        title += f"\n{run_label}"
    ax.set_title(title, fontsize=12, fontweight="bold")
    fig.tight_layout()

    out_path = out_dir / "fig_pairwise_jsd_heatmap.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate emergent-divergence figures")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-dir", type=Path,
                       help="Path to run directory (contains analysis_report.json)")
    group.add_argument("--analysis", type=Path,
                       help="Path directly to analysis_report.json")
    parser.add_argument("--out-dir", type=Path, default=FIGURE_DIR,
                        help="Output directory for figures (default: data/reports/figures)")
    args = parser.parse_args()

    # Resolve report path
    if args.run_dir:
        report_path = args.run_dir / "analysis_report.json"
        run_label = args.run_dir.name
    else:
        report_path = args.analysis
        run_label = report_path.parent.name

    if not report_path.exists():
        print(f"ERROR: Report not found at {report_path}")
        raise SystemExit(1)

    print(f"Loading report: {report_path}")
    report = load_report(report_path)

    # Create output dir
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {out_dir}\n")

    # Generate all figures
    fig_jsd_trajectories(report, out_dir, run_label)
    fig_behavioral_profiles(report, out_dir, run_label)
    fig_pairwise_jsd_heatmap(report, out_dir, run_label)

    print("\nDone.")


if __name__ == "__main__":
    main()
