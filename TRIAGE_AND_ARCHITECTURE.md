# Repo Triage & Architecture Report

## Emergent Behavioral Divergence Experiment
### Extracted from AGI-SAC (`topstolenname/agisa_sac`)

---

## 1. Repo Triage Map

### A. EXCLUDE — Not needed for this experiment

| Module / Path | Reason |
|---|---|
| `cloud/` | GCP API, Cloud Functions, Cloud Run — infra, not experiment |
| `containers/` | Docker, Dockerfile.chaos, edge containers — deployment layer |
| `docker-compose.*.yml` | Container orchestration — not needed locally |
| `infra/` | Terraform, GCP setup, ML pipeline config |
| `monitoring/` | Prometheus config — production observability |
| `observability/` | Grafana dashboards, FastAPI exporter — prod monitoring |
| `web/` | Dashboards, puppeteer — UI polish |
| `src/.../gcp/` | Distributed agent, Firestore, BigQuery, Vertex, GCS — cloud services |
| `src/.../federation/` | Distributed federation server, loop, CLI — multi-node architecture |
| `src/.../chaos/` | Chaos engine, orchestrator — chaos engineering tooling |
| `src/.../gui/` | Gradio GUI, tabs, visualization manager — UI layer |
| `src/.../governance/` | Full governance engine (appeals, voting, custody, enforcement) — ideological layer |
| `src/.../extensions/concord/` | Concord of Coexistence framework — ethics framework, not empirical |
| `src/.../agents/base_agent.py` | GCP-integrated hardened agent — too coupled to cloud infra |
| `src/.../orchestration/handoff_consumer.py` | Pub/Sub handoff — distributed messaging |
| `src/.../orchestration/topology_manager.py` | Topology management — advanced orchestration |
| `src/.../persistence/` | Firestore persistence — cloud dependency |
| `src/.../observability/` | OpenTelemetry tracing — production tooling |
| `src/.../cognition/` | Cognitive Governance Engine — specialized subsystem |
| `src/.../core/components/crdt_memory.py` | CRDT distributed memory — distributed systems tooling |
| `src/.../core/components/continuity_bridge.py` | CBP — specialized continuity mechanism |
| `src/.../core/components/enhanced_cbp.py` | Enhanced CBP — same |
| `src/.../core/components/semantic_analyzer.py` | Heavy semantic analysis — overkill for this experiment |
| `src/.../core/components/social.py` | Social graph with GPU — over-engineered for 3 agents |
| `src/.../core/multi_agent_system.py` | Thin wrapper — not useful standalone |
| `src/.../dev_agent.py` | Development agent tooling |
| `src/.../auditing/` | Transcript converter — post-processing utility |
| `src/.../utils/metrics.py` | Prometheus metrics — production monitoring |
| `src/.../chronicler.py` | ResonanceChronicler — AGI-SAC specific recording |
| `src/.../metrics/monitoring.py` | Monitoring metrics — prod tooling |
| `cognee/` | Hierarchical memory with genome — over-abstracted for this scope |
| `docs/` (most) | Historical docs, deployment guides, governance specs |
| `archived/` | Old discussions, snapshots, quickstarts |
| `validation/` | Legacy validators |
| `mkdocs.yml` | Documentation site config |
| `roadmap/` | Project roadmap |
| `scripts/chaos_orchestrator.py` | Chaos testing |
| `scripts/AGI_SAC_Phase_3.5_Main_Code.py` | Empty stub |

### B. OPTIONAL / ADAPTABLE — Conceptually useful, not directly portable

