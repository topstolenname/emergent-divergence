---
title: "Experiment Roadmap"
created: 2026-03-10
tags: [roadmap, de-risking, experiment-plan, runs, stopping-criteria]
---

# Experiment Roadmap

A concrete, phased plan to de-risk the five weaknesses identified in the pilot run ([[Run Summary — run_20260310_161255_db9f7b49]]).

---

## Observed Costs from Pilot

| Metric | Pilot Value |
|---|---|
| API calls per 50-round run | 300 |
| Wall-clock time | ~57 min |
| Mean latency / message | 11.3 s |
| Est. output tokens | ~144K |
| Est. cost per run (blended) | ~$2–3 |

All estimates below use **$3/run** as a conservative per-run cost.

---

## Phase 1 — Establish a Baseline Comparison

**Goal**: Determine whether memory contributes anything beyond role bias + stochastic variation.

### Run Matrix

| Run | Condition | Memory | Role Bias | Seed | Rounds | Status |
|---|---|---|---|---|---|---|
| P1-01 | A (memory) | on | on | 42 | 50 | **DONE** |
| P1-02 | B (no-memory) | **off** | on | 42 | 50 | TODO |
| P1-03 | A (memory) | on | on | 43 | 50 | TODO |
| P1-04 | B (no-memory) | **off** | on | 43 | 50 | TODO |

**Cost**: 3 new runs × $3 = **~$9**
**Time**: 3 × 57 min = **~2.8 hours** (sequential) or ~1 hour (parallel)

### Commands

```bash
# P1-02
python -m emergent_divergence run --config configs/no_memory.yaml --rounds 50

# P1-03 (requires adding --seed CLI flag or editing YAML)
# memory_enabled.yaml with seed: 43
python -m emergent_divergence run --config configs/memory_enabled.yaml --rounds 50

# P1-04
# no_memory.yaml with seed: 43
python -m emergent_divergence run --config configs/no_memory.yaml --rounds 50
```

### Comparison Metrics

For each run, extract:

| Metric | Source |
|---|---|
| Mean JSD (overall) | `analysis_report.json → linguistic_divergence.mean_jsd` |
| Peak JSD (max sliding window mean) | `jsd_over_time → max(mean_jsd)` |
| Final-window JSD (last window) | `jsd_over_time[-1].mean_jsd` |
| JSD slope (linear fit over windows) | Compute from `jsd_over_time` |
| Behavioral divergence score | `behavioral_specialization.divergence_score` |
| Lexical uniqueness spread | `max(uniqueness) - min(uniqueness)` |

### Stopping Criteria

| Criterion | Decision |
|---|---|
| Memory condition beats no-memory on mean JSD in **both** seeds | Memory effect is **supported** → proceed to Phase 2 |
| Memory condition beats no-memory in **1 of 2** seeds | **Ambiguous** → add seeds 44, 45 before deciding |
| Memory condition shows **no advantage** in either seed | Memory effect is **not supported** → skip to Phase 3 (role-bias ablation) |

### Null Result Protocol

If memory shows no effect:

> Divergence appears attributable to role bias and interaction structure rather than memory persistence.

Document this as a genuine finding, not a failure. Redirect effort to the role-bias ablation (Phase 3).

---

## Phase 2 — Strengthen with Seed Panel

**Goal**: Estimate variance and confirm stability of Phase 1 findings.

**Prerequisite**: Phase 1 showed at least ambiguous signal for memory.

### Run Matrix

| Run | Condition | Memory | Seed | Rounds |
|---|---|---|---|---|
| P2-01 | A | on | 44 | 50 |
| P2-02 | B | off | 44 | 50 |
| P2-03 | A | on | 45 | 50 |
| P2-04 | B | off | 45 | 50 |

**Cost**: 4 runs × $3 = **~$12**
**Time**: ~3.8 hours sequential

### Analysis

With 4 seeds × 2 conditions = 8 total runs:

1. **Compute per-seed deltas**: For each seed, `Δ_JSD = mean_JSD(memory) - mean_JSD(no_memory)`
2. **Report**: mean(Δ_JSD), sd(Δ_JSD), range
3. **Sign test**: Count how many of 4 seeds show positive Δ_JSD

### Stability Rule (Predefined)

> We consider the memory effect **stable** if memory-enabled runs exceed no-memory runs on mean JSD in **at least 3 of 4 seeds**.

### Summary Table Template

