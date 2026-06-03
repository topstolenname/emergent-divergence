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


def cmd_run(args: argparse.Namespace) -> None:
    """Execute a single matrix cell (backend × condition × seed).

    The full backend×condition×seed sweep lives in the ``pipeline`` command; this
    is the low-level escape hatch to run one cell to a chosen directory.
    """
    from emergent_divergence.orchestration.runner import CellConfig, CellRunner
    from emergent_divergence.providers import build_provider

    backend = args.backend or "stub"
    run_dir = Path(args.run_dir or f"data/raw_logs/{backend}_{args.condition}_seed{args.seed}")

    cfg = CellConfig(
        backend=backend,
        condition=args.condition,
        seed=args.seed,
        num_rounds=args.rounds or 50,
    )
    provider = build_provider(backend, {"model": args.model} if args.model else {})
    result = CellRunner(cfg, provider, run_dir).run()

    print(f"\nCell {result.cell_id}: {result.status} "
          f"({result.rounds_done}/{result.rounds_total} rounds, ${result.cost_usd:.4f})")
    print(f"Run dir: {result.run_dir}")
    if result.status != "done":
        sys.exit(1)


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze a completed experiment run."""
    from emergent_divergence.metrics.divergence import generate_analysis_report

    run_dir = Path(args.run_dir)
    log_path = run_dir / "events.jsonl"

    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        sys.exit(1)

    from emergent_divergence.metrics.llm_judge import DEFAULT_JUDGE_MODEL

    print(f"Analyzing: {log_path}")
    classifier = getattr(args, "classifier", "keyword")
    judge_model = getattr(args, "judge_model", DEFAULT_JUDGE_MODEL)
    if classifier != "keyword":
        print(f"  Behavioral classifier: {classifier} (judge model: {judge_model})")
    report = generate_analysis_report(
        log_path,
        classifier=classifier,
        judge_model=judge_model,
    )

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
    print("  ANALYSIS SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total messages: {report.get('total_messages', 0)}")
    print(f"  Agent count:    {report.get('agent_count', 0)}")
    print("\n  Linguistic Divergence:")
    print(f"    Mean JSD:           {ld.get('mean_jsd', 'N/A')}")
    print(f"    Lexical uniqueness: {ld.get('lexical_uniqueness', {})}")
    print("\n  Behavioral Specialization:")
    print(f"    Divergence score:   {bs.get('divergence_score', 'N/A')}")
    for aid, prof in bs.get("profiles", {}).items():
        top = sorted(prof.items(), key=lambda x: x[1], reverse=True)[:3]
        top_str = ", ".join(f"{k}={v}" for k, v in top)
        print(f"    {aid}: {top_str}")
    bj = report.get("behavioral_specialization_llm_judge")
    if bj:
        print("\n  Behavioral Specialization (LLM judge):")
        if "error" in bj:
            print(f"    Error: {bj['error']}")
        else:
            print(f"    Judge model:        {bj.get('judge_model', 'N/A')}")
            print(f"    Divergence score:   {bj.get('divergence_score', 'N/A')}")
            print(f"    Classifications:    {bj.get('total_classifications', 0)} "
                  f"({bj.get('classification_failures', 0)} failed)")
            for aid, prof in bj.get("profiles", {}).items():
                top = sorted(prof.items(), key=lambda x: x[1], reverse=True)[:3]
                top_str = ", ".join(f"{k}={v}" for k, v in top)
                print(f"    {aid}: {top_str}")
        ca = report.get("classifier_agreement")
        if ca and "error" not in ca:
            print("\n  Classifier Agreement (keyword vs judge):")
            print(f"    Top-1 match rate:   {ca.get('top_1_match_rate', 'N/A')}")
            print(f"    Mean Spearman:      {ca.get('mean_spearman_rank_correlation', 'N/A')}")

    sd = report.get("semantic_divergence", {})
    if sd and "error" not in sd:
        print("\n  Semantic Divergence:")
        print(f"    Mean cosine distance: {sd.get('mean_cosine_distance', 'N/A')}")
        for pair, ps in sd.get("pairwise_summaries", {}).items():
            print(f"    {pair}: mean={ps['mean']}, trend={ps['trend']:+.6f}")
    print(f"{'=' * 60}")


def cmd_pipeline(args: argparse.Namespace) -> None:
    """Drive the full matrix: preflight → test gate → cost → run → metrics → report."""
    from emergent_divergence.pipeline import run_pipeline

    overrides: dict = {"smoke": args.smoke}
    if args.run_id:
        overrides["run_id"] = args.run_id
    if args.backends:
        overrides["backends"] = args.backends
    if args.conditions:
        overrides["conditions"] = args.conditions
    if args.seeds:
        overrides["seeds"] = args.seeds
    if args.rounds:
        overrides["rounds"] = args.rounds
    if args.cap_usd is not None:
        overrides["cap_usd"] = args.cap_usd

    code = run_pipeline(
        config_path=args.config,
        overrides=overrides,
        skip_tests=args.skip_tests,
        no_report=args.no_report,
    )
    sys.exit(code)


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

    # run (single cell; the full sweep is `pipeline`)
    p_run = subparsers.add_parser("run", help="Execute a single cell (backend×condition×seed)")
    p_run.add_argument("--backend", choices=["stub", "ollama", "claude"], default="stub",
                       help="Model backend (default: stub)")
    p_run.add_argument("--condition", choices=["A", "B", "C"], default="A",
                       help="Experimental condition (default: A)")
    p_run.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    p_run.add_argument("--rounds", type=int, help="Number of rounds (default: 50)")
    p_run.add_argument("--model", help="Override the backend model id")
    p_run.add_argument("--run-dir", dest="run_dir", help="Output directory for this cell")
    p_run.set_defaults(func=cmd_run)

    # pipeline (the one-button matrix driver — brief §5)
    p_pipe = subparsers.add_parser("pipeline", help="Run the full backend×condition×seed matrix")
    p_pipe.add_argument("--config", default="configs/pipeline.yaml",
                        help="Path to pipeline YAML (default: configs/pipeline.yaml)")
    p_pipe.add_argument("--smoke", action="store_true",
                        help="Fast offline proof: stub backend, 2 rounds, 1 seed (<1 min)")
    p_pipe.add_argument("--run-id", dest="run_id", help="Resume/label a specific run")
    p_pipe.add_argument("--backends", nargs="+", help="Override backends (e.g. ollama claude)")
    p_pipe.add_argument("--conditions", nargs="+", help="Override conditions (A B C)")
    p_pipe.add_argument("--seeds", nargs="+", type=int, help="Override seeds")
    p_pipe.add_argument("--rounds", type=int, help="Override number of rounds")
    p_pipe.add_argument("--cap-usd", dest="cap_usd", type=float, help="Override the cost cap")
    p_pipe.add_argument("--skip-tests", action="store_true", help="Skip the pytest gate")
    p_pipe.add_argument("--no-report", action="store_true", help="Skip full report rendering")
    p_pipe.set_defaults(func=cmd_pipeline)

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze a completed run")
    p_analyze.add_argument("--run-dir", required=True, help="Path to run directory")
    p_analyze.add_argument("--semantic", action="store_true",
                           help="Include embedding-based semantic divergence analysis")
    p_analyze.add_argument("--classifier", choices=["keyword", "llm_judge", "both"],
                           default="keyword",
                           help="Behavioral classifier (default: keyword). 'llm_judge' and "
                                "'both' call the Anthropic judge and incur API cost.")
    from emergent_divergence.metrics.llm_judge import DEFAULT_JUDGE_MODEL
    p_analyze.add_argument("--judge-model", dest="judge_model",
                           default=DEFAULT_JUDGE_MODEL,
                           help=f"Judge model id (default: {DEFAULT_JUDGE_MODEL})")
    p_analyze.set_defaults(func=cmd_analyze)

    # compare
    p_compare = subparsers.add_parser("compare", help="Compare two runs")
    p_compare.add_argument("--runs", nargs=2, required=True, help="Two run directories")
    p_compare.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
