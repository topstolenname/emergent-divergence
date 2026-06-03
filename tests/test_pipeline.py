"""Tests for the matrix driver (brief §5): config resolution, expansion,
auto-reduce, integrity, and a full offline smoke run end-to-end.

The smoke path is the brief's headline guarantee — ``--smoke`` must produce the
complete artifact set (results, statistics, manifest, summary) using only the
free StubProvider, fast and offline.
"""

from __future__ import annotations

import json

import pytest

from emergent_divergence.cost.governor import CostGovernor
from emergent_divergence.orchestration.runner import CellResult
from emergent_divergence.pipeline import (
    auto_reduce,
    expand_matrix,
    integrity_check,
    load_pipeline_config,
    run_pipeline,
)

_ENV_KEYS = ("ROUNDS", "SEEDS", "COST_CAP_USD", "INFLUENCE_EVERY_N", "K_SAMPLES")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """The config layer honours these env vars; clear them for determinism."""
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


# ── config resolution / expansion ─────────────────────────────────────────────


def test_default_matrix_is_24_cells():
    cfg = load_pipeline_config(None)
    cells = expand_matrix(cfg)
    assert len(cells) == 24  # 2 backends × 3 conditions × 4 seeds
    assert cfg.backends == ["ollama", "claude"]
    assert cfg.rounds == 50


def test_smoke_clamps_to_offline_stub():
    cfg = load_pipeline_config(None, overrides={"smoke": True})
    assert cfg.smoke is True
    assert cfg.backends == ["stub"]
    assert cfg.conditions == ["A", "B", "C"]
    assert len(cfg.seeds) == 1
    assert cfg.rounds == 2
    assert cfg.influence_every_n == 1
    assert cfg.run_id == "smoke"
    assert len(expand_matrix(cfg)) == 3  # 1 backend × 3 conditions × 1 seed


def test_overrides_take_precedence():
    cfg = load_pipeline_config(
        None,
        overrides={"backends": ["stub"], "seeds": [7], "rounds": 9, "cap_usd": 12.5},
    )
    assert cfg.backends == ["stub"]
    assert cfg.seeds == [7]
    assert cfg.rounds == 9
    assert cfg.cap_usd == 12.5


# ── auto-reduce ───────────────────────────────────────────────────────────────


def test_auto_reduce_shrinks_to_fit_cap():
    # A $1 cap against the full claude matrix can't fit; the driver must shrink it.
    cfg = load_pipeline_config(None, overrides={"cap_usd": 1.0})
    governor = CostGovernor(cap_usd=cfg.cap_usd, prices=cfg.prices)
    seeds_before, rounds_before = len(cfg.seeds), cfg.rounds

    info = auto_reduce(cfg, governor)

    assert info["reduced"] is True
    # It drops seeds first, then scales rounds — at least one of those happened.
    assert len(cfg.seeds) < seeds_before or cfg.rounds < rounds_before
    assert info["final_estimate"]["total_est_usd"] <= cfg.cap_usd


def test_auto_reduce_noop_when_already_affordable():
    # Stub-only matrix costs $0, so nothing is reduced.
    cfg = load_pipeline_config(None, overrides={"backends": ["stub"]})
    governor = CostGovernor(cap_usd=cfg.cap_usd, prices=cfg.prices)
    info = auto_reduce(cfg, governor)
    assert info["reduced"] is False


# ── integrity ─────────────────────────────────────────────────────────────────


def _result(cell_id, status):
    return CellResult(cell_id=cell_id, status=status, rounds_done=2, rounds_total=2,
                      cost_usd=0.0, run_dir="x")


def test_integrity_ok_when_any_cell_analyzable():
    cfg = load_pipeline_config(None, overrides={"backends": ["stub"]})
    results = [_result("c1", "done"), _result("c2", "failed")]
    out = integrity_check(cfg, results, summaries=[{"cell_id": "c1"}])
    assert out["ok"] is True
    assert out["done"] == 1
    assert out["failed"] == 1
    assert out["analyzable"] == 1


def test_integrity_not_ok_when_nothing_analyzable():
    cfg = load_pipeline_config(None, overrides={"backends": ["stub"]})
    results = [_result("c1", "skipped_unavailable")]
    out = integrity_check(cfg, results, summaries=[])
    assert out["ok"] is False
    assert out["attempted"] == 0
    assert out["skipped_unavailable"] == 1


# ── full smoke run (offline, free) ────────────────────────────────────────────


def test_run_pipeline_smoke_end_to_end(tmp_path):
    cfg_yaml = tmp_path / "pipeline.yaml"
    cfg_yaml.write_text(
        f"output_root: {tmp_path / 'raw'}\n"
        f"report_root: {tmp_path / 'reports'}\n"
    )

    code = run_pipeline(
        config_path=str(cfg_yaml),
        overrides={"smoke": True},
        skip_tests=True,    # don't recurse into pytest from inside a test
        no_report=False,
        verbose=False,
    )
    assert code == 0

    report_dir = tmp_path / "reports" / "smoke"
    for name in ("results.csv", "results.json", "statistics.json",
                 "RUN_MANIFEST.json", "RESULTS_SUMMARY.md"):
        assert (report_dir / name).exists(), f"missing artifact: {name}"

    manifest = json.loads((report_dir / "RUN_MANIFEST.json").read_text())
    assert manifest["run_id"] == "smoke"
    assert manifest["integrity"]["ok"] is True
    # Three stub cells (A/B/C), all should complete offline.
    assert manifest["integrity"]["done"] == 3