| Seed | Mean JSD (Mem) | Mean JSD (No-Mem) | Δ | Behav Div (Mem) | Behav Div (No-Mem) | Δ |
|---|---|---|---|---|---|---|
| 42 | 0.2935 | ? | ? | 0.1544 | ? | ? |
| 43 | ? | ? | ? | ? | ? | ? |
| 44 | ? | ? | ? | ? | ? | ? |
| 45 | ? | ? | ? | ? | ? | ? |
| **Mean** | | | | | | |
| **SD** | | | | | | |

---

## Phase 3 — Role-Bias Ablation

**Goal**: Determine how much of the observed divergence is prompt-driven vs. interaction-driven.

**This phase runs regardless of Phase 1/2 outcomes.** Even if memory has no effect, the role-bias question is independently important.

### New Condition: No Role Bias

Create `configs/no_role_bias.yaml`:

```yaml
num_agents: 3
role_biases:
  - neutral    # All agents get identical prompts
  - neutral
  - neutral
memory_enabled: true
memory_max_entries: 200
model: "claude-sonnet-4-20250514"
max_tokens: 1024
temperature: 1.0
num_rounds: 50
turns_per_round: 2
condition: "no_role_bias"
seed: 42
output_dir: "data/raw_logs"
```

This requires a small code change: add a `"neutral"` entry to `ROLE_BIASES` in `agent.py` that contains only the agent ID and no behavioral inclination.

### Run Matrix (2×2 Factorial)

| Run | Memory | Role Bias | Seed | Condition Label |
|---|---|---|---|---|
| P1-01 | on | on | 42 | **DONE** (A) |
| P1-02 | off | on | 42 | B (from Phase 1) |
| P3-01 | on | **off** | 42 | C |
| P3-02 | off | **off** | 42 | D |

**Cost**: 2 new runs × $3 = **~$6**

### Interpretation Guide

| Result Pattern | Conclusion |
|---|---|
| A > B > C ≈ D | Both memory and role bias contribute; memory amplifies role-driven divergence |
| A ≈ B > C ≈ D | Role bias drives divergence; memory has no incremental effect |
| A > C > B ≈ D | Memory drives divergence; role bias has modest effect |
| A ≈ B ≈ C ≈ D | Divergence is stochastic noise; neither memory nor role bias matter |
| A > B, C > D | Memory drives divergence independently of role bias (strongest finding) |

Where `>` means "higher mean JSD and/or behavioral divergence."

### Role Leakage Check

For the full-bias conditions (A and B), measure:

- Does "critic" language appear in proposer outputs?
- Does "proposal" language appear in critic outputs?

If profiles are somewhat mixed (as observed in the pilot), that supports the claim that biases are weak inclinations, not deterministic scripts.

---

## Phase 4 — Upgrade Behavioral Classifier

**Goal**: Replace the crude keyword classifier with LLM-judge classification, validated against human labels.

**Prerequisite**: At least Phase 1 is complete (you need run data to classify).

### Step 1: Build a Gold Set

1. Randomly sample **100 messages** from the pilot run (stratified: ~33 per agent)
2. **Label each message** with one or more categories: proposal, critique, synthesis, verification, recall, clarification
3. Record confidence (clear / ambiguous / edge-case)
4. Time: ~2–3 hours of manual work

### Step 2: LLM-Judge Classification

For each of the 100 sampled messages, prompt a separate model:

```
Classify this message from a multi-agent coordination experiment.

Categories (select all that apply, with confidence 0.0–1.0):
- proposal: generating ideas, suggesting solutions, introducing framings
- critique: evaluating critically, identifying weaknesses, pushing for rigor
- synthesis: integrating perspectives, finding common ground, reconciling
- verification: citing evidence, referencing data, demanding specifics
- recall: referencing prior rounds, memory, past discussions
- clarification: requesting definitions, asking for elaboration

Message:
"""
{message_text}
"""

Respond as JSON: {"proposal": 0.8, "critique": 0.1, ...}
```

### Step 3: Validate

| Comparison | Metric |
|---|---|
| Human vs. keyword classifier | Cohen's κ or accuracy on top-1 label |
| Human vs. LLM judge | Cohen's κ or accuracy on top-1 label |
| Keyword vs. LLM judge | Agreement rate |

**Expected outcome**: LLM judge substantially outperforms keywords, especially on synthesis (currently undercounted).

### Step 4: Re-Score All Runs

Once validated, apply the LLM judge to all messages across all runs. Recompute behavioral profiles and divergence scores. Compare with keyword-based results.

**Cost**: 100 messages × ~$0.002/call = **~$0.20** for validation. Full re-scoring of 300 messages/run × N runs = modest.

---

## Phase 5 — Temporal Behavioral Analysis

**Goal**: Track whether specialization deepens, fades, or remains stable over the course of a run.

