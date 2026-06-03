"""Structured JSONL event logging for experiment runs.

Every interaction, memory event, and round boundary is logged as a single
JSON line. This is the non-negotiable backbone of the experiment.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExperimentEvent:
    """A single logged event."""

    event_type: str
    run_id: str
    timestamp: float = field(default_factory=time.time)
    round_id: int | None = None
    task_id: str | None = None
    agent_id: str | None = None
    agent_role_bias: str | None = None
    condition: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        d = asdict(self)
        # Strip None values for cleaner logs
        return json.dumps({k: v for k, v in d.items() if v is not None}, ensure_ascii=False)


class ExperimentLogger:
    """Appends structured JSONL events to a log file."""

    def __init__(self, run_dir: Path, run_id: str, condition: str):
        self.run_dir = Path(run_dir)
        self.run_id = run_id
        self.condition = condition
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.run_dir / "events.jsonl"
        self._file = open(self.log_path, "a", encoding="utf-8")

        # Write run manifest as first event
        self.log_event(ExperimentEvent(
            event_type="run_start",
            run_id=self.run_id,
            condition=self.condition,
            data={"log_version": "1.0"},
        ))

    def log_event(self, event: ExperimentEvent) -> None:
        """Write a single event to the log file."""
        self._file.write(event.to_json() + "\n")
        self._file.flush()

    def log(self, event_type: str, *, round_id: int | None = None,
            task_id: str | None = None, agent_id: str | None = None,
            agent_role_bias: str | None = None, **data: Any) -> None:
        """Convenience method for logging."""
        event = ExperimentEvent(
            event_type=event_type,
            run_id=self.run_id,
            round_id=round_id,
            task_id=task_id,
            agent_id=agent_id,
            agent_role_bias=agent_role_bias,
            condition=self.condition,
            data=data,
        )
        self.log_event(event)

    def close(self) -> None:
        self.log("run_end")
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def generate_run_id() -> str:
    """Generate a timestamped run ID."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"run_{ts}_{short_uuid}"


def load_events(log_path: Path) -> list[dict]:
    """Load all events from a JSONL log file."""
    events = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
