# Pre-Control Gap Closure — Design Spec

**Date**: 2026-03-10
**Status**: Approved
**Scope**: Close infrastructure gaps before executing P1-02 (no-memory control run)

---

## 1. Design Summary

Close the gaps identified in the pilot run infrastructure before executing P1-02. All changes are additive — no refactors, no log schema breaks, no new experimental conditions.

### Analysis-side only changes
- **LLM-judge classifier module** — Configurable LLM-based 6-category message classifier, parallel to keyword classifier. Default: Haiku (low-cost). Judge is blind to agent identity, role bias, condition, and model.
- **`--classifier` flag on `analyze`** — Select keyword, llm_judge, or both
- **Streamlit dashboard v1** — Read-only metrics explorer with run comparison

### Runner/runtime changes
- **`--seed` CLI override** with YAML fallback
- **`metadata.json` generation** at run start, including git and environment provenance
- **Full RNG propagation** — seed `random`, `numpy`, and task generator consistently
- **Run directory naming** — include condition, seed, and short unique suffix
- **System prompt logging** — optional, enabled via `--log-system-prompts` flag

### Dashboard additions
- Run selector, JSD-over-time plots, behavioral profile charts, summary comparison table with deltas, condition comparison overlay view

---

## 2. Patch Plan

### 2.1 `--seed` CLI override with YAML fallback

| | |
|---|---|
| **File(s)** | `src/emergent_divergence/cli/runner.py` |
| **Purpose** | Add `--seed INT` optional flag to `run` command. If provided, overrides `seed` in YAML config. |
| **Affects** | Runner behavior (seed selection). Does NOT affect log format. |
| **Size/Risk** | ~15 lines. Low risk — additive flag, existing behavior unchanged when flag is absent. |

### 2.2 `metadata.json` generation

| | |
|---|---|
| **File(s)** | `src/emergent_divergence/orchestration/runner.py`, `src/emergent_divergence/logging_/events.py` |
| **Purpose** | Write `metadata.json` to run directory at experiment start. Records config provenance, seed provenance, git state, Python version, and all config params. |
| **Affects** | Adds a new file to run output. Does NOT change `events.jsonl` format. |
| **Size/Risk** | ~50 lines. Very low risk — purely additive output file. |

### 2.3 Full RNG propagation

| | |
|---|---|
| **File(s)** | `src/emergent_divergence/orchestration/runner.py` |
| **Purpose** | At experiment start, seed `random.seed(seed)`, `numpy.random.seed(seed)`, and pass seed to TaskGenerator (already done). Consolidate in one location. |
| **Affects** | Runner behavior (determinism of local components). Does NOT affect log format. |
| **Size/Risk** | ~5 lines. Low risk — makes existing behavior more robust. |

### 2.4 Run directory naming

| | |
|---|---|
| **File(s)** | `src/emergent_divergence/logging_/events.py` |
| **Purpose** | Change run directory from `run_{timestamp}_{uuid}` to `run_{timestamp}_seed{seed}_{condition}_{shortid}`. The `{shortid}` is the first 6 hex chars of a UUID, preventing collisions when multiple runs share timestamp+seed+condition. Example: `run_20260311_143000_seed43_memory_enabled_a3f1b2` |
| **Affects** | Run directory name format. Does NOT affect log contents or event schema. |
| **Size/Risk** | ~10 lines. Low risk — old runs with old names still load fine (analyze/compare use the directory path, not the name pattern). |

### 2.5 System prompt logging (optional)

| | |
|---|---|
| **File(s)** | `src/emergent_divergence/cli/runner.py`, `src/emergent_divergence/orchestration/runner.py`, `src/emergent_divergence/agents/agent.py` |
| **Purpose** | When `--log-system-prompts` is passed, log each agent's constructed system prompt as a `system_prompt` event. One event per agent per turn. Whether this was enabled is recorded in `metadata.json`. |
| **Affects** | Appends new event type to `events.jsonl` when enabled. Does NOT modify existing event types. Old analysis code ignores unknown event types. |
| **Size/Risk** | ~25 lines. Low risk — additive event, opt-in only, no existing code reads this event type. |

### 2.6 `--classifier` flag for `analyze`

