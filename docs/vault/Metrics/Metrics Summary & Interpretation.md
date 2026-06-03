---
title: "Metrics Summary & Interpretation"
created: 2026-03-10
tags: [metrics, summary, interpretation, findings]
---

# Metrics Summary & Interpretation

## Headline Findings

### 1. Behavioral specialization aligns with role biases (H2: Supported)

Each agent's dominant behavioral category matches their assigned role bias. [[Agent 0 — Proposer|Agent 0]] leads in proposal (0.302), [[Agent 1 — Critic|Agent 1]] leads in critique (0.273) and verification (0.217), and [[Agent 2 — Synthesizer|Agent 2]] leads in synthesis (0.055). The behavioral divergence score of **0.1544** confirms measurable differentiation.

However, agents are not locked into their roles — they all exhibit behaviors outside their bias. The biases shape tendencies, not deterministic scripts.

### 2. Linguistic divergence shows modest temporal evolution (H1: Weak Signal)

JSD computed in sliding windows shows a ~5% increase from early rounds (0.382) to mid-run peak (0.403), followed by stabilization around 0.39. This is a modest signal that may partly reflect stochastic variation at temperature=1.0. The overall mean JSD of **0.2935** indicates moderate (not extreme) linguistic divergence.

The proposer-critic pair shows the strongest divergence trajectory, reaching JSD of 0.412 in peak windows.

### 3. Memory usage is structurally symmetric (H3: Cannot assess without control)

All three agents show identical memory read/write patterns (100 writes, 945 reads, 9.45 mean reads/msg). The current memory design doesn't create differential usage patterns. Testing H3 (memory amplifies divergence) requires running the [[Config — no_memory.yaml|no-memory control condition]].

### 4. Coordination structure is uniform by design (H4: Not applicable in current design)

Equal message counts and rotating turn order prevent emergent coordination asymmetry. Testing H4 would require optional turn-taking or variable participation.

## Cross-Metric Synthesis

| Metric | Finding | Strength |
|---|---|---|
| JSD over time | Modest upward trend, mid-run peak, stabilization | Weak-to-moderate |
| Behavioral profiles | Clear role alignment, non-trivial divergence score | Moderate |
| Lexical uniqueness | Agent 1 most unique (22%), Agent 2 least (19.6%) | Moderate |
| Memory patterns | Symmetric — no differential usage | Null (by design) |
| Coordination | Uniform — no emergent structure | Null (by design) |

## Assessment Against Success Criteria

From [[01 — Research Question & Hypothesis|the original success criteria]]:

> Evidence that **at least one** of the following holds...

1. **Agents become measurably more linguistically distinct over time** — *Weak support*. JSD rises modestly but the signal is small relative to stochastic noise.

2. **Agents stabilize into differentiated behavioral roles** — *Moderate support*. Behavioral profiles clearly differentiate, aligning with role biases. Whether this constitutes "emergent" divergence vs. "prompt-driven" differentiation is debatable.

3. **Persistent memory increases divergence relative to controls** — *Cannot assess*. No control condition data yet.

4. **Coordination structure becomes non-uniform and repeatable** — *Not testable* with the current forced-rotation design.

## Confidence Level

**Low-to-moderate confidence** that behavioral divergence exceeds what would be expected from role bias text alone. The key limitation is the absence of the no-memory control condition, which would isolate memory's contribution. The behavioral profiles could be entirely explained by the system prompt role biases, with memory having no incremental effect.

## Recommended Next Steps

1. **Run the no-memory control** with identical parameters and seed
2. **Compare JSD trajectories** between conditions
3. **Implement embedding-based behavioral classification** to replace crude keyword approach
4. **Add multiple seeds** (43, 44, 45) to assess stability across task orderings
5. **Consider shuffled turn order** condition to test positional effects

## Related

- [[Metric A — Linguistic Divergence (JSD)]]
- [[Metric B — Behavioral Specialization]]
- [[Metric C — Memory Usage Patterns]]
- [[Metric D — Coordination Structure]]
- [[Future Work]]
