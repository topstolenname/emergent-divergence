# Emergent Divergence — Pilot Run Analysis Report

**Generated**: 2026-04-05
**Scope**: All experiment runs completed to date
**Purpose**: Summarize findings, assess repo readiness, and identify next steps

---

## 1. Inventory of Experiment Output Files

### Completed Runs

| Run ID | Condition | Seed | Rounds Completed | Events | Status |
|--------|-----------|------|-----------------|--------|--------|
| `run_20260310_161255_db9f7b49` | memory_enabled | 42 | 49 | 703 lines | **Complete** (original pilot) |
| `run_20260318_014704_seed42_memory_enabled_5858a3` | memory_enabled | 42 | 50 | 703 lines | **Complete** (matrix run) |
| `run_20260318_024307_seed42_no_memory_6c6c75` | no_memory | 42 | 4 | 32 lines | **Partial** (ran out of credits) |

### Failed / Incomplete Runs

| Run ID | Condition | Status | Notes |
|--------|-----------|--------|-------|
| `run_20260318_014100_seed42_memory_enabled_e09fe3` | memory_enabled | Aborted | 5 event lines only — likely a false start |
| `run_20260318_014101_seed42_no_memory_cc957f` | no_memory | Aborted | 5 event lines only — likely a false start |
| `matrix_manifest.json` no_memory entry | no_memory | **Failed** | API credit balance error after ~250s / 4 rounds |

### Generated Artifacts

| File | Location | Contents |
|------|----------|----------|
| `analysis_report.json` | `data/raw_logs/run_20260310_161255_db9f7b49/` | Full metric report for original pilot (49 rounds) |
| Memory logs (×3) | `run_..._db9f7b49/memory/agent_{0,1,2}.jsonl` | Per-agent memory store for original pilot |
| Memory logs (×3) | `run_..._5858a3/memory/agent_{0,1,2}.jsonl` | Per-agent memory store for matrix memory run |
| `metadata.json` (×4) | Each run directory | Config snapshot for reproducibility |

### Missing Artifacts

- **No `analysis_report.json`** for the matrix memory-enabled run (`5858a3`) — needs to be generated
- **No figures** (PNG/SVG/PDF) anywhere in the repo — no visualizations have been created
- **No `data/processed/` outputs** — directory contains only `.gitkeep`
- **No `data/reports/` outputs** — directory contained only `.gitkeep` before this report
- **No `statistical_analysis.json`** exists as a standalone file — the statistical claims (Spearman ρ=0.511, p=0.0007) appear to come from external analysis not captured in the repo

---

## 2. Key Metrics from the Completed Run

All metrics below are from `analysis_report.json` (original pilot, `run_20260310_161255_db9f7b49`, 49 rounds, memory enabled, seed 42).

### A. Linguistic Divergence (JSD)

| Metric | Value |
|--------|-------|
| Mean pairwise JSD (overall) | **0.2935** |
| Agent 0 vs Agent 1 | 0.2986 |
| Agent 0 vs Agent 2 | 0.2870 |
| Agent 1 vs Agent 2 | 0.2947 |

**JSD over time (sliding window of 10 rounds):**

| Window | Mean JSD | Trend |
|--------|----------|-------|
| Rounds 1–10 (early) | 0.382 | Baseline |
| Rounds 11–20 (mid-early) | 0.384–0.390 | Gradual increase |
| Rounds 17–26 (mid-peak) | **0.396–0.403** | **Peak divergence** |
| Rounds 22–31 (mid-late) | 0.398–0.403 | Plateau |
| Rounds 36–45 (late) | 0.384–0.391 | Slight decline |
| Rounds 40–49 (final) | 0.392 | Stabilized |

**Trajectory summary**: JSD rises ~5.5% from early windows (0.382) to a peak around rounds 20–30 (0.403), then settles back to ~0.392. The proposer–critic pair (Agent 0 vs Agent 1) shows the strongest divergence, peaking at JSD=0.412.

### B. Behavioral Specialization

| Agent | Role Bias | Proposal | Critique | Synthesis | Verification | Recall | Clarification |
|-------|-----------|----------|----------|-----------|--------------|--------|---------------|
| Agent 0 | Proposer | **0.302** | 0.217 | 0.039 | 0.153 | 0.025 | 0.033 |
| Agent 1 | Critic | 0.095 | **0.273** | 0.020 | **0.217** | 0.025 | 0.047 |
| Agent 2 | Synthesizer | 0.149 | 0.262 | **0.055** | 0.212 | 0.013 | 0.041 |

