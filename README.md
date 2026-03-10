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
