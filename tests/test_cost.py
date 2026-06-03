"""Unit tests for the cost governor (brief §6)."""

from __future__ import annotations

from emergent_divergence.cost.governor import CostGovernor, Price


def test_free_backends_cost_zero():
    g = CostGovernor()
    assert g.cost_of("ollama", 1_000_000, 1_000_000) == 0.0
    assert g.cost_of("stub", 1_000_000, 1_000_000) == 0.0


def test_claude_pricing():
    g = CostGovernor()
    assert g.cost_of("claude", 1_000_000, 0) == 3.0
    assert g.cost_of("claude", 0, 1_000_000) == 15.0
    assert g.cost_of("claude", 1_000_000, 1_000_000) == 18.0


def test_unknown_backend_is_free():
    assert CostGovernor().cost_of("mystery", 1_000_000, 1_000_000) == 0.0


def test_record_accumulates():
    g = CostGovernor()
    c1 = g.record("claude", 1_000_000, 0)
    c2 = g.record("claude", 0, 1_000_000)
    assert c1 == 3.0 and c2 == 15.0
    assert g.spent_usd == 18.0
    assert g.input_tokens == 1_000_000 and g.output_tokens == 1_000_000
    assert g.calls == 2


def test_would_exceed_and_remaining():
    g = CostGovernor(cap_usd=10.0)
    assert not g.would_exceed(5.0)
    assert g.would_exceed(10.01)
    g.record("claude", 0, 1_000_000)  # +$15 -> over a $10 cap
    assert g.remaining() == 0.0


def test_can_afford():
    g = CostGovernor(cap_usd=1.0)
    assert g.can_afford("claude", 100_000, 0)        # $0.30
    assert not g.can_afford("claude", 0, 1_000_000)  # $15.00


def test_snapshot_roundtrip():
    g = CostGovernor(cap_usd=42.0)
    g.record("claude", 500_000, 200_000)
    snap = g.snapshot()
    g2 = CostGovernor()
    g2.load_snapshot(snap)
    assert g2.cap_usd == 42.0
    assert g2.spent_usd == g.spent_usd
    assert g2.calls == g.calls
    assert g2.input_tokens == g.input_tokens


def test_save_and_from_file(tmp_path):
    g = CostGovernor(cap_usd=12.0)
    g.record("claude", 100_000, 100_000)
    path = tmp_path / "snap" / "cost.json"
    g.save(path)
    assert path.exists()
    g2 = CostGovernor.from_file(path)
    assert g2.cap_usd == 12.0
    assert g2.spent_usd == g.spent_usd
    assert g2.calls == 1


def test_custom_prices():
    g = CostGovernor(prices={"claude": Price(1.0, 2.0)})
    assert g.cost_of("claude", 1_000_000, 1_000_000) == 3.0
