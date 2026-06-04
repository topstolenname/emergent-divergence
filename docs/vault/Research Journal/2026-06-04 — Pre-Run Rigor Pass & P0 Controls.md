---
title: "2026-06-04 — Pre-Run Rigor Pass & P0 Controls"
created: 2026-06-04
project: emergent-divergence
tags: [journal, entry, rigor, reproducibility, methodology]
---

# 2026-06-04 — Pre-Run Rigor Pass & P0 Controls

> Final methodological review before the full matrix run, followed by landing the
> three highest-leverage pre-run controls and merging the two open feature PRs.

## Context

The codebase was feature-complete for the full 2×3×4 matrix (backends `llama3.2:3b` +
`claude-sonnet-4-6`; conditions A/B/C; seeds 42–45; T=50 rounds) and the question was
no longer "does it run" but **"would the results withstand rigorous peer review after
`run_all.sh`?"** A combined pass — external literature on best practice plus an internal
audit of the rigor-critical files — was done to answer that and produce a punch-list.

## What changed

Two PRs merged to `main`:

- **#4 — CoT qualitative judge** (`evaluation/judge.py`): a complementary, *identity-aware*
  rubric evaluator (role consistency, distinctiveness, contribution quality, coherence,
  engagement; 1–5, Chain-of-Thought before scoring). Kept **separate** from the blind
  six-category divergence classifier (`metrics/llm_judge.py`), which stays the production
  metric and stays blind by design. Declined a frozen-prompt refactor and a marketing doc.
- **#5 — P0 pre-run rigor controls** (this entry's focus). None alter the experiment's
  design; they add a missing measurement, a safety gate, and reproducibility metadata.

### The three P0 controls (PR #5)

1. **Same-prompt resampling null baseline** (`orchestration/runner.py`). On each measured
   round every agent is resampled `null_k = max(2, k_samples)` times on the *identical*
   task prompt (`_run_null_baseline_probe`, logging `null_baseline_start` /
   `null_baseline_samples`). The intra-agent spread is the pure decoding-noise floor that
   genuine **between-agent** divergence must exceed — without it a rising divergence trend
   could be nothing but `temperature=1.0` sampling. Uses a disjoint seed stream
   (`_NULL_SEED_OFFSET`) so it is independent of the influence probe.
2. **Embedder integrity gate** (`embeddings/embedder.py` + `pipeline.py`). Semantic
   divergence/influence are only semantic on MiniLM; on the lexical hashing fallback they
   silently collapse to word overlap. Real runs now **abort before any spend** (exit 4)
   unless `--smoke` or `ALLOW_HASHING_EMBEDDER=1`.
3. **Manifest provenance** (`pipeline.py`). `RUN_MANIFEST.json` gains a `provenance` block:
   git SHA / branch / dirty, Ollama model content digest, Claude dated-snapshot detection
   with a pin-warning for rolling aliases, plus python / platform / package version. A
   follow-up fixed the Ollama match to compare the full `repo:tag` (missing tag → `:latest`)
   so a different installed tag can never supply the wrong digest.

## Results & evidence

- Suite green on the merged state; `ruff` clean. New tests cover null-probe logging +
  disable, the embedder gate (abort / opt-in / smoke-bypass), `is_fallback`, the provenance
  fields, and the Ollama tag-matching edge case.
- A clean offline smoke run confirmed the null events materialise
  (`null_baseline_start`, `null_baseline_samples`) and the provenance block populates.
- Traceability: see `main` commits for #4 (`Implement CoT qualitative judge`) and #5
  (`Add P0 pre-run rigor controls …`).

## Decisions & rationale

**Verdict on readiness.** As an honest **exploratory / pilot** study the design is strong
and close to ready. As a **confirmatory** study (reporting H1–H5 / H-I1–3 as
Supported/Not-supported), it is **not yet** there — the controls below move it closer, but
the statistical-power and multiplicity items are genuine and must be framed honestly.

**Standards the design is being checked against** (for the eventual Limitations section):

| Dimension | Key standard(s) | Status |
|---|---|---|
| Statistical rigor | bootstrap CIs unreliable at small N (Efron & Tibshirani 1993); multiplicity correction (Benjamini–Hochberg 1995); few-seed ML uncertainty (Henderson 2018; Agarwal *rliable* 2021); autocorrelated trend tests (Yue & Wang 2002) | ⚠ N=4; no multiplicity correction yet |
| LLM-judge validity | self-preference when same family judges itself (Panickssery 2024; Zheng MT-Bench 2023); G-Eval calibration (Liu 2023) | ⚠ no human-validated κ / out-of-family judge yet |
| Reproducibility | pin dated snapshots, log digests; silent API drift (Chen, Zaharia & Zou 2024); REFORMS / repro checklists (Kapoor & Narayanan 2024) | ✓ provenance landed; pin the dated Claude snapshot before the paid run |
| Causal / influence | average interventional, not per-instance counterfactual; influence ≠ manipulation (Carroll et al. 2023); ablation-method sensitivity (Optimal Ablation, NeurIPS 2024) | ✓ honestly scoped; run both `neutral` + `drop` as robustness |
| Construct validity | same-prompt null vs sampling noise; emergence-as-metric-artifact (Schaeffer 2023); cosine arbitrariness (Steck 2024); JSD finite-size bias (Shade & Altmann 2023); context-growth / lost-in-the-middle (Liu 2024) | ⚠ null baseline now collected; analysis-side use pending |

**Highest-value single addition** was the null baseline — it converts "agents diverge"
from "could be temperature noise" into "exceeds the sampling floor," and it had to be
**logged during the run**, hence P0.

## Risks / confounds surfaced

For [[Risks & Confounds]]: (1) N=4 underpowers bootstrap CIs and the A/B contrasts;
(2) no FWER/FDR correction across the H1–H5 / H-I1–3 × metrics × conditions grid;
(3) same-family judging (Haiku judging Sonnet) is unvalidated against human labels;
(4) the "increases over rounds" claim faces repetition/degeneration and context-growth
confounds; (5) absolute cosine/JSD are not calibrated constructs.

## Next

- [ ] **Pre-run:** pin a *dated* Claude snapshot in `configs/pipeline.yaml`; verify
      `RUN_MANIFEST.json → preflight.embedder.backend == "minilm"`.
- [ ] **Run** the full matrix via `run_all.sh`; archive `RUN_MANIFEST.json` + `results.csv`.
- [ ] **P1 (write-up):** consume the null floor in the stats; Benjamini–Hochberg (or one
      primary metric); human-validate the judge + an out-of-family cross-check; re-test each
      trend under a 2nd near-linear metric with CIs; report repetition-rate / length covariates.
- [ ] Frame the paper as a **pilot** with effect sizes + CIs, not confirmatory verdicts.

---

## Related

- [[00 — Journal Index]]
- [[Experiment Roadmap]] — Phased run plan
- [[Risks & Confounds]] — Validity threats being de-risked
- [[Metric A — Linguistic Divergence (JSD)]] | [[Metric B — Behavioral Specialization]]
- [[04 — Lineage & Provenance]]
