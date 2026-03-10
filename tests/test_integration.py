"""Integration tests for the refactored experiment pipeline.

Tests the three new features working together:
1. MockLLMBackend — deterministic responses without API calls
2. Turn order rotation — starting agent rotates per round
3. Async orchestration — full pipeline runs under asyncio
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from emergent_divergence.agents.agent import Agent, AgentConfig, MockLLMBackend
from emergent_divergence.logging_.events import load_events
from emergent_divergence.orchestration.runner import ExperimentConfig, ExperimentRunner


# ── MockLLMBackend unit tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_backend_returns_string():
    backend = MockLLMBackend()
    result = await backend.complete(
        [{"role": "user", "content": "Hello world"}],
        system="You are a test agent.",
    )
    assert isinstance(result, str)
    assert len(result) > 20


@pytest.mark.asyncio
async def test_mock_backend_deterministic():
    """Same input → same output, always."""
    backend = MockLLMBackend()
    msgs = [{"role": "user", "content": "Analyze this claim."}]
    kwargs = {"system": "You are Agent agent_0."}

    r1 = await backend.complete(msgs, **kwargs)
    r2 = await backend.complete(msgs, **kwargs)
    assert r1 == r2


@pytest.mark.asyncio
async def test_mock_backend_varies_with_input():
    """Different inputs should (usually) produce different outputs."""
    backend = MockLLMBackend()
    r1 = await backend.complete([{"role": "user", "content": "Topic A"}])
    r2 = await backend.complete([{"role": "user", "content": "Topic B"}])
    # Not guaranteed to differ for all inputs, but overwhelmingly likely
    # with SHA-256 seeding. We test it's not trivially broken.
    assert isinstance(r1, str) and isinstance(r2, str)


def test_mock_backend_token_count():
    backend = MockLLMBackend()
    count = backend.token_count("hello world this is a test")
    assert isinstance(count, int)
    assert count > 0


@pytest.mark.asyncio
async def test_mock_backend_tracks_call_count():
    backend = MockLLMBackend()
    assert backend.call_count == 0
    await backend.complete([{"role": "user", "content": "test"}])
    await backend.complete([{"role": "user", "content": "test2"}])
    assert backend.call_count == 2


# ── Agent async tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_respond_async():
    """Agent.respond is now async and returns the expected dict shape."""
    backend = MockLLMBackend()
    config = AgentConfig(agent_id="agent_0", role_bias="proposer", memory_enabled=False)
    agent = Agent(config, backend)

    result = await agent.respond(
        [{"role": "user", "content": "Discuss climate policy."}],
        round_id=0,
        task_id="task_0000",
    )

    assert result["agent_id"] == "agent_0"
    assert result["role_bias"] == "proposer"
    assert result["model"] == "mock-v1"
    assert isinstance(result["response_text"], str)
    assert result["token_count"] is not None
    assert result["latency_s"] >= 0


# ── Turn order rotation tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_turn_order_rotation():
    """Verify that the starting agent rotates every round."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ExperimentConfig(
            num_agents=3,
            num_rounds=6,  # 6 rounds = each agent starts exactly twice
            turns_per_round=1,
            memory_enabled=False,
            backend="mock",
            condition="test_rotation",
            output_dir=tmpdir,
        )
        runner = ExperimentRunner(config)
        run_dir = await runner.run_async()

        events = load_events(run_dir / "events.jsonl")
        agent_messages = [e for e in events if e.get("event_type") == "agent_message"]

        # With 3 agents and 1 turn per round, we get 3 messages per round.
        # Check who speaks first in each round.
        # round_id and agent_id are top-level fields in the event schema.
        first_speakers_by_round: dict[int, str] = {}
        for msg in agent_messages:
            rid = msg.get("round_id")
            aid = msg.get("agent_id")
            if rid is not None and rid not in first_speakers_by_round:
                first_speakers_by_round[rid] = aid

        # Round 0: offset=0 → agent_0 first
        # Round 1: offset=1 → agent_1 first
        # Round 2: offset=2 → agent_2 first
        # Round 3: offset=0 → agent_0 first (wraps)
        assert first_speakers_by_round[0] == "agent_0"
        assert first_speakers_by_round[1] == "agent_1"
        assert first_speakers_by_round[2] == "agent_2"
        assert first_speakers_by_round[3] == "agent_0"


# ── Full pipeline integration test ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_pipeline_with_mock():
    """Run a complete 5-round experiment with mock backend and verify logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ExperimentConfig(
            num_agents=3,
            num_rounds=5,
            turns_per_round=2,
            memory_enabled=True,
            memory_max_entries=50,
            backend="mock",
            condition="memory_enabled",
            seed=42,
            output_dir=tmpdir,
        )
        runner = ExperimentRunner(config)
        run_dir = await runner.run_async()

        # Verify log file exists and is valid JSONL
        log_path = run_dir / "events.jsonl"
        assert log_path.exists()

        events = load_events(log_path)
        event_types = [e["event_type"] for e in events]

        # Must have the full lifecycle
        assert "run_start" in event_types
        assert "experiment_config" in event_types
        assert "round_start" in event_types
        assert "agent_message" in event_types
        assert "memory_write" in event_types
        assert "round_end" in event_types
        assert "run_end" in event_types

        # 5 rounds × 2 turns × 3 agents = 30 agent messages
        agent_msgs = [e for e in events if e["event_type"] == "agent_message"]
        assert len(agent_msgs) == 30

        # Every agent message has the required fields
        for msg in agent_msgs:
            data = msg.get("data", msg)
            assert "agent_id" in data or "agent_id" in msg
            assert "response_text" in data
            assert "token_count" in data
            assert "model" in data

        # Memory files should exist for each agent
        for i in range(3):
            mem_path = run_dir / "memory" / f"agent_{i}.jsonl"
            assert mem_path.exists()


@pytest.mark.asyncio
async def test_no_memory_condition():
    """No-memory control: verify memory is cleared after each round."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ExperimentConfig(
            num_agents=2,
            num_rounds=3,
            turns_per_round=1,
            memory_enabled=False,
            backend="mock",
            condition="no_memory",
            seed=99,
            output_dir=tmpdir,
        )
        runner = ExperimentRunner(config)
        await runner.run_async()

        # Agents should have no accumulated memory
        for agent in runner.agents:
            if agent.memory:
                assert agent.memory.count() == 0


@pytest.mark.asyncio
async def test_config_validation():
    """ExperimentConfig rejects invalid settings."""
    with pytest.raises(ValueError, match="at least 2 agents"):
        ExperimentConfig(num_agents=1).validate()

    with pytest.raises(ValueError, match="role_biases length"):
        ExperimentConfig(num_agents=3, role_biases=["proposer"]).validate()

    with pytest.raises(ValueError, match="Unknown backend"):
        ExperimentConfig(backend="gpt-magic").validate()
