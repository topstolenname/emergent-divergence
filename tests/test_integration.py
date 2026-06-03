"""End-to-end integration tests for the single-cell runner (brief §3, §4.3, §7).

These exercise the *real* synchronous coordination loop on the deterministic
``StubProvider`` — no mocks, no network. They cover the deliberation loop, memory
writes, the counterfactual influence probe, checkpoint/resume idempotency, and the
bridge into per-cell metrics. The stub keeps them offline and fast while still
driving every code path the paid backends use.
"""

from __future__ import annotations

from collections import Counter

from emergent_divergence.logging_.events import load_events
from emergent_divergence.metrics.cell import analyze_cell
from emergent_divergence.orchestration.runner import CellConfig, CellRunner
from emergent_divergence.providers.stub import StubProvider


def _cfg(condition: str = "A", *, num_rounds: int = 2, seed: int = 42) -> CellConfig:
    return CellConfig(
        backend="stub",
        condition=condition,
        seed=seed,
        num_rounds=num_rounds,
        turns_per_round=2,
        num_agents=3,
        influence_every_n=1,   # measure every round so probes always fire
        k_samples=1,
    )


def _event_counts(run_dir) -> Counter:
    return Counter(e["event_type"] for e in load_events(run_dir / "events.jsonl"))


# ── condition A: full lifecycle ───────────────────────────────────────────────


def test_condition_a_runs_to_done(tmp_path):
    cfg = _cfg("A")
    run_dir = tmp_path / cfg.cell_id()
    res = CellRunner(cfg, StubProvider(), run_dir, verbose=False).run()

    assert res.status == "done"
    assert res.rounds_done == cfg.num_rounds == 2
    assert res.rounds_total == 2
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "status.json").exists()


def test_condition_a_event_lifecycle(tmp_path):
    cfg = _cfg("A")
    run_dir = tmp_path / cfg.cell_id()
    CellRunner(cfg, StubProvider(), run_dir, verbose=False).run()

    counts = _event_counts(run_dir)
    # config logged exactly once; full lifecycle present.
    assert counts["experiment_config"] == 1
    assert counts["run_start"] == 1
    assert counts["run_end"] == 1
    assert counts["round_start"] == 2 and counts["round_end"] == 2
    # 2 rounds × 2 turns × 3 agents.
    assert counts["agent_message"] == 12
    # condition A has memory enabled -> one write per agent message.
    assert counts["memory_write"] == 12
    # influence probe fires every (measured) round.
    assert counts["influence_probe_start"] == 2
    assert counts["influence_probe_factual"] > 0
    assert counts["influence_probe_ablated"] > 0


def test_condition_b_has_no_memory_writes(tmp_path):
    cfg = _cfg("B")
    run_dir = tmp_path / cfg.cell_id()
    res = CellRunner(cfg, StubProvider(), run_dir, verbose=False).run()

    assert res.status == "done"
    counts = _event_counts(run_dir)
    assert counts["memory_write"] == 0           # memory disabled in B
    assert counts["agent_message"] == 12          # deliberation still happens


def test_unknown_condition_raises(tmp_path):
    cfg = _cfg("Z")
    try:
        CellRunner(cfg, StubProvider(), tmp_path / "z", verbose=False)
    except ValueError as e:
        assert "condition" in str(e).lower()
    else:  # pragma: no cover - guard
        raise AssertionError("expected ValueError for unknown condition")


# ── checkpoint / resume ───────────────────────────────────────────────────────


def test_resume_when_already_complete_is_idempotent(tmp_path):
    cfg = _cfg("A")
    run_dir = tmp_path / cfg.cell_id()
    CellRunner(cfg, StubProvider(), run_dir, verbose=False).run()
    before = _event_counts(run_dir)

    # A second runner over the same dir must short-circuit, not re-run or duplicate.
    res2 = CellRunner(cfg, StubProvider(), run_dir, verbose=False).run()
    after = _event_counts(run_dir)

    assert res2.status == "done"
    assert res2.rounds_done == cfg.num_rounds
    assert after == before  # no duplicated events


def test_resume_from_partial_completes(tmp_path):
    run_dir = tmp_path / "stub_A_seed42"
    # First pass: only 1 round.
    CellRunner(_cfg("A", num_rounds=1), StubProvider(), run_dir, verbose=False).run()
    # Second pass on the same dir wants 2 rounds; it should resume from round 1.
    res = CellRunner(_cfg("A", num_rounds=2), StubProvider(), run_dir, verbose=False).run()

    assert res.status == "done"
    assert res.rounds_done == 2
    counts = _event_counts(run_dir)
    assert counts["experiment_config"] == 1   # not re-logged on resume
    assert counts["agent_message"] == 12       # round 0 + round 1, no duplication
    assert counts["round_end"] == 2


# ── named ablation hook (brief §4.3) ──────────────────────────────────────────


def test_rerun_target_with_ablation_shape(tmp_path):
    cfg = _cfg("A")
    runner = CellRunner(cfg, StubProvider(), tmp_path / cfg.cell_id(), verbose=False)
    out = runner.rerun_target_with_ablation("agent_0", "agent_1", round_id=0)

    assert set(out) == {"factual", "ablated"}
    assert out["factual"] and out["ablated"]
    assert all(isinstance(t, str) for t in out["factual"] + out["ablated"])


# ── metrics bridge ────────────────────────────────────────────────────────────


def test_analyze_cell_after_run(tmp_path):
    cfg = _cfg("A")
    run_dir = tmp_path / cfg.cell_id()
    CellRunner(cfg, StubProvider(), run_dir, verbose=False).run()

    out = analyze_cell(run_dir)
    summary = out["summary"]
    assert summary["backend"] == "stub"
    assert summary["condition"] == "A"
    assert summary["seed"] == 42
    assert summary["influence_available"] is True
    assert "report" in out
