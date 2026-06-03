---
title: "Experimental Design"
created: 2026-03-10
tags: [experiment-design, methodology, conditions]
---

# Experimental Design

## Overview

A repeated-measures multi-agent coordination experiment where 3 instances of the same base LLM (with weak role biases and persistent memory) collaborate on debatable claim analysis tasks across 50 rounds.

## Conditions

### Condition A — Memory Enabled (THIS RUN)

- Agents retain persistent per-agent memory across rounds
- Each agent stores a 300-character summary of their own output after each turn
- Memory is recalled (most recent 10 entries) and injected into the system prompt
- Config: [[Config — memory_enabled.yaml]]

### Condition B — No Memory (CONTROL, NOT YET RUN)

- Agents have no persistent memory between rounds
- Each round starts fresh with no prior context
- Config: [[Config — no_memory.yaml]]

## Agent Configuration

| Agent | ID | Role Bias | Bias Strength |
|---|---|---|---|
| [[Agent 0 — Proposer]] | `agent_0` | Proposer | Weak ("You *tend* to...") |
| [[Agent 1 — Critic]] | `agent_1` | Critic | Weak |
| [[Agent 2 — Synthesizer]] | `agent_2` | Synthesizer | Weak |

All agents use the **same model** (`claude-sonnet-4-20250514`) with **identical parameters** (temperature=1.0, max_tokens=1024). The only difference is the role bias text in their system prompts.

### Role Bias Texts

- **Proposer**: "You tend to generate initial ideas, propose solutions, and introduce new framings. You enjoy opening up the solution space."
- **Critic**: "You tend to evaluate proposals critically, identify weaknesses, and push for rigor. You value precision and skepticism."
- **Synthesizer**: "You tend to integrate perspectives, find common ground, and build composite solutions. You value coherence and completeness."

These are described as "slight inclinations, not rigid rules" in the system prompt.

## Task Design

### Task Family: Collaborative Claim Analysis

Each round presents a debatable claim from a bank of 20 claims spanning 9 domains. Agents must:

1. Evaluate the claim's validity with evidence and reasoning
2. Identify strongest arguments for and against
3. Note key uncertainties or missing information
4. Arrive at a nuanced group assessment

### Claim Bank

See [[Round Timeline]] for the full mapping of claims to rounds. The claim bank contains 20 claims across domains: technology (7), science (4), organizational (4), education (3), economics (3), engineering (1), governance (1), health (1), environment (1).

Claims cycle through the bank with seeded shuffling (seed=42), so claims repeat after the bank is exhausted at round 20.

## Turn Structure

Each round consists of **2 turns**, where each agent speaks once per turn, for a total of **6 messages per round**.

### Turn Order Rotation

The starting agent rotates every round: `offset = round_id % num_agents`. This ensures every agent gets equal time as first speaker.

| Round | First Speaker | Order |
|---|---|---|
| 0, 3, 6, ... | agent_0 | 0 → 1 → 2 |
| 1, 4, 7, ... | agent_1 | 1 → 2 → 0 |
| 2, 5, 8, ... | agent_2 | 2 → 0 → 1 |

## Memory Mechanics

### Write

After each agent response, the first 300 characters of their output are stored as a memory entry with metadata (round_id, agent_id, timestamp, source="self").

### Read

Before each response, the agent's system prompt includes their 10 most recent memory entries, formatted as: `[Round N] <content>`.

### Persistence

Memory is stored as JSONL files at `data/raw_logs/<run_id>/memory/<agent_id>.jsonl`. Each agent accumulated **100 memory entries** over the 50-round run (2 writes per round).

### Eviction

Max capacity is 200 entries. At 100 entries over 50 rounds, eviction was not triggered in this run.

## Reproducibility

- **Seed**: 42 (controls task generation order)
- **Deterministic task cycling**: Same seed produces same claim sequence
- **JSONL logging**: Every interaction, memory event, and round boundary is logged
- **Run ID**: `run_20260310_161255_db9f7b49` (timestamp + UUID fragment)

## Related

- [[03 — Architecture Overview]] — How this design is implemented
- [[Run Summary — run_20260310_161255_db9f7b49]] — Results from this run
- [[Risks & Confounds]] — Known limitations of this design
