---
title: "Emergent Behavioral Divergence — Experiment Documentation"
created: 2026-03-10
project: emergent-divergence
run_id: run_20260310_161255_db9f7b49
tags: [index, experiment, multi-agent, divergence]
---

# Emergent Behavioral Divergence in Coordinated Multi-Agent Systems

> Do multiple instances of the same base LLM develop measurable and stable behavioral divergence when coordinating on repeated tasks under shared system constraints?

This vault rigorously documents a completed experimental run: **3 agents, 50 rounds, 300 messages, ~57 minutes of wall-clock time**, using `claude-sonnet-4-20250514` with persistent memory enabled.

---

## Vault Navigation

### Core Documentation

- [[01 — Research Question & Hypothesis]] — The empirical claim being tested
- [[02 — Experimental Design]] — Conditions, controls, parameters
- [[03 — Architecture Overview]] — System architecture and module map
- [[04 — Lineage & Provenance]] — Relationship to AGI-SAC parent project

### Agents

- [[Agent 0 — Proposer]] — Role bias, behavioral profile, memory trajectory
- [[Agent 1 — Critic]] — Role bias, behavioral profile, memory trajectory
- [[Agent 2 — Synthesizer]] — Role bias, behavioral profile, memory trajectory

### Run Data

- [[Run Summary — run_20260310_161255_db9f7b49]] — Complete run overview with all 50 rounds
- [[Round Timeline]] — Chronological index of all 50 rounds with claims and domains
- [[Round Transcripts/]] — Full conversation transcripts per round (Rounds 00–49)

### Metrics & Analysis

- [[Metric A — Linguistic Divergence (JSD)]] — Pairwise JSD, sliding windows, lexical uniqueness
- [[Metric B — Behavioral Specialization]] — Keyword-based behavioral profiles and divergence score
- [[Metric C — Memory Usage Patterns]] — Read/write stats across agents
- [[Metric D — Coordination Structure]] — Turn order, first-speaker rotation, message distribution
- [[Metrics Summary & Interpretation]] — Synthesis of all metrics with key findings

### Configuration & Source

- [[Config — memory_enabled.yaml]] — The config used for this run
- [[Config — no_memory.yaml]] — The control condition config (not yet run)
- [[Source Code Index]] — Annotated index of all source modules

### Meta

- [[Risks & Confounds]] — Known limitations and confounding variables
- [[Experiment Roadmap]] — Concrete phased plan: 10 runs, stopping criteria, 2×2 factorial design
- [[Future Work]] — Broader aspirations beyond the immediate roadmap
- [[Glossary]] — Key terms used throughout this vault

---

## Quick Stats

| Parameter | Value |
|---|---|
| Run ID | `run_20260310_161255_db9f7b49` |
| Date | 2026-03-10 |
| Duration | ~56.7 minutes |
| Condition | `memory_enabled` (Condition A) |
| Model | `claude-sonnet-4-20250514` |
| Temperature | 1.0 |
| Agents | 3 |
| Rounds | 50 |
| Turns/Round | 2 |
| Total Messages | 300 (100 per agent) |
| Total Memory Writes | 300 |
| Seed | 42 |
| Mean JSD (overall) | 0.2935 |
| Behavioral Divergence Score | 0.1544 |

---

## Lineage

Extracted from [[04 — Lineage & Provenance|AGI-SAC]] (`topstolenname/agisa_sac`) as a minimal empirical bridge experiment. See the [[03 — Architecture Overview|Architecture Overview]] for what was ported vs. newly built.