| | |
|---|---|
| **File(s)** | `src/emergent_divergence/cli/runner.py`, `src/emergent_divergence/metrics/divergence.py` |
| **Purpose** | Add `--classifier {keyword,llm_judge,both}` flag to `analyze` command. Default: `keyword` (preserves current behavior). Routes to appropriate classifier in `generate_analysis_report()`. |
| **Affects** | Analysis only. Does NOT affect runner or log format. |
| **Size/Risk** | ~25 lines in CLI, ~15 lines plumbing in metrics. Low risk. |

### 2.7 LLM-judge classifier module

| | |
|---|---|
| **File(s)** | `src/emergent_divergence/metrics/llm_judge.py` (NEW), `src/emergent_divergence/metrics/divergence.py` |
| **Purpose** | New module implementing LLM-based 6-category message classification. Fixed schema: proposal, critique, synthesis, verification, recall, clarification. Configurable backend/model with low-cost default (Haiku). Judge is blind to agent ID, role bias, condition, run label, and model. Returns per-category confidence scores (0.0-1.0). Stores results alongside keyword results in analysis report. Includes agreement computation with Spearman rank correlation. The `--judge-model` flag on the `analyze` command selects the judge model (default: `claude-haiku-4-5-20251001`). |
| **Affects** | Analysis only. Does NOT affect runner or log format. |
| **Size/Risk** | ~180 lines new module, ~40 lines integration. Medium size, low risk — entirely additive, isolated module. |

Note: The `--judge-model` flag is implemented in `cli/runner.py` alongside `--classifier` (patch 2.6) and passed through to `llm_judge.classify_run()`. It is not a separate patch — it is part of the LLM-judge integration surface.

### 2.8 Streamlit dashboard v1

| | |
|---|---|
| **File(s)** | `dashboard/app.py` (NEW), `dashboard/components/` (NEW directory) |
| **Purpose** | Read-only Streamlit app. Primary data source: `analysis_report.json`. Secondary: `metadata.json`. Loads `events.jsonl` only when needed (e.g., future transcript view). Provides run selection, JSD plots, behavioral charts, comparison tables. |
| **Affects** | Analysis/visualization only. Does NOT affect runner, log format, or any existing code. |
| **Size/Risk** | ~400 lines total. Low risk — completely standalone, reads existing data. |

---

## 3. Backward Compatibility

### Changes that do NOT alter existing log format
- `--seed` CLI flag — changes how seed is selected, not what's logged
- `metadata.json` — new file alongside existing `events.jsonl`, not a modification
- RNG propagation — internal runner change, no log impact
- Run directory naming — directory name changes, log contents unchanged
- `--classifier` flag — analysis-side only
- LLM-judge module — analysis-side only
- Streamlit dashboard — reads existing data

### Changes that append new data safely
- **System prompt logging** (when enabled) — adds new `system_prompt` event type to `events.jsonl`. Existing analysis code in `generate_analysis_report()` filters events by known types (`round_start`, `agent_message`, `memory_write`, `round_end`). Unknown event types are ignored. Safe append.

### Old runs analyzed unchanged
**Yes.** All analysis changes are backward-compatible:
- `analyze --classifier keyword` on an old run produces identical output to current behavior
- `analyze --classifier llm_judge` on an old run works — it reads `agent_message` events from `events.jsonl`, which are unchanged
- `analyze --classifier both` produces both outputs side by side
- Dashboard loads any run directory containing `events.jsonl` and optionally `analysis_report.json`
- `compare` works on any two run directories regardless of when they were generated
- Absence of `metadata.json` is handled gracefully (dashboard shows "metadata not available")

---

## 4. Data Model

### 4.1 `metadata.json` schema

```json
{
  "run_id": "run_20260311_143000_seed43_memory_enabled_a3f1b2",
  "config_file": "configs/memory_enabled.yaml",
  "seed_yaml": 42,
  "seed_cli_override": 43,
  "seed_effective": 43,
  "timestamp": "2026-03-11T14:30:00",
  "condition": "memory_enabled",
  "model": "claude-sonnet-4-20250514",
  "temperature": 1.0,
  "max_tokens": 1024,
  "num_agents": 3,
  "num_rounds": 50,
  "turns_per_round": 2,
  "memory_enabled": true,
  "memory_max_entries": 200,
  "role_biases": ["proposer", "critic", "synthesizer"],
  "backend": "anthropic",
  "log_system_prompts": false,
  "git_commit": "a3f1b2c",
  "git_dirty": true,
  "python_version": "3.11.8"
}
```

