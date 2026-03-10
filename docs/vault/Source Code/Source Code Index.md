---
title: "Source Code Index"
created: 2026-03-10
tags: [source-code, architecture, modules]
---

# Source Code Index

Annotated index of all source modules in the `emergent-divergence` project. See [[03 — Architecture Overview]] for the system diagram and design rationale.

## Core Modules

### `src/emergent_divergence/agents/agent.py`
**Purpose**: Agent instances wrapping shared LLM backend with per-agent role bias and memory.

Key components:
- `LLMBackend` (Protocol) — Swappable async LLM interface
- `AnthropicBackend` — Claude API wrapper using `anthropic.AsyncAnthropic()`
- `MockLLMBackend` — Deterministic testing backend (hash-based template selection)
- `Agent` — Core agent class: builds system prompts, calls LLM, manages memory
- `ROLE_BIASES` — Dict of weak role bias texts
- `AgentConfig` — Dataclass for agent initialization

Design principles: No cognitive engine, no personality vectors, LLM is sole behavior driver.

### `src/emergent_divergence/memory/store.py`
**Purpose**: Lightweight per-agent persistent memory with JSONL backing.

Key components:
- `MemoryStore` — Ordered list with add, get_recent, search, clear, JSONL persistence
- `SharedMemory` — Optional shared context (not used in this run)

Max capacity: 200 entries with oldest-first eviction. Retrieval: most recent N entries.

### `src/emergent_divergence/tasks/generator.py`
**Purpose**: Deterministic task generation from a bank of debatable claims.

Key components:
- `CLAIM_BANK` — 20 claims across 9 domains (technology, science, organizational, education, economics, engineering, governance, health, environment)
- `TaskGenerator` — Seeded RNG, shuffled cycling through claim bank
- `Task` — Dataclass with claim, domain, difficulty, instructions template

### `src/emergent_divergence/orchestration/runner.py`
**Purpose**: Multi-agent coordination loop.

Key components:
- `ExperimentConfig` — All experiment parameters as a dataclass
- `ExperimentRunner` — Initializes agents, runs rounds with turn rotation, logs events, handles memory writes
- Turn rotation: `offset = round_id % num_agents`

### `src/emergent_divergence/logging_/events.py`
**Purpose**: Structured JSONL event logging.

Key components:
- `ExperimentEvent` — Dataclass for all event types (strips None values for clean logs)
- `ExperimentLogger` — Append-only JSONL writer with run manifest
- `generate_run_id()` — Timestamp + UUID fragment
- `load_events()` — Parse JSONL file back to dicts

### `src/emergent_divergence/metrics/divergence.py`
**Purpose**: All analysis metrics.

Key components:
- `compute_pairwise_jsd()` — JSD between agent word frequency distributions
- `compute_jsd_over_time()` — Sliding window JSD trajectories
- `compute_lexical_uniqueness()` — Per-agent unique vocabulary ratio
- `classify_message_behavior()` — Keyword-density behavioral classification
- `compute_behavioral_profiles()` — Per-agent averaged behavioral scores
- `compute_behavioral_divergence()` — Mean pairwise L2 distance between profiles
- `compute_memory_stats()` — Read/write counts per agent
- `compute_turn_order_stats()` — First-mover frequency and message distribution
- `generate_analysis_report()` — Full report generation combining all metrics

### `src/emergent_divergence/evaluation/judge.py`
**Purpose**: Placeholder for LLM-as-judge evaluation.

Key components:
- `JudgeRubric` — 5 scoring dimensions (role_consistency, distinctiveness, contribution_quality, coherence, engagement)
- `build_judge_prompt()` — Prompt template for judge LLM
- `evaluate_agent()` — Placeholder (returns "not_implemented")

### `src/emergent_divergence/cli/runner.py`
**Purpose**: CLI entry points.

Commands:
- `run` — Execute experiment from YAML config (with optional overrides)
- `analyze` — Generate analysis report from a completed run
- `compare` — Compare two runs (e.g., memory vs. no-memory)

## Test Suite

| File | Tests | Coverage |
|---|---|---|
| `tests/test_memory.py` | 5 | MemoryStore CRUD and persistence |
| `tests/test_logging.py` | 3 | Event logging and JSONL format |
| `tests/test_metrics.py` | 6 | JSD, behavioral classification, memory stats |
| `tests/test_tasks.py` | 3 | Task generation and cycling |
| `tests/test_integration.py` | Integration | Full experiment run with mock backend |
| `tests/conftest.py` | - | Shared fixtures |

## Configuration Files

| File | Purpose |
|---|---|
| `configs/baseline.yaml` | Shared defaults |
| `configs/memory_enabled.yaml` | [[Config — memory_enabled.yaml|Condition A]] |
| `configs/no_memory.yaml` | [[Config — no_memory.yaml|Condition B]] |

## Related

- [[03 — Architecture Overview]] — System diagram
- [[04 — Lineage & Provenance]] — What was ported vs. newly built
