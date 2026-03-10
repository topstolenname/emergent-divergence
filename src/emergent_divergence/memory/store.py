"""Lightweight per-agent persistent memory.

Design goals:
- Simple key-value with recency ordering
- JSONL-backed persistence between rounds
- Clear read/write event boundaries for logging
- No heavyweight vector DB — just structured recall
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MemoryStore:
    """Per-agent memory: an ordered list of memory entries with optional persistence."""

    def __init__(self, agent_id: str, persist_path: Path | None = None,
                 max_entries: int = 200):
        self.agent_id = agent_id
        self.persist_path = persist_path
        self.max_entries = max_entries
        self._entries: list[dict[str, Any]] = []

        if persist_path and persist_path.exists():
            self._load()

    def add(self, entry: dict[str, Any]) -> None:
        """Add a memory entry. Evicts oldest if at capacity."""
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
        if self.persist_path:
            self._save()

    def get_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent N entries."""
        return self._entries[-limit:]

    def get_all(self) -> list[dict[str, Any]]:
        """Return all entries."""
        return list(self._entries)

    def search(self, keyword: str, limit: int = 5) -> list[dict[str, Any]]:
        """Simple keyword search over memory content fields."""
        results = []
        keyword_lower = keyword.lower()
        for entry in reversed(self._entries):
            content = entry.get("content", "")
            if keyword_lower in content.lower():
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        """Reset memory (used for no-memory control condition)."""
        self._entries = []
        if self.persist_path:
            self._save()

    def _save(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.persist_path, "w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _load(self) -> None:
        self._entries = []
        with open(self.persist_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._entries.append(json.loads(line))


class SharedMemory:
    """Shared context memory accessible by all agents (optional condition)."""

    def __init__(self, persist_path: Path | None = None, max_entries: int = 500):
        self.persist_path = persist_path
        self.max_entries = max_entries
        self._entries: list[dict[str, Any]] = []

        if persist_path and persist_path.exists():
            self._load()

    def add(self, entry: dict[str, Any]) -> None:
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

    def get_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._entries[-limit:]

    def _save(self) -> None:
        if self.persist_path:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, "w", encoding="utf-8") as f:
                for entry in self._entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _load(self) -> None:
        self._entries = []
        with open(self.persist_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._entries.append(json.loads(line))
