---
title: "Research Question & Hypothesis"
created: 2026-03-10
tags: [research-question, hypothesis, experiment-design]
---

# Research Question & Hypothesis

## Primary Research Question

> Do multiple instances of the same base LLM develop measurable and stable behavioral divergence when coordinating on repeated tasks under shared system constraints?

## Hypotheses

### H1 — Linguistic Divergence Increases Over Time
Agents become measurably more linguistically distinct over rounds, as measured by Jensen-Shannon Divergence (JSD) of word frequency distributions computed in sliding windows.

### H2 — Behavioral Role Specialization Emerges
Agents stabilize into differentiated behavioral roles beyond their initial weak bias, measured by keyword-based behavioral profiling.

### H3 — Memory Amplifies Divergence
Persistent memory (Condition A) increases divergence relative to the no-memory control (Condition B). This requires comparing the current run against a future [[Config — no_memory.yaml|no-memory control run]].

### H4 — Coordination Structure Becomes Non-Uniform
The interaction patterns between agents develop structure (e.g., certain agents tend to respond to certain others, first-mover effects stabilize).

## Success Criteria

Evidence that **at least one** of the following holds:

1. Agents become measurably more linguistically distinct over time
2. Agents stabilize into differentiated behavioral roles
3. Persistent memory increases divergence relative to controls
4. Coordination structure becomes non-uniform and repeatable

## Non-Goals

This experiment does **not** test:

- Consciousness or selfhood
- AGI capabilities
- Full AGI-SAC architecture validation
- Emergent reasoning or tool use

It tests **one narrow empirical claim** about behavioral divergence under structured coordination with persistent memory.

## Related

- [[02 — Experimental Design]] — How these hypotheses are operationalized
- [[Metrics Summary & Interpretation]] — Results against these hypotheses
- [[Risks & Confounds]] — What could invalidate findings
