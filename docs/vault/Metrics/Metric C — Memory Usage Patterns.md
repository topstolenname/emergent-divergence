---
title: "Metric C — Memory Usage Patterns"
created: 2026-03-10
tags: [metrics, memory, read-write-patterns]
---

# Metric C — Memory Usage Patterns

## Method

Memory events are tracked via two mechanisms:
1. **Writes**: Logged as `memory_write` events in the JSONL log
2. **Reads**: Recorded as `memory_reads` field in each `agent_message` event (count of memory entries retrieved)

## Results

| Agent | Total Writes | Total Reads | Mean Reads/Msg | Max Reads |
|---|---|---|---|---|
| [[Agent 0 — Proposer\|Agent 0]] | 100 | 945 | 9.45 | 10 |
| [[Agent 1 — Critic\|Agent 1]] | 100 | 945 | 9.45 | 10 |
| [[Agent 2 — Synthesizer\|Agent 2]] | 100 | 945 | 9.45 | 10 |

## Interpretation

### Symmetric Memory Usage

All three agents show **identical memory statistics**. This is expected because:

1. **Writes are deterministic**: Every agent writes 1 memory entry per turn, 2 turns per round, 50 rounds = 100 writes.
2. **Reads are capped**: The system retrieves the 10 most recent entries per message. Since all agents accumulate memories at the same rate, they all hit the 10-entry read cap at roughly the same time (after round 5).
3. **No asymmetry mechanism**: The current design doesn't allow agents to read others' memories or selectively recall based on content.

### Memory Growth Trajectory

- **Rounds 0–4**: Memory grows from 0 to ~10 entries. Mean reads increase from 0 to 10.
- **Rounds 5–49**: Memory saturates at 10 reads per message (the retrieval cap). Total entries grow from 10 to 100, but only the most recent 10 are recalled.

### Key Observation

The memory system as designed provides **recency-weighted context** but not **differential usage patterns**. All agents receive the same amount of contextual history. The behavioral differences documented in [[Metric B — Behavioral Specialization]] arise from how agents *use* their memories in generating responses, not from differences in memory access patterns.

## Implications for Future Work

- **Selective recall**: Implementing keyword-based or embedding-based memory retrieval could create asymmetric memory usage patterns
- **Cross-agent memory**: Allowing agents to read each others' memories could create network-like memory structures
- **Memory importance weighting**: Prioritizing "important" memories over merely recent ones could differentiate memory strategies

## Related

- [[02 — Experimental Design]] — Memory mechanics specification
- [[Metric D — Coordination Structure]] — Another structural metric
- [[Future Work]] — Memory improvements
