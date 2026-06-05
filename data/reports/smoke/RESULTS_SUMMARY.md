# Results summary — run `smoke`

Generated 2026-06-05T01:48:36.560753+00:00

## Cells

- Total cells: 3
- done: 3
- Spend: $0.0000 / $50.00 cap (144 calls)

## Hypothesis verdicts

### Backend: `stub` (3 cells)

| Hypothesis | Verdict | Statement |
| --- | --- | --- |
| H1 | Insufficient data | Linguistic divergence increases over rounds (Spearman ρ on pairwise JSD). |
| H2 | Mixed | Agents specialize behaviorally by role. |
| H3 | Insufficient data | Semantic divergence increases over rounds (Spearman ρ on MiniLM cosine). |
| H4 | Mixed | Memory amplifies divergence (condition A > condition B). |
| H5 | Insufficient data | Divergence occurs even without role priors (condition C). |
| H-I1 | Not supported | Memory amplifies cross-agent influence (A > B). |
| H-I2 | Supported | Influence concentrates into a hub (Gini of outgoing influence). |
| H-I3 | Insufficient data | Influence precedes divergence (lagged correlation, lag ≥ 1). |

## Integrity

- OK: True
- expected: 3
- attempted: 3
- done: 3
- skipped_due_to_cap: 0
- skipped_unavailable: 0
- failed: 0
- analyzable: 3

> Influence-delta measures **influence, not manipulation** (see report Limitations).
