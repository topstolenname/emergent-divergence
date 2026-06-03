"""Tests for the memory store."""

import json
import tempfile
from pathlib import Path

from emergent_divergence.memory.store import MemoryStore


def test_memory_add_and_retrieve():
    store = MemoryStore("test_agent")
    store.add({"content": "hello", "round_id": 0})
    store.add({"content": "world", "round_id": 1})
    assert store.count() == 2
    recent = store.get_recent(limit=1)
    assert len(recent) == 1
    assert recent[0]["content"] == "world"


def test_memory_eviction():
    store = MemoryStore("test_agent", max_entries=3)
    for i in range(5):
        store.add({"content": f"msg_{i}", "round_id": i})
    assert store.count() == 3
    assert store.get_all()[0]["content"] == "msg_2"


def test_memory_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "mem.jsonl"
        store = MemoryStore("test_agent", persist_path=path)
        store.add({"content": "persisted", "round_id": 0})

        # Reload
        store2 = MemoryStore("test_agent", persist_path=path)
        assert store2.count() == 1
        assert store2.get_recent()[0]["content"] == "persisted"


def test_memory_clear():
    store = MemoryStore("test_agent")
    store.add({"content": "hello"})
    store.clear()
    assert store.count() == 0


def test_memory_search():
    store = MemoryStore("test_agent")
    store.add({"content": "The weather is sunny today"})
    store.add({"content": "Machine learning is interesting"})
    store.add({"content": "The weather will be rainy tomorrow"})

    results = store.search("weather")
    assert len(results) == 2
