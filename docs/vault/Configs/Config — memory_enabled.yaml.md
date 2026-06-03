---
title: "Config — memory_enabled.yaml"
created: 2026-03-10
condition: memory_enabled
tags: [config, condition-a, memory-enabled]
---

# Config — memory_enabled.yaml

**Condition A**: Memory-enabled coordination. This is the config used for the completed run `run_20260310_161255_db9f7b49`.

## Parameters

```yaml
# Condition A: Memory-enabled coordination
# Agents retain and use memory across rounds
num_agents: 3
role_biases:
  - proposer
  - critic
  - synthesizer
memory_enabled: true
memory_max_entries: 200
model: "claude-sonnet-4-20250514"
max_tokens: 1024
temperature: 1.0
num_rounds: 100        # Config says 100, run was executed with 50
turns_per_round: 2
condition: "memory_enabled"
seed: 42
output_dir: "data/raw_logs"
```

## Notes

- The config specifies `num_rounds: 100` but the actual run was executed with **50 rounds** (likely via CLI override `--rounds 50`)
- `memory_max_entries: 200` was not reached during the 50-round run (max accumulated was 100 entries per agent)
- `temperature: 1.0` is the maximum standard temperature, introducing maximal stochastic variation

## Usage

```bash
python -m emergent_divergence run --config configs/memory_enabled.yaml --rounds 50
```

## Related

- [[Config — no_memory.yaml]] — The control condition
- [[02 — Experimental Design]] — How this config maps to experimental design
- [[Run Summary — run_20260310_161255_db9f7b49]] — Results from this config