Field notes:
- `seed_cli_override` is `null` when no CLI override was used
- `seed_yaml` is `null` if the YAML config has no `seed` key. In this case, `seed_cli_override` MUST be provided or the run exits with an error: "No seed specified. Provide --seed or set seed in config YAML."
- `seed_effective` always reflects the seed that was actually used. It is never null — if neither YAML nor CLI provides a seed, the run fails before start.
- `git_commit` is the short SHA of HEAD at run time; `null` if not a git repo
- `git_dirty` is `true` if there are uncommitted changes; `null` if not a git repo
- `log_system_prompts` records whether `--log-system-prompts` was passed

### 4.2 System prompt event schema (logged only when `--log-system-prompts` is enabled)

```json
{
  "event_type": "system_prompt",
  "run_id": "run_20260311_143000_seed43_memory_enabled_a3f1b2",
  "timestamp": 1773260000.123,
  "round_id": 5,
  "agent_id": "agent_0",
  "agent_role_bias": "proposer",
  "condition": "memory_enabled",
  "data": {
    "turn": 0,
    "system_prompt_text": "You are participating in a collaborative analysis...\n\nYou tend to generate initial ideas...\n\nYour notes from prior rounds:\n  [Round 4] I proposed that...\n  [Round 3] My framework for...",
    "memory_entries_included": 2
  }
}
```

- Logged once per agent per turn, immediately before the LLM call
- `memory_entries_included` enables quick auditing without parsing prompt text

### 4.3 LLM-judge output schema (stored in analysis report)

```json
{
  "behavioral_specialization_llm_judge": {
    "classifications": {
      "agent_0": [
        {
          "round_id": 0,
          "turn": 0,
          "task_id": "task_0000_1af214",
          "scores": {
            "proposal": 0.85,
            "critique": 0.10,
            "synthesis": 0.15,
            "verification": 0.05,
            "recall": 0.00,
            "clarification": 0.10
          }
        }
      ]
    },
    "profiles": {
      "agent_0": {
        "proposal": 0.72,
        "critique": 0.12,
        "synthesis": 0.18,
        "verification": 0.08,
        "recall": 0.15,
        "clarification": 0.05
      }
    },
    "divergence_score": 0.1823,
    "judge_model": "claude-haiku-4-5-20251001",
    "total_classifications": 300,
    "classification_failures": 0
  }
}
```

### 4.4 Classifier agreement schema (stored in analysis report when `--classifier both`)

```json
{
  "classifier_agreement": {
    "top_1_match_rate": 0.68,
    "per_category_agreement": {
      "proposal": 0.82,
      "critique": 0.78,
      "synthesis": 0.51,
      "verification": 0.75,
      "recall": 0.69,
      "clarification": 0.64
    },
    "mean_spearman_rank_correlation": 0.61,
    "per_message_spearman": {
      "mean": 0.61,
      "std": 0.18,
      "min": -0.14,
      "max": 0.94
    },
    "disagreement_examples": [
      {
        "round_id": 7,
        "agent_id": "agent_2",
        "keyword_top": "critique",
        "llm_judge_top": "synthesis",
        "spearman": 0.03,
        "text_preview": "Building on both perspectives, I think..."
      }
    ]
  }
}
```

Agreement metrics:
- **top_1_match_rate**: fraction of messages where top-1 category matches between classifiers
- **per_category_agreement**: for each category, fraction of messages where both classifiers agree on whether that category scores above 0.3 (present/absent threshold)
- **mean_spearman_rank_correlation**: average Spearman rank correlation of the 6-category score vectors across all messages. Measures whether the two classifiers rank categories in the same order, even if absolute scores differ.
- **per_message_spearman**: distribution stats for per-message Spearman correlations
- **disagreement_examples**: up to 10 messages with lowest Spearman correlation, for manual inspection

---

## 5. CLI Design

### `run`

```bash
# Basic (uses YAML seed)
python -m emergent_divergence run --config configs/no_memory.yaml --rounds 50

# With seed override
python -m emergent_divergence run --config configs/memory_enabled.yaml --rounds 50 --seed 43

# With system prompt logging
python -m emergent_divergence run --config configs/memory_enabled.yaml --seed 43 --log-system-prompts

# With mock backend for testing
python -m emergent_divergence run --config configs/memory_enabled.yaml --rounds 5 --seed 43 --backend mock
```

