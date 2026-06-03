---
title: "Architecture Overview"
created: 2026-03-10
tags: [architecture, system-design, modules]
---

# Architecture Overview

## System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    CLI (runner.py)                        │
│              run | analyze | compare                     │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │   ExperimentRunner      │
        │   (orchestration/)      │
        │                         │
        │  ┌───────────────────┐  │
        │  │  TaskGenerator    │  │
        │  │  (tasks/)         │  │
        │  └───────────────────┘  │
        │                         │
        │  For each round:        │
        │  ┌─────┐ ┌─────┐ ┌─────┐
        │  │ A0  │ │ A1  │ │ A2  │  ← Agent instances
        │  │prop │ │crit │ │synth│     (agents/)
        │  └──┬──┘ └──┬──┘ └──┬──┘
        │     │        │       │   │
        │  ┌──▼──┐ ┌──▼──┐ ┌──▼──┐
        │  │Mem0 │ │Mem1 │ │Mem2 │  ← MemoryStore
        │  └─────┘ └─────┘ └─────┘     (memory/)
        │                         │
        │  ┌───────────────────┐  │
        │  │ ExperimentLogger  │  │
        │  │ (logging_/)       │  │
        │  └───────────────────┘  │
        └────────────────────┬────┘
                             │
              ┌──────────────▼──────────────┐
              │   AnthropicBackend          │
              │   claude-sonnet-4-20250514  │
              │   (shared across agents)    │
              └─────────────────────────────┘
```

## Module Map

### `agents/agent.py`

Core agent implementation. Key design principles:

- **No cognitive engine** — the LLM is the sole driver of behavior
- **No personality vectors** — role bias is text in the system prompt
- **Protocol-based backend** — `LLMBackend` protocol enables swapping Anthropic/Mock

Key classes:
- `LLMBackend` — Protocol for async LLM backends
- `AnthropicBackend` — Claude API wrapper (async client)
- `MockLLMBackend` — Deterministic mock for testing (hash-based template selection)
- `Agent` — Wraps backend + memory + role bias, builds system prompts, generates responses
- `ROLE_BIASES` — Dict mapping role names to bias text strings

### `memory/store.py`

Lightweight per-agent persistent memory:

- `MemoryStore` — Ordered list with JSONL persistence, recency-based retrieval, keyword search, max capacity eviction
- `SharedMemory` — Optional shared context (not used in this run)

### `tasks/generator.py`

Deterministic task generation:

- `CLAIM_BANK` — 20 debatable claims across 9 domains
- `TaskGenerator` — Seeded RNG, shuffled cycling through claim bank
- `Task` — Dataclass with claim, domain, difficulty, instructions template

### `orchestration/runner.py`

Multi-agent coordination loop:

- `ExperimentConfig` — Dataclass with all experiment parameters
- `ExperimentRunner` — Initializes agents, runs rounds, manages logging
- Turn order rotation: `offset = round_id % num_agents`
- Memory write after each agent response (first 300 chars)

### `logging_/events.py`

Structured JSONL event logging:

- `ExperimentEvent` — Dataclass for all event types
- `ExperimentLogger` — Appends events to JSONL file
- Event types: `run_start`, `experiment_config`, `round_start`, `agent_message`, `memory_write`, `round_end`, `run_end`

### `metrics/divergence.py`

All analysis metrics:

- **Linguistic**: Pairwise JSD, sliding window JSD, lexical uniqueness
- **Behavioral**: Keyword classification, behavioral profiles, L2 divergence
- **Memory**: Read/write stats per agent
- **Coordination**: Turn order, first-speaker counts

### `evaluation/judge.py`

Placeholder for LLM-as-judge scoring (not implemented in v1):

- `JudgeRubric` — Scoring dimensions and scale
- `DEFAULT_RUBRIC` — 5 dimensions (role_consistency, distinctiveness, contribution_quality, coherence, engagement)

### `cli/runner.py`

CLI entry points: `run`, `analyze`, `compare`

## What Was Ported vs. Newly Built

See [[04 — Lineage & Provenance]] for the full triage of what came from AGI-SAC vs. what was written fresh.

| Component | Origin |
|---|---|
| Config-driven execution pattern | Ported concept from AGI-SAC |
| Per-agent memory with persistence | Ported concept, rewritten implementation |
| LLM backend + Agent | **Newly built** (old repo used numeric engines) |
| Task bank + generator | **Newly built** |
| JSONL structured logger | **Newly built** |
| Divergence metrics (JSD, behavioral) | **Newly built** |
| CLI | **Newly built** |

## Dependencies

```
pyyaml >= 6.0
numpy >= 1.24.0
scipy >= 1.10.0
scikit-learn >= 1.2.0
anthropic >= 0.39.0
tiktoken >= 0.5.0
```

## Related

- [[Source Code Index]] — Annotated file listing
- [[02 — Experimental Design]] — How architecture serves the experimental design
- [[04 — Lineage & Provenance]] — Origin story
