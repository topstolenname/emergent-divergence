# ASSESSMENT — emergent-divergence v2 (Phase 0)

Inspection of the prior repo (`topstolenname/emergent-divergence`, imported here from
the `emergent-divergence-main` snapshot) and the per-module refactor/rebuild decision
for the v2 dual-backend, one-button pipeline. This is the first commit.

## Environment reality (drives several decisions)

The build/host machine has constraints that shape the robustness strategy:

- **Python 3.14.4** is the system interpreter, with **no `pip`** and a broken
  `ensurepip` (so `python -m venv` cannot bootstrap pip on its own).
- **`uv` 0.9.22** *is* installed and PyPI is reachable. `uv venv --python 3.12`
  + `uv pip install` works and is fast (verified: numpy 2.4.6, scipy 1.17.1).
- Python 3.14 lacks wheels for parts of the heavy ML stack (notably `torch`, which
  `sentence-transformers` needs). A pinned **3.12** venv has broad wheel coverage.
- **Ollama is not installed** on this machine and **no `ANTHROPIC_API_KEY`** is set.

**Decisions taken in response (the "most robust default" the brief authorises):**

1. `run_all.sh` **prefers `uv`** (creating a Python 3.12 venv) and falls back to
   `python -m venv` + pip only if `uv` is absent. Clear messaging either way.
2. **Every heavy dependency is optional with a deterministic fallback** so the
   pipeline always reaches a complete report, even fully offline:
   - **Embeddings**: `sentence-transformers` MiniLM (`all-MiniLM-L6-v2`) is the
     default and primary. If it cannot be imported/loaded, the `Embedder` falls
     back to a deterministic hashing embedding (384-d, L2-normalised). The active
     embedder is recorded in `RUN_MANIFEST.json` and disclosed in the report. This
     keeps cross-backend numbers comparable *within a run* and guarantees the
     offline path; the fallback's limitations are stated in the report.
   - **Figures**: `matplotlib` if available, else figure generation is skipped with
     a recorded note (report still builds; HTML still self-contained).
   - **PDF**: `weasyprint` → `pandoc` → skipped. Never fails the run.
3. The end-to-end `--smoke` path uses the offline `StubProvider` + (typically) the
   fallback embedder, so it runs with only `numpy`, `scipy`, `pyyaml` present.

## Disposition of prior repo

Prior pilot data **preserved, not deleted**: the two prior runs in
`data/raw_logs/` (`run_20260310_161255_db9f7b49` — the seed‑42 memory‑enabled
pilot — and `run_20260405_052657_2879ed7a`) were moved to
`data/archive/pilot_2026-03/`. `data/reports/pilot_analysis_report.md` is kept.
The v2 report may reference these as historical context.

## Per-module decision