### `analyze`

```bash
# Default: keyword classifier (backward-compatible)
python -m emergent_divergence analyze --run-dir data/raw_logs/run_20260311_143000_seed43_memory_enabled_a3f1b2

# LLM-judge only (configurable model)
python -m emergent_divergence analyze --run-dir <path> --classifier llm_judge
python -m emergent_divergence analyze --run-dir <path> --classifier llm_judge --judge-model claude-sonnet-4-20250514

# Both classifiers + agreement report
python -m emergent_divergence analyze --run-dir <path> --classifier both
```

### `compare`

```bash
# Compare two runs (unchanged syntax, uses whichever classifier data is in the reports)
python -m emergent_divergence compare \
  --runs data/raw_logs/run_20260310_161255_seed42_memory_enabled_db9f7b \
         data/raw_logs/run_20260311_143000_seed42_no_memory_c4e8a1
```

### Dashboard launch

```bash
# Launch Streamlit dashboard
streamlit run dashboard/app.py -- --data-dir data/raw_logs

# Or with explicit path
streamlit run dashboard/app.py -- --data-dir /path/to/raw_logs
```

---

## 6. LLM-Judge Design

### Relationship to keyword classifier

Parallel, independent module. Both classifiers produce the same output shape (per-message scores across 6 fixed categories). Neither replaces the other. Results are stored in separate keys in the analysis report (`behavioral_specialization` for keyword, `behavioral_specialization_llm_judge` for judge).

### Backend/model configuration

- **Default**: `claude-haiku-4-5-20251001` (low-cost, fast)
- **Override**: `--judge-model <model_id>` flag on `analyze`
- The model used is recorded in the analysis report under `judge_model`
- Uses the same `anthropic` SDK already in dependencies

### Judge blindness

The judge sees ONLY the message text. The following are never included in the judge prompt:
- Agent ID
- Role bias
- Condition label
- Run label
- Generating model name
- Round number or task metadata

This prevents the judge from inferring roles and biasing scores.

### Fixed category schema

| Category | Definition (used in judge prompt) |
|---|---|
| proposal | Generating ideas, suggesting solutions, introducing new framings |
| critique | Evaluating critically, identifying weaknesses, pushing for rigor |
| synthesis | Integrating perspectives, finding common ground, reconciling viewpoints |
| verification | Citing evidence, referencing data, demanding specifics |
| recall | Referencing prior rounds, memory, past discussions |
| clarification | Requesting definitions, asking for elaboration |

These definitions are **hardcoded constants**, not generated or inferred. The judge prompt includes them verbatim. The category set must not be modified without updating both classifiers simultaneously.

### Judge prompt

```
Classify this message from a multi-agent discussion.

Assign a confidence score (0.0 to 1.0) for each category.
Scores are independent — a message can score high on multiple categories.

Categories:
- proposal: generating ideas, suggesting solutions, introducing new framings
- critique: evaluating critically, identifying weaknesses, pushing for rigor
- synthesis: integrating perspectives, finding common ground, reconciling viewpoints
- verification: citing evidence, referencing data, demanding specifics
- recall: referencing prior rounds, memory, past discussions
- clarification: requesting definitions, asking for elaboration

Message:
"""
{message_text}
"""

Respond with ONLY a JSON object, no other text:
{"proposal": 0.0, "critique": 0.0, "synthesis": 0.0, "verification": 0.0, "recall": 0.0, "clarification": 0.0}
```

### Output schema (per message)

```python
{
    "proposal": float,       # 0.0-1.0
    "critique": float,
    "synthesis": float,
    "verification": float,
    "recall": float,
    "clarification": float
}
```

### Error handling

- Invalid JSON from judge: retry once with same prompt
- Second failure: log as classification failure, record `null` scores for that message
- Total failures recorded in `classification_failures` field
- If failures exceed 10% of messages, abort and report error

### Agreement computation

When `--classifier both` is used:

