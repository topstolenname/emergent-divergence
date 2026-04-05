# Emergent Behavioral Divergence in Coordinated Multi-Agent Systems

**An empirical experiment testing whether multiple instances of the same base LLM develop measurable behavioral divergence under structured coordination with persistent memory.**

## Research Question

> Do multiple instances of the same base LLM develop measurable and stable behavioral divergence when coordinating on repeated tasks under shared system constraints?

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run a pilot (30 rounds, 3 agents, memory enabled)
python -m emergent_divergence run --config configs/memory_enabled.yaml --rounds 30

# Run the no-memory control
python -m emergent_divergence run --config configs/no_memory.yaml --rounds 30

# Analyze results
python -m emergent_divergence analyze --run-dir data/raw_logs/<run_id>

# Compare conditions
python -m emergent_divergence compare --runs data/raw_logs/<run_a> data/raw_logs/<run_b>
```

## Experimental Design

- **3 agents** (same base LLM) with weak role priors: Proposer, Critic, Synthesizer
- **Condition A**: Memory-enabled coordination (agents retain context across rounds)
- **Condition B**: No-memory control (agents reset each round)
- **Task**: Multi-turn collaborative claim analysis requiring disagreement and synthesis
- **Rounds**: 30 (pilot) → 100+ (full experiment)
- **Metrics**: Linguistic divergence (JSD), behavioral specialization, memory usage patterns, coordination structure

## Project Structure

```
emergent-divergence/
├── configs/               # Experiment configurations (YAML)
├── src/
│   ├── agents/            # Agent instantiation and LLM interface
│   ├── memory/            # Lightweight persistent per-agent memory
│   ├── tasks/             # Task generation and round management
│   ├── orchestration/     # Multi-agent coordination loop
│   ├── logging_/          # Structured JSONL event logging
│   ├── metrics/           # Divergence and specialization metrics
│   ├── evaluation/        # Optional LLM-judge scoring hooks
│   └── cli/               # CLI runner
├── experiments/           # Notebooks and pilot run outputs
├── data/                  # Raw logs, processed data, reports
└── tests/                 # Unit and integration tests
```

## Pilot Results (Memory Enabled, Seed 42, 50 Rounds)

> **Status**: Pilot complete. Control condition (no-memory) pending. Full multi-seed runs not yet complete.

| Hypothesis | Finding | Status |
|------------|---------|--------|
| H1 — Linguistic divergence increases over time | Spearman ρ=0.511, p=0.0007 across 40 sliding windows | ✅ Supported |
| H2 — Behavioral role specialization emerges | Divergence score=0.154; agents differentiate along role lines | ✅ Moderate support |
| H3 — Memory amplifies divergence vs. control | No-memory control incomplete (API credits exhausted after 4 rounds) | ⏳ Pending |
| H4 — Coordination structure becomes non-uniform | Fixed turn-order design prevents testing | 🚫 Not testable (by design) |

### Key Metrics (Run `run_20260310_161255_db9f7b49`, 49 rounds)

- **Mean pairwise JSD**: 0.2935 (Agent 0 vs 1: 0.299 | Agent 0 vs 2: 0.287 | Agent 1 vs 2: 0.295)
- **JSD trajectory**: Rises ~5.5% from early windows (0.382) to peak ~rounds 20–30 (0.403), then stabilizes (~0.392)
- **Behavioral divergence score**: 0.154 (mean pairwise L2 distance between role profiles)
- **Lexical uniqueness**: Agent 0: 20.2% | Agent 1: 22.0% | Agent 2: 19.6%

See [`data/reports/pilot_analysis_report.md`](data/reports/pilot_analysis_report.md) for full analysis.

### Next Steps

1. Top up API credits and run no-memory control (Condition B, ~$3, ~1 hour)
2. Run seeds 43–45 for both conditions
3. Generate visualizations: `python scripts/generate_figures.py --run-dir data/raw_logs/<run_id>`

## Non-Goals

This experiment does **not** test consciousness, selfhood, AGI, or validate the full AGI-SAC architecture. It tests one narrow empirical claim about behavioral divergence.

## Success Criteria

Evidence that at least one of:
- Agents become measurably more linguistically distinct over time
- Agents stabilize into differentiated behavioral roles
- Persistent memory increases divergence relative to controls
- Coordination structure becomes non-uniform and repeatable

## Lineage

Extracted from the [AGI-SAC](https://github.com/topstolenname/agisa_sac) research framework as a minimal empirical bridge experiment.

## License

MIT