### Method

Partition each run into terciles:

| Window | Rounds |
|---|---|
| Early | 0–16 |
| Middle | 17–33 |
| Late | 34–49 |

For each tercile, compute:
- Behavioral profiles per agent
- Behavioral divergence score
- Pairwise JSD

### Questions to Answer

| Question | What to Look For |
|---|---|
| Does specialization deepen? | Divergence score increases from Early → Late |
| Does memory accelerate specialization? | Memory condition shows steeper increase than no-memory |
| Do agents converge late-run? | JSD decreases in Late window (possible "consensus drift") |
| Is there a phase transition? | Sharp change at a specific round (e.g., after claim bank recycles at round 20) |

---

## Full Run Matrix (All Phases)

| ID | Phase | Memory | Role Bias | Seed | Rounds | Est. Cost | Status |
|---|---|---|---|---|---|---|---|
| P1-01 | 1 | on | on | 42 | 50 | $3 | **DONE** |
| P1-02 | 1 | off | on | 42 | 50 | $3 | TODO |
| P1-03 | 1 | on | on | 43 | 50 | $3 | TODO |
| P1-04 | 1 | off | on | 43 | 50 | $3 | TODO |
| P2-01 | 2 | on | on | 44 | 50 | $3 | TODO |
| P2-02 | 2 | off | on | 44 | 50 | $3 | TODO |
| P2-03 | 2 | on | on | 45 | 50 | $3 | TODO |
| P2-04 | 2 | off | on | 45 | 50 | $3 | TODO |
| P3-01 | 3 | on | **off** | 42 | 50 | $3 | TODO |
| P3-02 | 3 | off | **off** | 42 | 50 | $3 | TODO |

**Total**: 10 runs (9 new) × ~$3 = **~$27**
**Total time**: ~9.5 hours sequential, ~3 hours with 3-way parallelism

---

## Decision Tree

```
Start
  │
  ├─ Phase 1: Run P1-02, P1-03, P1-04
  │    │
  │    ├─ Memory beats no-memory in BOTH seeds?
  │    │    └─ YES → Phase 2 (add seeds 44, 45)
  │    │
  │    ├─ Memory beats no-memory in 1 of 2 seeds?
  │    │    └─ AMBIGUOUS → Phase 2 (add seeds 44, 45) to break tie
  │    │
  │    └─ Memory shows NO advantage?
  │         └─ Document null result → skip to Phase 3
  │
  ├─ Phase 2: Run P2-01 through P2-04
  │    │
  │    └─ Memory wins in ≥3 of 4 seeds?
  │         ├─ YES → Memory effect is stable → Phase 3
  │         └─ NO → Memory effect is marginal → Phase 3
  │
  ├─ Phase 3: Run P3-01, P3-02 (role-bias ablation)
  │    │
  │    └─ Interpret 2×2 factorial (see interpretation guide above)
  │
  ├─ Phase 4: Upgrade classifier (no new runs needed, uses existing data)
  │
  └─ Phase 5: Temporal analysis (no new runs needed, uses existing data)
```

---

## Constraints and Anti-Patterns

### Freeze Between Phases

- Do **not** change the claim bank between runs
- Do **not** change the model between conditions within the same phase
- Do **not** refactor the runner code mid-experiment (log format must remain consistent)

### Do NOT Do Yet

Per the [[04 — Lineage & Provenance|original architecture guidance]]:

- No additional agents (stay at 3) until 2×2 factorial is complete
- No TDA or topological metrics until behavioral classifier is upgraded
- No shared memory condition until per-agent memory effects are established
- No architecture refactoring until all Phase 1–3 data is collected

### Cost Guardrail

Total budget for all 10 runs: **~$30**. If any single run exceeds $5, investigate before proceeding (may indicate context window bloat or API pricing change).

---

## Methods Section Draft

Once Phases 1–3 are complete, the methods claim becomes:

> We compared memory-enabled and no-memory conditions across 4 seeds (42–45), and additionally ablated role-bias prompts in a 2×2 factorial design to distinguish prompt-induced specialization from interaction-driven divergence. Behavioral classification was validated against human labels using both keyword-density and LLM-judge approaches.

---

## Related

- [[Run Summary — run_20260310_161255_db9f7b49]] — Pilot run (P1-01)
- [[Risks & Confounds]] — Weaknesses this roadmap addresses
- [[Future Work]] — Broader aspirations beyond this roadmap
- [[Metrics Summary & Interpretation]] — Current state of evidence
- [[Config — memory_enabled.yaml]] | [[Config — no_memory.yaml]] — Existing configs
