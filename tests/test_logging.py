"""Tests for the structured event logger."""

import json
import tempfile
from pathlib import Path

from emergent_divergence.logging_.events import (
    ExperimentEvent,
    ExperimentLogger,
    generate_run_id,
    load_events,
)


def test_event_serialization():
    event = ExperimentEvent(
        event_type="test_event",
        run_id="run_test",
        round_id=5,
        agent_id="agent_0",
        data={"key": "value"},
    )
    j = event.to_json()
    parsed = json.loads(j)
    assert parsed["event_type"] == "test_event"
    assert parsed["round_id"] == 5
    assert parsed["data"]["key"] == "value"
    # None values should be stripped
    assert "task_id" not in parsed


def test_logger_writes_events():
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "test_run"
        logger = ExperimentLogger(run_dir, "run_001", "test_condition")

        logger.log("agent_message", round_id=0, agent_id="agent_0",
                    response_text="hello world")
        logger.close()

        events = load_events(run_dir / "events.jsonl")
        # Should have: run_start, agent_message, run_end
        assert len(events) == 3
        assert events[0]["event_type"] == "run_start"
        assert events[1]["event_type"] == "agent_message"
        assert events[2]["event_type"] == "run_end"


def test_generate_run_id():
    rid = generate_run_id()
    assert rid.startswith("run_")
    assert len(rid) > 20
