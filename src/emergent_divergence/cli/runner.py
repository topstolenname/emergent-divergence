"""CLI entry point for the experiment.

Commands:
  run      - Execute an experiment with a given config
  analyze  - Analyze a completed run
  compare  - Compare two runs (e.g., memory vs no-memory)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def cmd_run(args: argparse.Namespace) -> None:
    """Execute an experiment run."""
    from emergent_divergence.orchestration.runner import ExperimentConfig, ExperimentRunner

    # Load config from YAML
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path) as f:
            cfg_data = yaml.safe_load(f)
    else:
        print(f"Config file not found: {config_path}")
        sys.exit(1)

    # CLI overrides
    if args.rounds:
        cfg_data["num_rounds"] = args.rounds
    if args.backend:
        cfg_data["backend"] = args.backend

    config = ExperimentConfig(**cfg_data)
    runner = ExperimentRunner(config)
    run_dir = runner.run()  # synchronous wrapper handles asyncio.run()
    print(f"\nRun complete: {run_dir}")


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze a completed experiment run."""
    from emergent_divergence.metrics.divergence import generate_analysis_report

    run_dir = Path(args.run_dir)
    log_path = run_dir / "events.jsonl"

    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        sys.exit(1)

    print(f"Analyzing: {log_path}")
    report = generate_analysis_report(log_path)

    # Semantic analysis (opt-in)
    if args.semantic:
        from emergent_divergence.metrics.semantic_divergence import run_semantic_analysis
        print("\nRunning semantic analysis...")
        semantic_report = run_semantic_analysis(run_dir)
        report["semantic_divergence"] = semantic_report

    # Save report
    report_path = run_dir / "analysis_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Report saved: {report_path}")

    # Print summary
    ld = report.get("linguistic_divergence", {})
    bs = report.get("behavioral_specialization", {})
    print(f"\n{'=' * 60}")
    print(f"  ANALYSIS SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total messages: {report.get('total_messages', 0)}")
    print(f"  Agent count:    {report.get('agent_count', 0)}")
    print(f"\n  Linguistic Divergence:")
    print(f"    Mean JSD:           {ld.get('mean_jsd', 'N/A')}")
    print(f"    Lexical uniqueness: {ld.get('lexical_uniqueness', {})}")
    print(f"\n  Behavioral Specialization:")
    print(f"    Divergence score:   {bs.get('divergence_score', 'N/A')}")
    for aid, prof in bs.get("profiles", {}).items():
        top = sorted(prof.items(), key=lambda x: x[1], reverse=True)[:3]
        top_str = ", ".join(f"{k}={v}" for k, v in top)
        print(f"    {aid}: {top_str}")
    sd = report.get("semantic_divergence", {})
    if sd and "error" not in sd:
        print(f"\n  Semantic Divergence:")
        print(f"    Mean cosine distance: {sd.get('mean_cosine_distance', 'N/A')}")
        for pair, ps in sd.get("pairwise_summaries", {}).items():
            print(f"    {pair}: mean={ps['mean']}, trend={ps['trend']:+.6f}")
    print(f"{'=' * 60}")


def cmd_compare(args: argparse.Namespace) -> None:
    """Compare two experiment runs."""
    from emergent_divergence.metrics.divergence import (
        compare_conditions,
        generate_analysis_report,
    )

    runs = args.runs
    if len(runs) != 2:
        print("Provide exactly 2 run directories to compare.")
        sys.exit(1)

    reports = []
    for run_dir in runs:
        log_path = Path(run_dir) / "events.jsonl"
        if not log_path.exists():
            print(f"Log not found: {log_path}")
            sys.exit(1)
        reports.append(generate_analysis_report(log_path))

    comparison = compare_conditions(reports[0], reports[1])

    # Save
    out_path = Path("data/reports/comparison.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(comparison, f, indent=2)

    print(json.dumps(comparison, indent=2))
    print(f"\nComparison saved: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="emergent-divergence",
        description="Multi-agent behavioral divergence experiment",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subparsers.add_parser("run", help="Execute an experiment")
    p_run.add_argument("--config", required=True, help="Path to YAML config")
    p_run.add_argument("--rounds", type=int, help="Override number of rounds")
    p_run.add_argument("--backend", choices=["anthropic", "claude-code", "mock"],
                       help="Override LLM backend (default: from config)")
    p_run.set_defaults(func=cmd_run)

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze a completed run")
    p_analyze.add_argument("--run-dir", required=True, help="Path to run directory")
    p_analyze.add_argument("--semantic", action="store_true",
                           help="Include embedding-based semantic divergence analysis")
    p_analyze.set_defaults(func=cmd_analyze)

    # compare
    p_compare = subparsers.add_parser("compare", help="Compare two runs")
    p_compare.add_argument("--runs", nargs=2, required=True, help="Two run directories")
    p_compare.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
