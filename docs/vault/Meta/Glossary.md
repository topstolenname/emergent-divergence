---
title: "Glossary"
created: 2026-03-10
tags: [glossary, definitions, reference]
---

# Glossary

## Experiment Terms

**Agent**: A single LLM instance with a unique ID, role bias, and optional persistent memory. In this experiment, all agents share the same base model.

**Behavioral Divergence Score**: Mean pairwise L2 distance between agents' behavioral profile vectors. Higher values indicate more behavioral specialization.

**Behavioral Profile**: A vector of keyword-density scores across 6 categories (proposal, critique, synthesis, verification, recall, clarification) averaged over all of an agent's messages.

**Claim Bank**: A fixed set of 20 debatable claims used as task stimuli. Claims cycle with seeded shuffling.

**Condition**: An experimental treatment. Condition A = memory enabled; Condition B = no memory (control).

**JSD (Jensen-Shannon Divergence)**: A symmetric measure of distance between two probability distributions. Used here to compare word frequency distributions between agent pairs. Range: 0 (identical) to ~0.83 (maximally different).

**Lexical Uniqueness**: The fraction of an agent's vocabulary (unique word types) not used by any other agent.

**Memory Entry**: A stored record containing round_id, content (first 300 chars of agent response), source, agent_id, and timestamp.

**Memory Store**: Per-agent persistent memory backed by JSONL files. Supports add, get_recent, search, clear.

**Role Bias**: A weak textual inclination injected into an agent's system prompt. Not a hard constraint — agents can act outside their bias.

**Round**: One iteration of the experiment loop. Each round presents a claim and involves 2 turns of all agents speaking.

**Run**: A complete experiment execution producing a directory of logs. Identified by a run_id like `run_20260310_161255_db9f7b49`.

**Seed**: Integer controlling the random number generator for task ordering. Enables reproducibility.

**Sliding Window**: A moving block of N consecutive rounds used to compute time-varying metrics (e.g., JSD over time).

**Turn**: Within a round, one pass through all agents. With 2 turns per round and 3 agents, each round produces 6 messages.

## Technical Terms

**Anthropic Backend**: The `AnthropicBackend` class that wraps the Claude API async client.

**JSONL**: JSON Lines format — one JSON object per line. Used for event logs and memory persistence.

**Mock Backend**: `MockLLMBackend` — a deterministic testing backend that generates responses from templates using SHA-256 hashing of inputs.

**System Prompt**: The instructional text sent to the LLM as the "system" role. Contains agent identity, role bias text, and memory context.

## Lineage Terms

**AGI-SAC**: The parent research framework (`topstolenname/agisa_sac`) from which this experiment was extracted. A numeric multi-agent simulation using cognitive state vectors.

**Emergent Divergence**: The hypothesized phenomenon where same-model LLM instances develop distinct behavioral patterns through repeated interaction with persistent memory.

## Related

- [[00 — Index]] — Vault home
- [[01 — Research Question & Hypothesis]] — What we're testing