- **Behavioral divergence score**: **0.1544** (mean pairwise L2 distance between profile vectors)
- Each agent's dominant behavior aligns with their role bias
- Agent 1 (Critic) also leads in verification — natural pairing
- Synthesis scores are universally low, likely due to keyword classifier undercounting (noted in vault docs)

### C. Lexical Uniqueness

| Agent | Unique Word Ratio |
|-------|-------------------|
| Agent 0 (Proposer) | 20.2% |
| Agent 1 (Critic) | **22.0%** |
| Agent 2 (Synthesizer) | 19.6% |

Agent 1 (Critic) uses the most distinctive vocabulary, consistent with a critical/evaluative role requiring more specialized language.

### D. Memory Usage

All agents show **identical** memory patterns: 100 writes, 945 reads, 9.45 mean reads/message, max 10 reads. Memory usage is structurally symmetric — the current design doesn't create differential usage.

### E. Coordination Structure

Equal message counts (100 per agent) and fixed turn order. Agent 0 is always first speaker (49/49 rounds). No emergent coordination structure is possible under the current forced-rotation design.

---

## 3. Hypothesis Assessment

### H1 — Linguistic Divergence Increases Over Time

**Status: Weak-to-moderate support (pending statistical confirmation)**

The JSD sliding window data shows a ~5.5% increase from early to peak, which is modest. You report a Spearman ρ=0.511 (p=0.0007) correlation between round number and JSD — if confirmed, this is statistically significant and supports H1. However, this statistical test result is not captured anywhere in the repo's analysis pipeline.

**Key nuance**: The JSD trajectory shows a rise-then-plateau pattern rather than monotonic increase. Divergence peaks around rounds 20–30 and then partially retreats. This could reflect: (a) task bank recycling (the 20-claim bank repeats after round 20), (b) natural convergence as agents develop shared conventions, or (c) stochastic noise at temperature=1.0.

### H2 — Behavioral Role Specialization Emerges

**Status: Moderate support**

Behavioral profiles clearly differentiate along role lines. The divergence score of 0.1544 is non-trivial. However, the key question is whether this reflects emergent specialization or just prompt-driven differentiation from the role bias text. This cannot be answered without the no-role-bias ablation (Phase 3).

### H3 — Memory Amplifies Divergence

**Status: Cannot assess**

The no-memory control condition failed (API credits ran out after 4 rounds). Without a complete control run, memory's incremental contribution is unknown. This is the single most important gap.

### H4 — Coordination Structure Becomes Non-Uniform

**Status: Not testable under current design**

Fixed turn order prevents emergent coordination. Would require shuffled or optional turn-taking.

---

## 4. Consistency with README and Research Goals

The README states four success criteria, requiring evidence for "at least one":

| Criterion | README Claim | Actual Status |
|-----------|-------------|---------------|
| Linguistically distinct over time | Yes | Weak signal; needs statistical test in pipeline |
| Differentiated behavioral roles | Yes | Moderate support from keyword classifier |
| Memory increases divergence vs controls | Yes | **Cannot assess — control missing** |
| Non-uniform coordination | Yes | Not testable with current design |

**Assessment**: The results are *consistent* with the research goals but fall short of being *conclusive*. The experiment is generating the kind of signal the design was meant to detect, but the absence of the control condition is a critical gap. The README should be updated to reflect that this is a pilot finding, not a confirmed result.

---

## 5. Recommended Repo Updates

### 5.1 README.md Updates

The README currently has no results section. Add one:

```markdown
## Pilot Results (Condition A: Memory Enabled, Seed 42, 50 Rounds)

- **H1 (Linguistic divergence)**: Weak-to-moderate support. JSD increases ~5.5%
  from early to peak windows (0.382 → 0.403), with Spearman ρ=0.511, p=0.0007.
- **H2 (Behavioral specialization)**: Moderate support. Agents differentiate along
  role lines (divergence score = 0.154).
- **H3 (Memory effect)**: Cannot assess — no-memory control incomplete.
- **H4 (Coordination structure)**: Not testable under fixed-rotation design.

See `data/reports/` for detailed analysis.
```

### 5.2 Generate Missing Analysis Report

Run the analysis on the matrix memory-enabled run:

```bash
python -m emergent_divergence analyze --run-dir data/raw_logs/run_20260318_014704_seed42_memory_enabled_5858a3
```

This will produce an `analysis_report.json` for the 50-round run (vs. the current 49-round pilot). Compare the two to verify consistency.

### 5.3 Add the Spearman Test to the Pipeline

