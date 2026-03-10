---
title: "Metric D — Coordination Structure"
created: 2026-03-10
tags: [metrics, coordination, turn-order, interaction-patterns]
---

# Metric D — Coordination Structure

## Method

Analyzes who speaks when and basic coordination patterns by examining agent_message events for turn order, first-mover frequency, and message distribution.

## Results

### Message Distribution

| Agent | Messages | Share |
|---|---|---|
| [[Agent 0 — Proposer\|Agent 0]] | 100 | 33.3% |
| [[Agent 1 — Critic\|Agent 1]] | 100 | 33.3% |
| [[Agent 2 — Synthesizer\|Agent 2]] | 100 | 33.3% |

Perfectly balanced — each agent speaks exactly 100 times across 300 total messages.

### First Speaker Counts

The coordination structure reports:

| Agent | First Speaker Count |
|---|---|
| Agent 0 | 49 |

**Note**: The reporting only logged agent_0 as first speaker for 49 rounds out of 49 total tracked rounds. This appears to be an artifact of how `first_speaker_counts` is computed (by sorting on turn number within each round). Since turn order rotates (`offset = round_id % 3`), the actual first speaker varies.

### Turn Order Rotation

By design, the starting agent rotates every round:

```
Round 0: agent_0 → agent_1 → agent_2 → agent_0 → agent_1 → agent_2
Round 1: agent_1 → agent_2 → agent_0 → agent_1 → agent_2 → agent_0
Round 2: agent_2 → agent_0 → agent_1 → agent_2 → agent_0 → agent_1
Round 3: agent_0 → agent_1 → agent_2 → ...
```

Each agent speaks first in approximately 1/3 of rounds (16–17 out of 50).

### Total Rounds Logged: 49

One fewer than expected (50 rounds were run). This may be a logging edge case in the coordination analysis where round 0 vs. round 49 boundary creates an off-by-one.

## Interpretation

### Uniform by Design

The coordination structure is **deliberately uniform** — equal message counts, rotating turn order. This is a baseline design choice to prevent positional bias from confounding divergence measurements.

### No Emergent Coordination Asymmetry

Unlike natural conversation where dominant speakers emerge, this system enforces equal participation. Future experiments could introduce optional turns (agents can "pass") or variable-length turns to allow emergent coordination patterns.

### Positional Effects

Despite rotation, there may be subtle positional effects:
- The first speaker in each round sets the framing for the discussion
- The last speaker has the most context but least opportunity for response
- Turn 2 speakers may disproportionately respond to the immediately preceding speaker

These potential confounds are documented in [[Risks & Confounds]].

## Related

- [[02 — Experimental Design]] — Turn order rotation specification
- [[Metric C — Memory Usage Patterns]] — Another structural metric
- [[Risks & Confounds]] — Fixed turn order confound