1. **top_1_match_rate**: fraction of messages where top-1 category matches between classifiers
2. **Per-category agreement**: for each category, fraction of messages where both classifiers agree on whether that category scores above 0.3 (present/absent threshold)
3. **Spearman rank correlation**: for each message, compute Spearman rank correlation between the two 6-element score vectors (keyword scores vs. judge scores). Report mean, std, min, max across all messages.
4. **Disagreement examples**: sample up to 10 messages with lowest Spearman correlation, for manual inspection

### Cost estimate

- 300 messages per run x ~200 tokens input + ~50 tokens output per classification
- Haiku pricing: ~$0.02 per full run analysis
- Sequential calls, no parallelism needed at this scale

---

## 7. Streamlit Dashboard Scope (v1)

### Architecture

```
dashboard/
├── app.py                  # Main Streamlit app, page routing
├── components/
│   ├── run_selector.py     # Run discovery and selection widget
│   ├── jsd_plots.py        # JSD-over-time visualizations
│   ├── behavioral.py       # Behavioral profile charts
│   ├── comparison.py       # Side-by-side condition comparison
│   └── data_loader.py      # Load analysis_report.json, metadata.json, events.jsonl
```

### Data loading strategy

1. **Primary**: `analysis_report.json` — all metric data lives here. Loaded first.
2. **Secondary**: `metadata.json` — run provenance, displayed in headers and selectors. Loaded if present, graceful fallback if absent.
3. **Lazy**: `events.jsonl` — loaded only when a feature requires raw event data (not needed for v1 metrics views). Architecture supports adding an events-based transcript tab later without changing the loader.

### Pages / Views

**1. Single Run View**
- **Run selector**: Dropdown listing all run directories in `--data-dir`. Displays condition and seed from `metadata.json` when available, otherwise directory name.
- **JSD-over-time plot**: Line chart with sliding window mean JSD and per-pair JSD traces (Plotly)
- **Behavioral profiles**: Grouped bar chart showing per-agent behavioral scores across 6 categories. If both classifier outputs exist in the report, toggle between keyword / LLM-judge / overlay.
- **Summary metrics table**: Mean JSD, behavioral divergence score, lexical uniqueness per agent, message counts, memory stats

**2. Comparison View**
- **Two-run selector**: Pick two runs from dropdown
- **JSD trajectory overlay**: Both runs' mean JSD over time on the same chart, color-coded by condition
- **Summary comparison table**:

| Metric | Run A (memory) | Run B (no-memory) | Delta |
|---|---|---|---|
| Mean JSD | 0.2935 | ? | ? |
| Behavioral divergence | 0.1544 | ? | ? |
| Lexical uniqueness spread | 0.024 | ? | ? |

- **Behavioral profile comparison**: Per-agent profiles from both runs, side by side

### What is NOT in v1
- No transcript viewer (but `data_loader.py` architecture supports adding it as a tab that lazy-loads `events.jsonl`)
- No LLM-judge triggering from the dashboard
- No run execution from the dashboard
- No editing or writing to data files

### Dependencies
- `streamlit>=1.30`
- `plotly>=5.18`
- `pandas>=2.0`

Added to `pyproject.toml` under `[project.optional-dependencies] dashboard`.

---

## 8. Implementation Order

### Must do before P1-02

These changes establish run provenance. Without them, multi-seed work risks confusion.

| Step | Change | Risk | Rationale |
|---|---|---|---|
| 1 | `metadata.json` generation | Very low | Additive output file, no log changes. Highest value — prevents provenance mistakes. |
| 2 | `--seed` CLI override | Low | Additive flag, default unchanged. Required for multi-seed runs. |
| 3 | Full RNG propagation | Low | ~5 lines, makes determinism robust. |
| 4 | Run directory naming (with short unique suffix) | Low | Changes directory name, nothing parses names. |
| 5 | Git/code provenance in metadata | Very low | Part of metadata.json, just reads git state. |

### Safe but non-blocking for P1-02

These are valuable but do not block the control run.

| Step | Change | Risk | Rationale |
|---|---|---|---|
| 6 | LLM-judge module | Very low | New file, no existing code touched. |
| 7 | `--classifier` flag on `analyze` | Very low | Additive flag, default `keyword` preserves behavior. |
| 8 | Streamlit dashboard | Very low | Completely standalone. |
| 9 | Optional system prompt logging | Low | Additive, opt-in. Useful before publication-facing runs. |

