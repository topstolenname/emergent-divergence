---
title: "Config — no_memory.yaml"
created: 2026-03-10
condition: no_memory
tags: [config, condition-b, no-memory, control]
---

# Config — no_memory.yaml

**Condition B**: No-memory control. This config has **not yet been run**.

## Parameters

```yaml
# Condition B: No-memory control
# Agents do not accumulate persistent memory between rounds
num_agents: 3
role_biases:
  - proposer
  - critic
  - synthesizer
memory_enabled: false
memory_max_entries: 0
model: "claude-sonnet-4-20250514"
max_tokens: 1024
temperature: 1.0
num_rounds: 100
turns_per_round: 2
condition: "no_memory"
seed: 42
output_dir: "data/raw_logs"
```

## Differences from Condition A

| Parameter | Condition A | Condition B |
|---|---|---|
| `memory_enabled` | `true` | **`false`** |
| `memory_max_entries` | 200 | **0** |
| All other params | identical | identical |

## Purpose

This is the **control condition** for testing [[01 — Research Question & Hypothesis#H3 — Memory Amplifies Divergence|Hypothesis H3]]. By comparing JSD trajectories and behavioral profiles between the memory-enabled and no-memory conditions, we can isolate memory's contribution to behavioral divergence.

## Usage

```bash
python -m emergent_divergence run --config configs/no_memory.yaml --rounds 50
```

## Related

- [[Config — memory_enabled.yaml]] — The experimental condition (completed)
- [[Future Work]] — Running this control is the highest-priority next step