| Module | Decision | Rationale |
|---|---|---|
| `memory/store.py` | **Keep as-is** | Clean JSONL-backed key-value store with `clear()` for the no-memory condition. Exactly what v2 needs. |
| `tasks/generator.py` | **Keep** | Seeded, deterministic claim-bank cycling; 20 debatable claims. Fit for purpose. |
| `logging_/events.py` | **Keep** | Solid structured JSONL logger (`ExperimentEvent`, `ExperimentLogger`, `generate_run_id`). v2 adds `influence_delta` event types on top — no change needed to the logger. |
| `metrics/divergence.py` | **Keep + extend** | JSD, behavioral profiles/specialization, lexical uniqueness, memory stats, Spearman temporal correlation, `compare_conditions` all port directly. v2 consumes these per cell. |
| `metrics/semantic_divergence.py` | **Refactor** | Embedding + cosine logic is good but instantiates MiniLM inline. Refactor to use the new shared `Embedder` component (single source of embeddings, swappable, fallback-aware). Plotting kept. |
| `agents/agent.py` | **Refactor** | Good "LLM is the sole driver" design and `ROLE_BIASES` (incl. `generic` for Condition C). But it is **async** and returns bare strings via `LLMBackend.complete`. v2 standardises on the **sync `ModelProvider.generate -> Generation`** interface (per brief §4.1) for clean token/cost accounting and ablation replay. `MockLLMBackend` concept is reborn as `StubProvider`. |
| `orchestration/runner.py` | **Rebuild** | Async, single-backend, no checkpoint/resume, no cost governance, no influence ablation hook. v2 needs sync providers, per-cell checkpoint/resume, retries, and the `rerun_target_with_ablation` counterfactual hook. The round/rotation/memory-write logic is preserved in spirit. |
| `cli/runner.py` | **Refactor** | Keep `run`/`analyze`/`compare` ergonomics; add `pipeline` (the matrix driver) and `--smoke`. |
| `evaluation/judge.py` | **Keep (placeholder)** | Out of scope for v2 metrics; left intact. |
| `scripts/generate_figures.py` | **Superseded** | Figure generation moves into `report/figures.py` driven by the pipeline; the standalone script is retained for ad-hoc use. |
| `configs/*.yaml` | **Superseded by `configs/pipeline.yaml`** | The single pipeline config (Appendix B) drives the whole 2×3×4 matrix. Old per-condition YAMLs kept for reference/manual single runs. |
| `docs/` (vault etc.) | **Keep** | Useful research context; harmless. |

## New components built for v2

- `providers/` — `base.py` (`Generation`, `ModelProvider` Protocol), `ollama.py`
  (`llama3.2:3b` via local HTTP), `claude.py` (Sonnet via Anthropic SDK with
  `usage` capture), `stub.py` (deterministic offline provider with built-in
  hub structure so influence matrices are non-degenerate in smoke).
- `embeddings/embedder.py` — shared MiniLM embedder with deterministic fallback.
- `metrics/influence_delta.py` — Appendix A: `id_sem`, `id_tok` (JSD), influence
  matrix `M`, asymmetry `A = M − Mᵀ`, concentration `Gini(row_sums)`.
- `metrics/statistics.py` — bootstrap CIs, Spearman trends, A-vs-B contrasts
  (effect size + CI), per-hypothesis verdict assembly, cross-backend comparison.
- `cost/governor.py` — live token-based spend tracking and the $50 hard cap.
- `orchestration/pipeline.py` — the matrix driver: preflight, test gate,
  cost pre-estimate/auto-reduce, checkpointed/resumable cell execution, integrity
  check, then metrics → stats → figures → report.
- `report/` — `builder.py` (REPORT.md/HTML/PDF, results.csv/json, RUN_MANIFEST.json,
  RESULTS_SUMMARY.md) and `figures.py`.
- `run_all.sh` — the one button (thin wrapper around `python -m emergent_divergence pipeline`).

## Honesty / scope constraints carried into the report

- The influence-delta metric measures **influence**, not **manipulation**; the
  good-counsel vs. manipulation distinction is deliberately out of scope and the
  report's Limitations says so explicitly (never silently relabelled).
- Claude exposes no per-token vocabulary distribution → semantic influence-delta
  is the primary cross-backend metric; token-JSD on Claude is Monte-Carlo
  empirical, stated in Methods.
- API nondeterminism (Claude ignores `seed`) is averaged over seeds with CIs and
  documented; `llama3.2:3b` is small and may yield weaker/noisier effects — noted
  in Limitations rather than over-read.

## Risks

- **3.14 host**: if an operator runs on a Python with no compatible heavy-stack
  wheels and `uv` is absent, the full MiniLM/matplotlib path degrades to fallbacks.
  Mitigated by `uv`-first setup and graceful degradation; disclosed in the manifest.
- **Influence-delta is the cost driver**: round-subsampling (`every_n_rounds`),
  small `k_samples`, and the `max_tokens` cap keep the paid arm bounded; the cost
  governor is the hard backstop.
- **Sonnet model string** (`claude-sonnet-4-6`) and prices are pinned in config and
  must be verified against current Anthropic listings before a paid run.
