# Emergent Divergence — Report (`smoke`)

_Generated 2026-06-05T01:48:36.562493+00:00_

## Abstract

This run (`smoke`) measured emergent behavioral divergence and cross-agent influence among three same-model agents (Proposer / Critic / Synthesizer) coordinating over multi-turn claim-analysis tasks. It analyzed **3 matrix cells** across backends ['stub'], conditions A/B/C, computing all semantic quantities with a shared `hashing-fallback` embedder so the two backends are directly comparable. Total spend was **$0.00**.

- stub: 1 supported, 2 mixed of 8 hypotheses

## Methods

**Design.** A `backends × conditions × seeds` matrix. Conditions: **A** = memory + weak role priors; **B** = memory disabled (context reset each round) + weak priors; **C** = memory + zero role priors (generic identical agents). Each cell runs independent, checkpointed rounds of two-turn deliberation with starting-agent rotation.

**Divergence metrics.** Linguistic divergence is the windowed mean pairwise Jensen-Shannon divergence (JSD, base 2) of agents' word-frequency distributions; its trend over rounds is a Spearman ρ (H1). Behavioral specialization scores how agents' message-act profiles differ (H2). Semantic divergence is the mean pairwise cosine distance between agent response embeddings (shared `hashing-fallback` embedder), with its round-trend as a Spearman ρ (H3).

**Influence-delta.** On every Nth round a counterfactual probe builds a canonical context where each target sees all other agents, generates factual continuations, then re-generates with one source ablated. The influence of source *i* on target *j* is the change between the two continuation pools — semantically (`id_sem`, centroid cosine distance) and lexically (`id_tok`, token-JSD). Aggregated over rounds these form an influence matrix `M[source→target]`; row sums give outgoing influence, `A = M − Mᵀ` gives net directed influence, and the Gini of row sums measures concentration / hub formation (H-I2). A lagged Spearman correlation tests whether influence precedes divergence (H-I3).

**Statistics.** Headline metrics are aggregated over seeds with percentile bootstrap 95% CIs; the memory contrast (A vs B) uses a bootstrap CI on the mean difference plus Cohen's *d*. Each hypothesis verdict is **data-driven**: *Supported* when the relevant CI excludes 0 in the hypothesized direction, *Mixed* when the point estimate points the right way but the CI straddles 0, *Not supported* otherwise.


## Results — backend `stub`

_3 cells; condition n = {'A': 1, 'B': 1, 'C': 1}_


### Headline metrics (95% bootstrap CI)

| Metric | A | B | C |
| --- | --- | --- | --- |
| Linguistic JSD | 0.295 (n=1) | 0.263 (n=1) | 0.269 (n=1) |
| Semantic cosine | 0.100 (n=1) | 0.081 (n=1) | 0.077 (n=1) |
| Behavioral div. | 0.088 (n=1) | 0.056 (n=1) | 0.051 (n=1) |
| Influence μ (sem) | 0.077 (n=1) | 0.091 (n=1) | 0.094 (n=1) |
| Influence Gini | 0.430 (n=1) | 0.463 (n=1) | 0.461 (n=1) |
| Semantic ρ (trend) | — | — | — |


### Hypothesis verdicts

| Hyp | Verdict | Statement | Evidence |
| --- | --- | --- | --- |
| H1 | **Insufficient data** | Linguistic divergence increases over rounds (Spearman ρ on pairwise JSD). | — |
| H2 | **Mixed** | Agents specialize behaviorally by role. | 0.088 (n=1) |
| H3 | **Insufficient data** | Semantic divergence increases over rounds (Spearman ρ on MiniLM cosine). | — |
| H4 | **Mixed** | Memory amplifies divergence (condition A > condition B). | Δ=0.018418, d=None, [0.018418, 0.018418] |
| H5 | **Insufficient data** | Divergence occurs even without role priors (condition C). | — |
| H-I1 | **Not supported** | Memory amplifies cross-agent influence (A > B). | Δ=-0.013743, d=None, [-0.013743, -0.013743] |
| H-I2 | **Supported** | Influence concentrates into a hub (Gini of outgoing influence). | Gini 0.430 (n=1) |
| H-I3 | **Insufficient data** | Influence precedes divergence (lagged correlation, lag ≥ 1). | proportion None |

![Divergence metrics by condition — stub](figures/divergence_by_condition_stub.svg)
*Divergence metrics by condition — stub*


![Influence metrics by condition — stub](figures/influence_by_condition_stub.svg)
*Influence metrics by condition — stub*


![Influence matrix M[source→target] (condition A) — stub](figures/influence_heatmap_stub.svg)
*Influence matrix M[source→target] (condition A) — stub*


## Cross-backend comparison (condition A)

| Metric | stub |
| --- | --- |
| Linguistic JSD | 0.295 (n=1) |
| Semantic cosine | 0.100 (n=1) |
| Behavioral div. | 0.088 (n=1) |
| Influence μ (sem) | 0.077 (n=1) |
| Influence Gini | 0.430 (n=1) |

## Hypothesis verdicts (all backends)

| Hyp | Statement | stub |
| --- | --- | --- |
| H1 | Linguistic divergence increases over rounds (Spearman ρ on pairwise JSD). | Insufficient data |
| H2 | Agents specialize behaviorally by role. | Mixed |
| H3 | Semantic divergence increases over rounds (Spearman ρ on MiniLM cosine). | Insufficient data |
| H4 | Memory amplifies divergence (condition A > condition B). | Mixed |
| H5 | Divergence occurs even without role priors (condition C). | Insufficient data |
| H-I1 | Memory amplifies cross-agent influence (A > B). | Not supported |
| H-I2 | Influence concentrates into a hub (Gini of outgoing influence). | Supported |
| H-I3 | Influence precedes divergence (lagged correlation, lag ≥ 1). | Insufficient data |

## Limitations

- **Influence is not manipulation.** The influence-delta measures how much one agent's *presence* changes another's output under ablation. It does **not** measure intent, persuasion, or manipulation, and is never relabelled as such.
- **Small samples.** CIs are bootstrap estimates over a handful of seeds; treat wide intervals and single-seed cells as suggestive, not conclusive.
- **Claude non-determinism.** The paid backend does not honor a generation seed, so its variance is absorbed into the seed-level CIs rather than removed.
- **Embedder fallback.** Semantic quantities used the deterministic `hashing-fallback` embedder (sentence-transformers not installed). Numbers are internally consistent and comparable across backends, but are *not* MiniLM semantic distances; install the `analysis` extra for the primary embedder.


## Reproducibility

- **Run id:** `smoke`
- **Command:** `./run_all.sh` (or `python -m emergent_divergence pipeline`).
- **Config:** `configs/pipeline.yaml` (single source of truth); environment overrides `ROUNDS`/`SEEDS`/`COST_CAP_USD`/`INFLUENCE_EVERY_N`/`K_SAMPLES`.
- **Artifacts:** `results.csv`, `results.json`, `statistics.json`, `cell_reports.json`, `RUN_MANIFEST.json` (full config, prices, per-cell status, actual spend), and these figures.
- **Determinism:** Ollama and the stub honor per-call seeds; the matrix is checkpointed per cell (`status.json`) and resumes without double-counting spend.