| Module | What's useful | Why not portable |
|---|---|---|
| `src/.../core/orchestrator.py` | Hook system, epoch loop pattern, save/load state | Tightly coupled to EnhancedAgent, TDA, social graph, chronicler. Useful as *inspiration* for the coordination loop, but needs rewrite. |
| `src/.../agents/agent.py` (EnhancedAgent) | Per-agent memory, personality-driven behavior, serialization | Built for numeric cognitive state vectors, not LLM text generation. No actual LLM calls. |
| `src/.../core/components/memory.py` | Memory add/retrieve/importance pattern | Over-engineered (semantic embeddings, importance decay). Our experiment needs simpler key-value recall. |
| `src/.../core/components/voice.py` | Concept of per-agent linguistic signature | Useful concept but implementation is AGI-SAC specific (style vectors, archetype tracking). |
| `src/.../analysis/analyzer.py` | System-wide metric aggregation | Computes satori ratios and archetype distributions — not relevant to our metrics. |
| `src/.../analysis/clustering.py` | KMeans clustering of style vectors | Concept useful; implementation needs rewrite for text-based features. |
| `src/.../analysis/tda.py` | Persistent homology tracker | Advanced topological analysis — optional future metric, not v1. |
| `src/.../config.py` | Dataclass config with presets | Pattern is good. Config fields are AGI-SAC specific. |
| `src/.../utils/logger.py` | Structured logging utility | Simple and reusable in spirit but our JSONL logger is purpose-built. |
| `src/.../utils/message_bus.py` | Pub/sub message passing | Could be useful for agent-to-agent messaging, but our sequential turn loop is simpler. |
| `examples/configs/` | YAML config pattern | Good pattern, configs need different fields. |

### C. MUST KEEP — Conceptual patterns worth porting

| Pattern | Where it comes from | How it's used in new repo |
|---|---|---|
| Config-driven experiment execution | `config.py`, orchestrator init | `ExperimentConfig` dataclass + YAML configs |
| Hook/callback system for epoch events | `orchestrator.register_hook()` | Future extension point (not v1) |
| Per-agent memory with persistence | `MemoryContinuumLayer` | `MemoryStore` with JSONL backing |
| Agent-ID-tagged interactions | EnhancedAgent pattern | Agent class with `agent_id`, `role_bias` |
| State serialization for reproducibility | `save_state()`/`load_state()` | JSONL event logs serve this role |
| Seeded RNG for determinism | `orchestrator.__init__` seeding | TaskGenerator and config seeds |

---

## 2. Minimal Architecture (New Repo)

```
emergent-divergence/
├── README.md
├── pyproject.toml
├── .gitignore
├── configs/
│   ├── baseline.yaml
│   ├── memory_enabled.yaml      # Condition A
│   └── no_memory.yaml           # Condition B
├── src/emergent_divergence/
│   ├── __init__.py
│   ├── __main__.py
│   ├── agents/
│   │   ├── __init__.py
│   │   └── agent.py             # LLM backend, Agent, role biases
│   ├── memory/
│   │   ├── __init__.py
│   │   └── store.py             # MemoryStore, SharedMemory
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── generator.py         # Task bank, TaskGenerator
│   ├── orchestration/
│   │   ├── __init__.py
│   │   └── runner.py            # ExperimentRunner, ExperimentConfig
│   ├── logging_/
│   │   ├── __init__.py
│   │   └── events.py            # JSONL logger, ExperimentEvent
│   ├── metrics/
│   │   ├── __init__.py
│   │   └── divergence.py        # JSD, behavioral, memory, coordination metrics
│   ├── evaluation/
│   │   ├── __init__.py
│   │   └── judge.py             # LLM-judge hooks (placeholder)
│   └── cli/
│       ├── __init__.py
│       └── runner.py            # CLI: run, analyze, compare
├── tests/
│   ├── conftest.py
│   ├── test_memory.py           # 5 tests
│   ├── test_logging.py          # 3 tests
│   ├── test_metrics.py          # 6 tests
│   └── test_tasks.py            # 3 tests
├── experiments/
│   ├── pilot_runs/
│   └── analysis_notebooks/
└── data/
    ├── raw_logs/
    ├── processed/
    └── reports/
```

---

## 3. Reusable Components Ported

