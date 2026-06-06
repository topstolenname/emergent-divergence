---
title: 2026-06-04 — alpha02 First Run & Memory-Read Gap
created: 2026-06-04
project: emergent-divergence
tags:
  - journal
  - entry
  - pilot
  - results
  - instrumentation
  - memory
run_id: alpha02
banner: https://iprsoftwaremedia.com/219/files/202605/154ea89a7177c7d568f2f4916c7fd53a/nvidia-rtx-spark.png
banner_y: "52.5"
---

# 2026-06-04 — alpha02 First Run & Memory-Read Gap

> First real cell off the bench (`ollama / A / seed42`). Read the pilot honestly,
> corrected three over-reads of the numbers, and closed an instrumentation gap that
> had left memory's effect unauditable — landed as PR #8.

## Context

The pre-run rigor pass ([[2026-06-04 — Pre-Run Rigor Pass & P0 Controls]]) ended with the
design judged sound-as-pilot, not-yet-confirmatory. This session was the first time the
matrix actually produced data. Two deviations from the planned matrix, both forced and both
recorded for honesty:

- **Paid arm skipped.** The Claude arm had no budget (≈$0.01 on the API console; the Max
  subscription is a *separate wallet* that can't drive the SDK pipeline). So only the free
  local arm ran.
- **Backend substituted.** The configured `llama3.2:3b` wasn't pulled locally; ran
  `phi3.5:3.8b` instead (a one-line `configs/pipeline.yaml` change, kept **local** — not in
  the repo). So `alpha02` is a small-model pilot, not the matrix's intended Ollama backend.

## What changed

**Run.** `alpha02` = `ollama / A / seed42`, `phi3.5:3.8b`, 50/50 rounds, 480 calls, **$0.00**.
Embedder ran as real MiniLM (`preflight.embedder.backend == minilm`), so the semantic metrics
are genuinely semantic, not the lexical-hashing fallback.

**Code — PR #8 (`claude/memory-read-instrumentation`, commit `8930f8f`).** A missing
measurement, no design change:

- `agents/agent.py` — `respond()` returns the recalled entries (`recalled_memories`), counted
  only when memory was actually injected (skips probe turns with a pinned `system_override`).
- `orchestration/runner.py` — `_run_round` emits a `memory_read` event per deliberation turn:
  `count`, `memory_size`, and a compact `(round_id, source, 80-char preview)` per recalled
  entry. Full text already lives in the paired `memory_write`, so reads stay joinable without
  log bloat.
- `metrics/divergence.py` — `compute_memory_stats` reads from `memory_read` events, falling
  back to the legacy inline `agent_message.memory_reads` for old logs.

## Results & evidence

From `data/reports/alpha02/` (`statistics.json`, `RESULTS_SUMMARY.md`). **n = 1** — pilot, not
inference.

| Hypothesis | Verdict (shown) | Numbers |
|---|---|---|
| **H1** linguistic divergence ↑ over rounds | **Not supported — flat** | ρ = −0.143, **p = 0.378**, n = 40; abs `mean_jsd` = 0.256 |
| **H3** semantic divergence ↑ over rounds | **Suggestive, sub-significant** | ρ = 0.260, **p = 0.069**; early cosine 0.283 → late 0.318 |
| **H-I2** influence concentrates into a hub | **Near-egalitarian (true negative)** | Gini 0.048 (sem) / 0.009 (tok); hub `agent_2` net +0.113, `agent_0` net −0.152 |

Three corrections to the first-pass read of these numbers (all are *the same error* —
treating a non-significant coefficient as a real effect):

1. **H1 is flat, not "homogenizing."** p = 0.378 means the sign of ρ is noise; "agents
   regress toward a mean style" claims a downward trend the data doesn't license. What *is*
   shown: absolute `mean_jsd` = 0.256 — agents are linguistically **distinct from round one,
   they just don't widen**.
2. **The real signal is the dissociation.** Linguistically flat (H1) while semantically
   drifting (H3, 0.283 → 0.318) = *same words, slowly diverging conceptual space*. Genuinely
   interesting — but H3's p = 0.069 is **also not significant**, and rounds are autocorrelated
   so even that nominal p is optimistic. "A hint at n=1," nothing stronger.
3. **H-I2 found near-equality, the opposite of "domination."** Gini ≈ 0 = influence spread
   evenly; "an agent dominates the swarm" would be Gini ≈ 1. The `hub_row_sum` 1.105/0.545 is
   just "largest of three in a ring," which the Gini correctly flags as **not** meaningful. So
   the framework scored a **true negative** (no hub where there is none) — a real win, but the
   inverse of "proves it detects domination." `agent_0` (the proposer, first-speaker 49/49) is
   a mild net *receiver*, not a leader.

**Memory instrumentation.** `alpha02` showed `total_reads: 0` against `total_writes: 100`/agent.
Traced to a **logging gap**, not inert memory: `memory_size` grows 1→100/agent and the read
path is wired (`agent.py` injects "Your notes from prior rounds:"), but the runner evented
writes and not reads. After PR #8, offline stub verification shows condition-A reads growing
0→5 with nonzero `total_reads`; condition B (memory off) stays 0 via the fallback. `ruff` clean,
**141 tests pass**.

## Decisions & rationale

- **Decided:** instrument reads *before* trusting any H4 (A-vs-B) verdict — memory's causal
  effect was unverifiable from artifacts (reads unevented, system prompt unlogged). A vs B
  could have differed for reasons nothing in the logs could trace.
- **Decided:** log a `(round_id, source, 80-char preview)` per recalled entry, not full text —
  the full content already lives in the paired `memory_write`; joining recovers it. Auditable,
  not bloated.
- **Decided:** ship as a PR on a `claude/*` branch (the repo's established CI-gated workflow),
  not a push to `main`.
- **Rejected:** reading `total_reads` from the inline `agent_message` field as the primary
  source — kept only as a backward-compat fallback so old logs (`alpha02`) still parse.
- **Noted (negative result):** `alpha02`'s own report **cannot** be retro-fixed — its
  `events.jsonl` never recorded reads. Only runs *after* PR #8 get real read counts.

## Risks / confounds surfaced

1. **n = 1, and both trends are sub-significant** (H1 p = 0.378, H3 p = 0.069). No claim of
   "increase" or "decrease" survives this single cell.
2. **Round autocorrelation** violates the Spearman independence assumption → nominal p-values
   are optimistic even before multiplicity.
3. **Backend is `phi3.5:3.8b`**, a small local model and *not* the matrix's intended
   `llama3.2:3b` / Claude arm — generalization is unestablished, and the config swap lives only
   locally.
4. **Memory was active but its *effect* is still unmeasured** — PR #8 makes reads visible, but
   demonstrating that recall *changed a token* needs the A-vs-B contrast (next).

## Next

- [ ] **Run B and C on Ollama, seed 42** (`--conditions A B C --seeds 42` resumes the done A
      cell) now that reads are instrumented → H4 / H5 / H-I1 get auditable data instead of
      "Insufficient."
- [ ] Merge **PR #8** once CI is green.
- [ ] Scale seeds 43–45; reserve the paid Claude arm for when there's budget + a pinned dated
      snapshot.
- [ ] In write-up, present `alpha02` as a *pilot with effect sizes*, and lead the semantic
      story with the **linguistic-flat / semantic-drifting dissociation**, not a divergence
      "verdict."

---

## Related

- [[00 — Journal Index]]
- [[2026-06-04 — Pre-Run Rigor Pass & P0 Controls]] — the pre-run controls this run exercised
- [[emergent-divergence|Experiment Canvas]]
- PR #8 — https://github.com/topstolenname/emergent-divergence/pull/8
