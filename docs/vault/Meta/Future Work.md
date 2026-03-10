---
title: "Future Work"
created: 2026-03-10
tags: [future-work, next-steps, roadmap]
---

# Future Work

## Priority 1 — Complete the Experiment

### Run the No-Memory Control (Condition B)
```bash
python -m emergent_divergence run --config configs/no_memory.yaml --rounds 50
```
This is the **single most important next step**. Without the control condition, we cannot isolate memory's contribution to divergence. Use the same seed (42) for direct comparison.

### Compare Conditions
```bash
python -m emergent_divergence compare --runs data/raw_logs/<memory_run> data/raw_logs/<no_memory_run>
```

## Priority 2 — Strengthen the Evidence

### Multiple Seeds
Run both conditions with seeds 43, 44, 45 to assess stability. If JSD trajectories are consistent across seeds, the signal is robust; if they vary wildly, it's noise.

### Extended Runs
Run 100+ rounds (as originally planned in the config) to see if divergence continues to increase, plateaus, or reverses.

## Priority 3 — Improve Metrics

### Embedding-Based Behavioral Classification
Replace the crude keyword classifier with sentence embeddings (e.g., using `sentence-transformers`) to better capture behavioral categories. This would address the systematic undercounting of synthesis behavior noted in [[Metric B — Behavioral Specialization]].

### LLM-Judge Evaluation
Implement the [[Source Code Index|judge.py]] placeholder. Use a separate LLM to score agent messages on:
- Role consistency
- Distinctiveness
- Contribution quality
- Coherence
- Engagement

### Temporal Behavioral Analysis
Track behavioral profiles over time (not just averaged). Do agents become more or less specialized as rounds progress?

## Priority 4 — Expand the Design

### Shuffled Turn Order
Remove fixed rotation and randomize speaking order per round to test whether positional effects drive divergence.

### Shared Memory Condition
Use the `SharedMemory` class (already implemented but unused) to create a condition where agents share a common memory pool.

### More Agents
Scale from 3 to 5–7 agents to test whether divergence scales with group size.

### Different Base Models
Test with `claude-haiku-4-5` or other models to see if divergence patterns are model-specific.

### Variable Participation
Allow agents to "pass" on turns, enabling emergent coordination structure (testing [[01 — Research Question & Hypothesis#H4|H4]]).

## What NOT to Do (Per Original Guidance)

From the [[04 — Lineage & Provenance|TRIAGE_AND_ARCHITECTURE.md]]:

- Do not add more agents until pilot results are in
- Do not add TDA, embedding-based metrics, or LLM-judge until v1 analysis is complete
- Do not add shared memory conditions until per-agent memory effects are established
- Do not refactor the architecture until you have usable experimental data

## Concrete Next Steps

See [[Experiment Roadmap]] for the phased execution plan with exact run specs, cost estimates, stopping criteria, and a decision tree. The roadmap covers:

- Phase 1: No-memory control + second seed
- Phase 2: Full seed panel (42–45)
- Phase 3: 2×2 role-bias ablation
- Phase 4: LLM-judge classifier upgrade
- Phase 5: Temporal behavioral analysis

Total cost for all 10 runs: ~$27. Total wall-clock time: ~9.5 hours sequential.

## Related

- [[Experiment Roadmap]] — The concrete execution plan
- [[Risks & Confounds]] — Limitations driving these priorities
- [[Metrics Summary & Interpretation]] — Current state of evidence
- [[Config — no_memory.yaml]] — The control condition config
