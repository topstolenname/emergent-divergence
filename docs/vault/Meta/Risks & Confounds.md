---
title: "Risks & Confounds"
created: 2026-03-10
tags: [risks, confounds, limitations, methodology]
---

# Risks & Confounds

## Implementation Risks

### 1. API Cost
100 rounds x 3 agents x 2 turns = 600 LLM calls per condition. At ~$0.003/1K tokens output, a full run costs ~$5-15. The 50-round run used 300 API calls.

### 2. Prompt Overdetermination
The role bias text in system prompts could dominate behavior. **Mitigation**: Biases are intentionally weak ("You *tend* to...") and the prompt explicitly says "respond naturally." However, the behavioral profiles in [[Metric B — Behavioral Specialization]] show clear alignment with biases, raising the question of whether divergence is "emergent" or "prompted."

### 3. Conversation Context Growth
By late turns, the context window fills with prior messages. **Mitigation**: 2 turns per round keeps context manageable; memory provides selective recall vs. full context.

### 4. Model Randomness vs. Divergence
Temperature=1.0 introduces stochastic variation. Need multiple seeds and repeated runs to distinguish noise from stable divergence. The current run uses only seed=42.

### 5. Keyword-Based Behavioral Classification
The current classifier uses keyword density, which is crude. Many behavioral acts use language that doesn't match the keyword lists. Synthesis behavior is particularly undercounted. Future versions should use embedding-based classification or LLM-judge scoring.

## Confounds

### Fixed Turn Order
Agents always speak in a deterministic rotation within each round. While the starting agent rotates, the *relative* order is fixed (0→1→2). This could create:
- **Positional bias**: First speakers set the frame; last speakers have more context but less opportunity
- **Response patterns**: Agent 1 may always respond to Agent 0's most recent point, creating dyadic patterns

**Mitigation**: Consider shuffling order per round in a future condition.

### Memory Asymmetry
Agents only store their own output summaries. They don't store:
- Others' contributions
- Task content
- Group conclusions

This means memory creates self-reinforcing behavioral patterns rather than shared context evolution.

### Task Difficulty Variance
Different claims elicit different amounts of disagreement. The seed ensures reproducibility, but analysis should control for task difficulty. Claims cycle after round 20, meaning agents encounter the same claims with different memory contexts.

### Single Model
All agents use `claude-sonnet-4-20250514`. Divergence is measured within a single model's output distribution. Different base models might show different divergence characteristics.

### Single Seed
Only seed=42 was used. The task ordering, RNG state, and all downstream effects depend on this single seed. Multiple seeds are needed to assess result stability.

### No Baseline Condition
The no-memory control (Condition B) has not been run. Without it, we cannot determine whether the observed divergence is attributable to memory, role biases, stochastic variation, or some combination.

## What Would Invalidate Results

- If the no-memory control shows identical divergence patterns, memory has no effect
- If different seeds produce wildly different JSD trajectories, the signal is noise
- If removing role biases eliminates all divergence, the biases are doing all the work
- If the keyword classifier produces the same profiles for random text, it's not measuring real behavioral differences

## Related

- [[Metrics Summary & Interpretation]] — How these risks affect interpretation
- [[Future Work]] — How to address these limitations
- [[02 — Experimental Design]] — Design choices that created these risks
