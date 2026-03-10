---
title: "Metric A — Linguistic Divergence (JSD)"
created: 2026-03-10
tags: [metrics, jsd, linguistic-divergence, lexical-uniqueness]
---

# Metric A — Linguistic Divergence (JSD)

## Method

Jensen-Shannon Divergence (JSD) is computed over word frequency distributions between agent pairs. Words are tokenized via simple whitespace + punctuation splitting, counts are smoothed (1e-10) and normalized. JSD ranges from 0 (identical distributions) to ~0.83 (maximally different for base-2 log).

### Sliding Window

JSD is computed in sliding windows of size 10 rounds to track how divergence evolves over time. Each window contains messages from a contiguous block of 10 rounds.

## Overall Results

### Pairwise JSD (All 50 Rounds)

| Pair | JSD |
|---|---|
| [[Agent 0 — Proposer\|Agent 0]] vs. [[Agent 1 — Critic\|Agent 1]] | **0.2986** (highest) |
| [[Agent 1 — Critic\|Agent 1]] vs. [[Agent 2 — Synthesizer\|Agent 2]] | 0.2947 |
| [[Agent 0 — Proposer\|Agent 0]] vs. [[Agent 2 — Synthesizer\|Agent 2]] | 0.2870 (lowest) |

**Mean JSD: 0.2935**

### Interpretation

All three pairs show moderate divergence (~0.29). The proposer-critic pair is most divergent, while proposer-synthesizer is least divergent. This makes intuitive sense: proposers and critics use different communicative registers, while synthesizers bridge between them.

## JSD Over Time (Sliding Windows)

### Trajectory Summary

| Window | Mean JSD | Trend |
|---|---|---|
| Rounds 1–10 | 0.382 | Starting point |
| Rounds 5–14 | 0.381 | Stable |
| Rounds 10–19 | 0.383 | Stable |
| Rounds 16–25 | 0.392 | Rising |
| Rounds 19–28 | 0.399 | Rising |
| Rounds 22–31 | 0.403 | **Peak region** |
| Rounds 25–34 | 0.395 | Declining |
| Rounds 30–39 | 0.391 | Stable |
| Rounds 35–44 | 0.391 | Stable |
| Rounds 40–49 | 0.392 | Stable |

### Key Observations

1. **Initial high JSD (0.382)**: Divergence starts moderate, not zero. Even in early rounds, agents use somewhat different vocabulary due to role biases and stochastic sampling.

2. **Mid-run peak (windows 20–24, mean ~0.40)**: JSD rises ~5% above baseline in the middle of the run. This is the period where the claim bank has cycled once and agents are re-encountering claims with accumulated memory.

3. **Late stabilization (~0.39)**: JSD settles to a slightly elevated plateau above the starting level. The ~2.5% increase from start to finish is modest but consistent.

4. **Agent 0 vs. Agent 1 divergence driver**: This pair shows the largest JSD increase over time, reaching 0.412 in the peak windows — suggesting the proposer and critic roles are differentiating most strongly.

## Lexical Uniqueness

Fraction of each agent's vocabulary not used by the other agents:

| Agent | Uniqueness |
|---|---|
| [[Agent 1 — Critic\|Agent 1]] | **0.2199** (most unique) |
| [[Agent 0 — Proposer\|Agent 0]] | 0.2016 |
| [[Agent 2 — Synthesizer\|Agent 2]] | 0.1959 (least unique) |

Agent 1 (critic) has the most distinctive vocabulary, consistent with evaluative and methodological language. Agent 2 (synthesizer) has the least, consistent with borrowing language from both other roles.

## Caveats

- JSD is computed on raw word frequencies, not semantic embeddings. Surface-level variation (different words with same meaning) inflates divergence.
- Temperature=1.0 introduces stochastic variation. Some divergence is noise, not stable differentiation.
- The window size of 10 rounds was chosen heuristically; different window sizes might show different patterns.

## Related

- [[Metric B — Behavioral Specialization]] — Behavioral dimension of divergence
- [[Metrics Summary & Interpretation]] — Cross-metric synthesis
- [[Risks & Confounds]] — Confound discussion
