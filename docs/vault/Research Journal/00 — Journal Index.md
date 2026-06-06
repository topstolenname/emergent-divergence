---
title: "Research Journal — Index"
created: 2026-06-04
project: emergent-divergence
tags: [journal, index, lab-notebook, white-paper-source]
---

# Research Journal

A chronological lab notebook for the **Emergent Behavioral Divergence** program. Each
entry records what was done, what was decided, what the evidence showed, and what is
next — in enough detail that the eventual **white paper** can be assembled directly
from these notes once the experiment is fully scaled.

This complements the rest of the vault:

- [[00 — Index]] documents the *state* of the experiment (design, metrics, runs).
- This journal documents the *process* — the dated trail of decisions and rationale
  behind that state. It is the primary-source material for Methods, Results, and
  Limitations.

> [!tip] One entry per working session or run
> Name entries `YYYY-MM-DD — Short Title.md`. Keep the newest at the top of the
> **Entry Log** below. Use [[_Entry Template]] as the skeleton.

---

## How to write an entry

Every entry should answer, in order:

1. **Context** — what prompted this session; where the program stood.
2. **What changed** — code, configs, design, or analysis (link PRs/commits/notes).
3. **Results & evidence** — numbers, plots, test output; what is *shown*, not claimed.
4. **Decisions & rationale** — what was chosen and *why*; what was rejected and why.
5. **Risks / confounds surfaced** — feeds [[Risks & Confounds]].
6. **Next** — the concrete next action(s).

Discipline that makes this publishable:

- Distinguish **shown** (has evidence) from **expected** (hypothesis) from **decided**
  (a judgement call) — the white paper needs that separation.
- Record **negative results and dead ends**; they are findings, not failures.
- Link claims to artifacts (`RUN_MANIFEST.json`, `results.csv`, commit SHAs) so every
  statement is traceable.

---

## White-paper crosswalk

Where each journal theme is expected to land in the final paper:

| Journal theme | Paper section |
|---|---|
| Hypotheses, conditions, ablations, frozen variables | Methods — Design |
| Metric definitions, judge protocol, null baseline | Methods — Measurement |
| Provenance, seeds, model snapshots, reproducibility | Methods — Reproducibility |
| Per-run results, CIs, trend tests, influence matrices | Results |
| Confounds, validity threats, scope limits | Limitations / Threats to Validity |
| Rejected designs, simplifications, cost trade-offs | Appendix — Design rationale |

---

## Entry Log

Newest first.

| Date | Entry | Theme |
|---|---|---|
| 2026-06-04 | [[2026-06-04 — Pre-Run Rigor Pass & P0 Controls]] | Rigor review verdict; pre-run controls landed |

---

## Related

- [[00 — Index]] — Experiment documentation root
- [[Experiment Roadmap]] — Phased run plan and stopping criteria
- [[Risks & Confounds]] — Known limitations this program is de-risking
- [[Future Work]] — Aspirations beyond the immediate roadmap