| New module | Inspired by | What changed |
|---|---|---|
| `memory/store.py` | `core/components/memory.py` | Stripped to JSONL-backed key-value. Removed embeddings, importance, semantic search. |
| `orchestration/runner.py` | `core/orchestrator.py` | Rewritten for LLM-calling sequential turn loop. Removed TDA, social graph, chronicler. |
| Config pattern | `config.py` | New dataclass with experiment-specific fields. Same preset pattern. |
| Seeded task generation | Orchestrator seeding | Isolated into TaskGenerator with deterministic cycling. |

---

## 4. Gap Analysis — What Was Newly Built

| Component | Why it didn't exist in old repo |
|---|---|
| **LLM backend** (`AnthropicBackend`) | Old repo used numeric cognitive engines, not actual LLM API calls |
| **Agent with LLM calls** (`Agent.respond()`) | Old `EnhancedAgent.simulation_step()` manipulates floats, doesn't call LLMs |
| **Task bank** (claim analysis tasks) | Old repo didn't have discrete task content — it used entropy-driven epochs |
| **JSONL structured logger** | Old repo used Python logging + chronicler; no structured event format |
| **Divergence metrics** (JSD, behavioral classification, lexical uniqueness) | Old `analyzer.py` computed satori ratios and archetype distributions — different metrics entirely |
| **LLM-judge evaluation hooks** | Didn't exist |
| **CLI with run/analyze/compare** | Old CLI ran the simulation engine; new CLI drives the experiment |
| **Multi-turn conversation builder** | Old orchestrator shuffled agent order and passed entropy; no conversation threading |

**Key insight**: The old repo is a *numeric multi-agent simulation* (agents have cognitive state vectors, personality floats, resonance trackers). This experiment requires *LLM text generation* with *conversation threading*. Almost everything had to be rewritten.

---

## 5. Risks and Confounds

### Implementation Risks

1. **API cost**: 100 rounds × 3 agents × 2 turns = 600 LLM calls per condition. At ~$0.003/1K tokens output, a full run costs ~$5-15. Budget accordingly.

2. **Prompt overdetermination**: The role bias text in system prompts could dominate behavior. Mitigation: biases are intentionally weak ("You *tend* to...") and the prompt explicitly says "respond naturally."

3. **Conversation context growth**: By late turns, the context window fills with prior messages. Mitigation: 2 turns per round keeps context manageable; memory provides selective recall vs. full context.

4. **Model randomness vs. divergence**: Temperature=1.0 introduces stochastic variation. Need multiple seeds and repeated runs to distinguish noise from stable divergence.

5. **Keyword-based behavioral classification**: The current classifier uses keyword density, which is crude. Future versions should use embedding-based classification or LLM-judge scoring.

### Confounds to Watch

- **Fixed turn order**: Agents always speak in the same order. This could create positional bias. Consider shuffling order per round in a future condition.
- **Memory asymmetry**: Agents only store their own output summaries. Shared memory or storing others' outputs could change dynamics.
- **Task difficulty variance**: Different claims may elicit different amounts of disagreement. The seed ensures reproducibility, but analysis should control for task difficulty.

---

## 6. Recommendation Memo

### The Smallest Viable Experiment

1. **Run Condition A** (memory-enabled, 3 agents, 30 rounds) with seed=42
2. **Run Condition B** (no-memory, 3 agents, 30 rounds) with seed=42
3. **Analyze both** using the built-in metrics
4. **Compare** JSD trajectories and behavioral profiles between conditions

This produces one defensible comparison with ~360 LLM calls total. Total cost: ~$5-10. Total time: ~30-60 minutes per condition.

If the pilot shows signal (JSD increases over time in Condition A but not B, or behavioral profiles differentiate), proceed to 100+ round runs with multiple seeds.

### What NOT to do

- Do not add more agents until pilot results are in
- Do not add TDA, embedding-based metrics, or LLM-judge until v1 analysis is complete
- Do not add shared memory conditions until per-agent memory effects are established
- Do not refactor the architecture until you have usable experimental data
