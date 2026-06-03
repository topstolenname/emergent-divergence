---
title: "Metric B — Behavioral Specialization"
created: 2026-03-10
tags: [metrics, behavioral-specialization, keyword-classification]
---

# Metric B — Behavioral Specialization

## Method

Each agent message is classified into 6 behavioral categories using **keyword density**: the fraction of category keywords found in the message text. Categories and their keyword lists:

| Category | Keywords |
|---|---|
| Proposal | suggest, propose, idea, what if, consider, approach, solution, let's try, we could, one option |
| Critique | disagree, however, but, flaw, weakness, problem, issue, concern, incorrect, overlook, miss |
| Synthesis | combining, integrate, overall, together, summary, consensus, both points, building on, merge, reconcile |
| Verification | evidence, data, study, research shows, according, specifically, fact, source, citation, empirically |
| Recall | earlier, previously, as we discussed, remember, last round, noted before, prior, mentioned |
| Clarification | what do you mean, clarify, elaborate, specifically, define, in other words, meaning |

Per-agent profiles are the mean scores across all 100 messages per agent. Behavioral divergence is the mean pairwise L2 distance between profile vectors.

## Results

### Behavioral Profiles

```
              Proposal  Critique  Synthesis  Verification  Recall  Clarification
Agent 0       0.302     0.217     0.039      0.153         0.025   0.033
Agent 1       0.095     0.273     0.020      0.217         0.025   0.047
Agent 2       0.149     0.262     0.055      0.212         0.013   0.041
```

### Profile Visualization

```
Agent 0 (Proposer):   ████████████████░░░░░░░ Proposal dominates
Agent 1 (Critic):     ███░░░░░░░░░░░░░░░░░░░ Low proposal
                      █████████████████░░░░░░ Critique + Verification dominant
Agent 2 (Synthesizer):██████░░░░░░░░░░░░░░░░ Balanced middle ground
```

### Behavioral Divergence Score: **0.1544**

This measures the average pairwise L2 distance between the three profile vectors. A score of 0 would mean identical profiles; higher values indicate more specialization.

## Interpretation

### Agent 0 — Proposer

Strongest at proposal (0.302), which is 3.2x Agent 1's proposal score. This agent clearly leads idea generation. Also shows moderate critique (0.217), suggesting it isn't locked into pure proposal mode.

### Agent 1 — Critic

Strongest at critique (0.273) and verification (0.217). Weakest at proposal (0.095) and synthesis (0.020). This is the most specialized agent — strongly differentiated toward evaluative behavior.

### Agent 2 — Synthesizer

Most balanced profile. Leads in synthesis (0.055) but scores are low across the board for synthesis keywords. Has moderate levels of everything else. This balanced profile is itself a form of specialization — the synthesizer role manifests as *not* being extreme on any dimension.

## Key Finding

**Role biases are reflected in behavioral profiles, but not deterministically.** Each agent's highest-scoring category matches their role bias, but agents still engage in behaviors outside their bias. Agent 0 (proposer) critiques, Agent 1 (critic) occasionally proposes, and Agent 2 (synthesizer) critiques frequently. The biases shape tendencies, not rigid roles.

## Caveats

- **Keyword-based classification is crude.** Many proposal, critique, and synthesis behaviors use language that doesn't match the keyword lists. Future work should use embedding-based classification or LLM-judge scoring.
- **Synthesis is systematically undercounted.** The keyword list for synthesis is narrow and may miss nuanced synthesis behaviors that use different phrasing.
- **No temporal dimension.** Profiles are averaged over all 50 rounds. Behavioral evolution within the run is not captured by this metric.

## Related

- [[Metric A — Linguistic Divergence (JSD)]] — Linguistic dimension
- [[Agent 0 — Proposer]] | [[Agent 1 — Critic]] | [[Agent 2 — Synthesizer]]
- [[Metrics Summary & Interpretation]]