---

## 9. Acceptance Criteria

### `--seed` CLI override
- `--seed 43` with a YAML containing `seed: 42` produces `metadata.json` with `seed_yaml: 42, seed_cli_override: 43, seed_effective: 43`
- Omitting `--seed` produces `metadata.json` with `seed_cli_override: null, seed_effective: 42`
- Two runs with `--seed 43` produce identical task orderings (verified via `round_start` events showing same `task_id` and `claim` sequence)

### `metadata.json`
- File exists in run directory after any run completes
- Contains all fields from schema (section 4.1), including `git_commit`, `git_dirty`, `python_version`, `log_system_prompts`
- Dashboard displays metadata when available, shows graceful fallback for old runs without it
- `git_commit` and `git_dirty` are `null` when not in a git repo (not an error)

### RNG propagation
- `random.seed()` and `numpy.random.seed()` called with effective seed at experiment start
- Reproducibility means: identical task ordering and deterministic local components (claim sequence, turn rotation, memory operations)
- LLM completions are NOT expected to be identical across reruns (stochastic API responses)

### Run directory naming
- Directory follows pattern `run_{YYYYMMDD}_{HHMMSS}_seed{N}_{condition}_{shortid}`
- Example: `run_20260311_143000_seed43_memory_enabled_a3f1b2`
- `{shortid}` is first 6 hex chars of a UUID
- Old runs with old naming convention still load in `analyze`, `compare`, and dashboard

### System prompt logging
- Only logged when `--log-system-prompts` is passed
- `metadata.json` contains `"log_system_prompts": true` when enabled, `false` otherwise
- When enabled: `events.jsonl` contains `system_prompt` events, one per agent per turn
- When disabled: no `system_prompt` events in log (no bloat on routine runs)
- `analyze` command produces identical output regardless of whether prompt events are present

### `--classifier` flag
- `analyze --classifier keyword` produces identical output to current behavior (default)
- `analyze --classifier llm_judge` produces `behavioral_specialization_llm_judge` section in report
- `analyze --classifier both` produces both sections plus `classifier_agreement` section (including Spearman correlation)
- Old runs analyzed with `--classifier keyword` produce identical results

### LLM-judge classifier
- Classifies all `agent_message` events from a run
- Returns scores for exactly 6 categories per message (no more, no fewer)
- Scores are floats 0.0-1.0
- Judge prompt contains ONLY message text — no agent ID, role, condition, or model
- Invalid JSON responses retried once, then logged as classification failure
- `--judge-model` flag overrides default model; model used recorded in report
- Default model is Haiku
- Profiles and divergence score computed identically to keyword method (mean scores per agent, L2 pairwise distance)

### Classifier agreement (when `--classifier both`)
- `top_1_match_rate` is a float 0.0-1.0
- `per_category_agreement` has exactly 6 entries matching the fixed category set
- `mean_spearman_rank_correlation` is computed across all messages
- `per_message_spearman` includes mean, std, min, max
- `disagreement_examples` contains up to 10 entries, sorted by lowest Spearman

### Streamlit dashboard
- Launches with `streamlit run dashboard/app.py -- --data-dir data/raw_logs`
- Discovers and lists all run directories in data dir
- Loads `analysis_report.json` as primary source, `metadata.json` as secondary
- Does NOT load `events.jsonl` unless a feature explicitly requires it
- Single run view: displays JSD-over-time plot, behavioral profiles, summary table
- Comparison view: overlays two runs' JSD trajectories, shows delta table
- Handles runs with only keyword data, only LLM-judge data, or both
- Handles old runs without `metadata.json` gracefully
- Does not write to any data files

### Backward compatibility (global)
- The pilot run (`run_20260310_161255_db9f7b49`) analyzes successfully with all new code
- `analyze` with no `--classifier` flag behaves identically to current code
- `compare` on two old-format runs behaves identically to current code

---

## 10. Minimal Diff Strategy

