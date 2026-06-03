---
title: "Lineage & Provenance"
created: 2026-03-10
tags: [lineage, provenance, agi-sac, history]
---

# Lineage & Provenance

## Origin

This experiment was extracted from the **AGI-SAC** research framework (`topstolenname/agisa_sac`) as a minimal empirical bridge experiment.

## Key Insight from Triage

> The old repo is a *numeric multi-agent simulation* (agents have cognitive state vectors, personality floats, resonance trackers). This experiment requires *LLM text generation* with *conversation threading*. Almost everything had to be rewritten.

## What Was Excluded

The triage identified extensive modules from AGI-SAC that were not needed:

- **Cloud infrastructure**: GCP, Cloud Functions, Cloud Run, Terraform, Pub/Sub
- **Container orchestration**: Docker, docker-compose
- **Production monitoring**: Prometheus, Grafana, OpenTelemetry
- **UI layers**: Gradio GUI, web dashboards, Puppeteer
- **Distributed systems**: Federation server, CRDT memory, topology manager
- **Ideological frameworks**: Governance engine, Concord of Coexistence, ethics framework
- **Chaos engineering**: Chaos engine and orchestrator
- **Heavy analytics**: TDA (persistent homology), semantic analyzer, social graph with GPU

## What Was Adapted (Concepts Only)

| AGI-SAC Module | Concept Used | How It Changed |
|---|---|---|
| `core/orchestrator.py` | Hook system, epoch loop | Rewritten as sequential turn loop |
| `agents/agent.py` (EnhancedAgent) | Per-agent memory, personality | Stripped to LLM system prompt biases |
| `core/components/memory.py` | Memory add/retrieve pattern | Simplified to JSONL key-value |
| `core/components/voice.py` | Per-agent linguistic signature | Measured post-hoc via JSD instead |
| `config.py` | Dataclass config with presets | New fields for experiment parameters |

## What Was Newly Built

| Component | Why It Didn't Exist |
|---|---|
| `AnthropicBackend` | Old repo used numeric cognitive engines, not LLM API calls |
| `Agent.respond()` | Old `EnhancedAgent.simulation_step()` manipulated floats |
| Task bank (claim analysis) | Old repo used entropy-driven epochs |
| JSONL structured logger | Old repo used Python logging + chronicler |
| Divergence metrics (JSD, behavioral) | Old metrics were satori ratios and archetype distributions |
| Multi-turn conversation builder | Old orchestrator shuffled agent order and passed entropy |
| CLI (run/analyze/compare) | Old CLI ran the numeric simulation engine |

## Related

- [[03 — Architecture Overview]] — Current architecture
- [[00 — Index]] — Vault home
