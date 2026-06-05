# Results summary — run `alpha02`

Generated 2026-06-05T02:56:44.676761+00:00

## Cells

- Total cells: 1
- done: 1
- Spend: $0.0000 / $5.00 cap (480 calls)

## Hypothesis verdicts

### Backend: `ollama` (1 cells)

| Hypothesis | Verdict | Statement |
| --- | --- | --- |
| H1 | Not supported | Linguistic divergence increases over rounds (Spearman ρ on pairwise JSD). |
| H2 | Mixed | Agents specialize behaviorally by role. |
| H3 | Mixed | Semantic divergence increases over rounds (Spearman ρ on MiniLM cosine). |
| H4 | Insufficient data | Memory amplifies divergence (condition A > condition B). |
| H5 | Insufficient data | Divergence occurs even without role priors (condition C). |
| H-I1 | Insufficient data | Memory amplifies cross-agent influence (A > B). |
| H-I2 | Mixed | Influence concentrates into a hub (Gini of outgoing influence). |
| H-I3 | Not supported | Influence precedes divergence (lagged correlation, lag ≥ 1). |

## Integrity

- OK: True
- expected: 1
- attempted: 1
- done: 1
- skipped_due_to_cap: 0
- skipped_unavailable: 0
- failed: 0
- analyzable: 1

> Influence-delta measures **influence, not manipulation** (see report Limitations).
