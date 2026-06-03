# Emergent Behavioral Divergence in Coordinated Multi-Agent Systems

**An empirical experiment: do multiple instances of the *same* base LLM, coordinating over many rounds, develop measurable behavioral divergence — and does cross-agent influence drive it?**

## Quickstart

```bash
cp .env.example .env          # optional: add ANTHROPIC_API_KEY for the paid arm
./run_all.sh --smoke          # free, offline, <1 min — proves the whole pipeline
./run_all.sh                  # full matrix; writes the complete report package
```

`run_all.sh` creates the virtualenv, installs dependencies on first run, runs the
test gate, executes the matrix, computes metrics, and leaves a self-contained
report under `data/reports/<run_id>/`. It is resumable: `Ctrl-C` and re-run with
`--run-id <id>` to continue without losing work or double-counting spend.

## What it measures

Three instances of one base model take fixed roles — **Proposer**, **Critic**,
**Synthesizer** — and deliberate over `T=50` rounds of multi-turn claim analysis.
We measure how their behavior diverges and how much each agent moves the others.

**Backends (run side by side):**
- `ollama` — `llama3.2:3b`, local and free
- `claude` — `claude-sonnet-4-6`, frontier API, paid (governed by a $50 cap)
- `stub`   — deterministic offline provider for `--smoke` and tests

**Conditions:**
- **A** — persistent memory + weak role priors
- **B** — memory disabled (context reset each round) + weak priors
- **C** — persistent memory + zero priors (generic identical agents)

**Matrix:** 2 backends × 3 conditions × 4 seeds `[42, 43, 44, 45]` = **24 cells**.
Hypotheses are reported **per backend** so the small local model and the frontier
model are never pooled.

## Hypotheses

| ID | Statement | Test |
|----|-----------|------|
| H1 | Linguistic divergence increases over time | Spearman ρ on pairwise token-JSD |
| H2 | Behavioral role specialization emerges | role-profile divergence score |
| H3 | Semantic divergence increases over time | MiniLM cosine distance, ρ over rounds |
| H4 | Memory amplifies divergence (A > B) | cross-condition effect size |
| H5 | Divergence emerges without role priors (C) | divergence under generic agents |
| H-I1 | Memory amplifies influence (A > B) | influence-delta, A vs B |
| H-I2 | Influence concentrates on a hub | Gini of the influence matrix |
| H-I3 | Influence precedes divergence | lagged correlation |

> **Honesty constraint:** the influence-delta metric measures **influence, not
> manipulation**. It is never silently relabeled; the report's Limitations section
> states this explicitly.

## Report package

Every run writes to `data/reports/<run_id>/`:

| File | Contents |
|------|----------|
| `results.csv` / `results.json` | one row per cell: metrics + run provenance |
| `statistics.json` | cross-cell statistics and per-backend hypothesis verdicts |
| `RESULTS_SUMMARY.md` | human-readable verdict tables + integrity summary |
| `RUN_MANIFEST.json` | config, preflight, test gate, cost estimate vs actual, integrity |
| `cell_reports.json` | rich per-cell appendix material |

## Configuration

One file is the source of truth: [`configs/pipeline.yaml`](configs/pipeline.yaml).
Precedence (low → high): packaged defaults → `pipeline.yaml` → environment
(`ROUNDS`, `SEEDS`, `COST_CAP_USD`, `INFLUENCE_EVERY_N`, `K_SAMPLES`) → CLI flags →
`--smoke` clamps. See [`.env.example`](.env.example) for the env knobs.

```bash
./run_all.sh --backends ollama          # free local arm only
./run_all.sh --cap-usd 5                 # tighter budget; matrix auto-reduces to fit
./run_all.sh --conditions A B --seeds 42 # a focused slice
```

## Cost governance

Free backends cost $0. The Claude arm is metered against a hard `$50` cap. Before
any paid generation the pipeline (1) runs the test gate — failing tests **STOP**
the run when a paid backend is enabled — and (2) estimates spend, auto-reducing
the matrix (seeds first, then rounds) until it fits the cap. Actual spend is
checkpointed to `cost_snapshot.json` so resumed runs never double-count.

## Commands

```bash
python -m emergent_divergence pipeline [--smoke] [--run-id ID] [flags]   # the matrix
python -m emergent_divergence run --backend stub --condition A --seed 42 # one cell
python -m emergent_divergence analyze --run-dir <dir> [--semantic]       # re-analyze
python -m emergent_divergence compare --runs <dirA> <dirB>               # two runs
```

## Development

```bash
pip install -e ".[dev]"
pytest -q          # full unit + integration suite
ruff check src tests
```

CI (`.github/workflows/ci.yml`) runs lint, the test suite, and an offline
`--smoke` run on Python 3.10 and 3.12, then asserts the report artifacts exist.

## Non-goals

This experiment does **not** test consciousness, selfhood, or AGI. It tests narrow,
falsifiable claims about behavioral divergence and cross-agent influence.

## License

MIT