### Principles
- **New files over modified files.** The LLM-judge is a new module (`llm_judge.py`), not changes to `divergence.py`. The dashboard is a new directory, not changes to existing code.
- **Additive flags with defaults.** `--classifier keyword` is the default. `--seed` is optional. `--log-system-prompts` is opt-in. Existing behavior unchanged in all cases.
- **No refactors.** The keyword classifier stays exactly as-is. No renaming, no restructuring, no "while we're here" improvements.
- **Minimal plumbing.** The `--classifier` flag threads through exactly two functions: `main()` in CLI `runner.py` passes it to `generate_analysis_report()` in `divergence.py`, which conditionally calls `llm_judge.classify_run()`. That's the entire integration surface.

### New files (no existing code risk)
- `src/emergent_divergence/metrics/llm_judge.py` (~180 lines)
- `dashboard/app.py` (~120 lines)
- `dashboard/components/data_loader.py` (~70 lines)
- `dashboard/components/run_selector.py` (~40 lines)
- `dashboard/components/jsd_plots.py` (~60 lines)
- `dashboard/components/behavioral.py` (~60 lines)
- `dashboard/components/comparison.py` (~80 lines)

### Modified files (minimal, additive changes)
- `src/emergent_divergence/cli/runner.py` — add `--seed`, `--classifier`, `--judge-model`, `--log-system-prompts` args (~40 lines added)
- `src/emergent_divergence/orchestration/runner.py` — add metadata.json write, RNG seeding, optional system prompt logging (~50 lines added)
- `src/emergent_divergence/metrics/divergence.py` — add `classifier` param to `generate_analysis_report()`, call LLM-judge when requested (~20 lines added)
- `src/emergent_divergence/logging_/events.py` — change run_id format to include seed+condition+shortid (~8 lines changed)
- `src/emergent_divergence/agents/agent.py` — expose system prompt text for logging (~5 lines added)
- `pyproject.toml` — add `streamlit`, `plotly`, `pandas` to optional deps, `scipy` already present for Spearman (~3 lines)

**Total estimated diff: ~750 lines added, ~10 lines modified.**

---

## 11. Explicit Non-Goals

- **No runner architecture rewrite.** The orchestration loop, turn rotation, memory clearing logic, and agent response flow stay exactly as they are.
- **No log schema breakage.** All existing event types (`run_start`, `experiment_config`, `round_start`, `agent_message`, `memory_write`, `round_end`, `run_end`) remain unchanged. The new `system_prompt` event is additive and opt-in.
- **No new experimental conditions.** No role-bias ablation configs, no shared memory conditions, no shuffled turn order. Those are Phase 3+ work.
- **No dashboard overbuild.** No transcript viewer, no run execution, no real-time monitoring, no LLM-judge triggering from the UI.
- **No transcript comparison UI.** The data model supports it (task_id and claim are already logged), but the UI is deferred.
- **No extra agents.** Stay at 3 agents until 2x2 factorial is complete, per the roadmap.
- **No metric redesign.** JSD computation, lexical uniqueness, memory stats, and coordination structure metrics stay exactly as-is. The only addition is the LLM-judge as a parallel classifier.
- **No keyword classifier changes.** The existing keyword lists, scoring logic, and output format are frozen. The LLM-judge runs alongside, not instead of.

---

## 12. Final Recommendation

### Must do before P1-02
1. `metadata.json` generation with git/code provenance
2. `--seed` CLI override
3. Full RNG propagation
4. Run directory naming with seed + condition + short unique suffix

These are the highest-value changes. Once you start multi-seed runs, provenance mistakes become very expensive. Total effort: ~80 lines across 3 files, low risk.

### Implement next (non-blocking for P1-02)
5. LLM-judge module
6. `--classifier` flag
7. Streamlit dashboard
8. Optional system prompt logging

These can be built while P1-02 is running or after it completes. The LLM-judge and dashboard are analysis-side only and can be applied retroactively to any existing run data.

### Change Risk Table

| Change | Risk | Touches runner? | Touches log format? | Must do before P1-02? |
|---|---|---|---|---|
| `metadata.json` + git provenance | Very low | Yes (adds output) | No | **Yes** |
| `--seed` CLI override | Low | Yes (seed selection) | No | **Yes** |
| RNG propagation | Low | Yes (init) | No | **Yes** |
| Run directory naming | Low | Yes (path format) | No | **Yes** |
| LLM-judge module | Very low | No | No | No |
| `--classifier` flag | Very low | No | No | No |
| Streamlit dashboard | Very low | No | No | No |
| System prompt logging | Low | Yes (adds events) | Additive, opt-in | No |