The Spearman ρ=0.511 (p=0.0007) result is not computed by the existing `divergence.py` metrics module. Either:

- Add a `compute_temporal_correlation()` function to `divergence.py` that computes Spearman correlation between window index and mean JSD
- Or add a standalone script in `scripts/` that performs the statistical test
- Document the methodology so the result is reproducible

### 5.4 Generate Figures

No figures exist anywhere in the repo. Create at minimum:

1. **JSD over time plot** — sliding window mean JSD with confidence band (the most important figure)
2. **Behavioral profile radar chart** — per-agent behavioral category scores
3. **Pairwise JSD heatmap** — 3×3 matrix showing agent-pair divergence

These should be saved to `data/reports/figures/` and referenced from the README or vault docs.

### 5.5 Clean Up Failed Runs

The aborted runs add noise to the data directory:

| Run | Action |
|-----|--------|
| `run_20260318_014100_seed42_memory_enabled_e09fe3` | Delete (5-line false start) |
| `run_20260318_014101_seed42_no_memory_cc957f` | Delete (5-line false start) |
| `run_20260318_024307_seed42_no_memory_6c6c75` | Keep but mark as incomplete in a manifest |

### 5.6 Update Experiment Roadmap

The `Experiment Roadmap.md` in the vault should reflect that:

- P1-01 is done (two complete memory-enabled runs exist)
- P1-02 (no-memory control) failed and needs re-running
- The matrix manifest should be regenerated after a successful control run

### 5.7 New Files to Commit

| File | Purpose |
|------|---------|
| `data/reports/pilot_analysis_report.md` | This report |
| `data/reports/figures/` (once generated) | Visualization outputs |
| Updated `README.md` | Add results section |
| Updated `divergence.py` (if adding Spearman test) | Statistical test in pipeline |

---

## 6. Gaps and Blocking Issues

### Critical (Blocks Publication)

1. **No-memory control (Condition B) is incomplete.** The single most important next step. Without it, H3 cannot be assessed and the entire experimental design lacks its primary comparison. Requires Anthropic API credits.

2. **Spearman test not in pipeline.** The headline finding (ρ=0.511, p=0.0007) cannot be reproduced from the repo's analysis tools. Either add it to `divergence.py` or provide a reproducible script.

3. **No figures.** A research project with zero visualizations is difficult to communicate. The JSD-over-time plot is essential.

### Important (Needed Before Broader Claims)

4. **Only one seed (42).** The roadmap calls for seeds 42–45. A single seed cannot distinguish stable signal from task-specific noise. At minimum, seed 43 for both conditions would help.

5. **Keyword classifier is crude.** Synthesis is systematically undercounted (max score 0.055). The LLM-judge pipeline exists as a placeholder (`judge.py`) but hasn't been run. Phase 4 of the roadmap addresses this.

6. **Two overlapping memory-enabled runs.** Both `db9f7b49` (49 rounds) and `5858a3` (50 rounds) are complete memory-enabled seed-42 runs. Clarify which is canonical. The 50-round run (`5858a3`) should be primary, but it lacks an `analysis_report.json`.

### Nice-to-Have (Future Phases)

7. **No role-bias ablation.** Phase 3 would isolate prompt-driven vs. interaction-driven divergence.
8. **Fixed turn order.** H4 cannot be tested without design changes.
9. **No temporal behavioral analysis.** Phase 5 would track specialization over time.
10. **Dashboard not deployed.** A Streamlit dashboard exists in `dashboard/` but hasn't been documented or connected to results.

---

## 7. Recommended Next Actions (Priority Order)

1. **Top up API credits and run the no-memory control** (`python -m emergent_divergence run --config configs/no_memory.yaml --rounds 50`). Cost: ~$3. Time: ~1 hour.

2. **Generate `analysis_report.json` for the 50-round memory run** (`python -m emergent_divergence analyze --run-dir data/raw_logs/run_20260318_014704_seed42_memory_enabled_5858a3`).

3. **Add Spearman temporal correlation test** to `divergence.py` or as a script, so the ρ=0.511 result is reproducible.

4. **Create figures** (JSD over time, behavioral profiles, pairwise heatmap) and save to `data/reports/figures/`.

5. **Update README.md** with a pilot results section and figure references.

6. **Clean up aborted runs** from `data/raw_logs/`.

7. **Run seed 43** for both conditions (Phase 1 completion).

8. **Compare conditions** once the no-memory control is available (`python -m emergent_divergence compare --runs <memory_run> <no_memory_run>`).
