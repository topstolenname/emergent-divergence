"""Matrix driver: the single entry behind ``python -m emergent_divergence pipeline``.

Stages (brief §5), each idempotent and resumable:

  0. preflight   — shared embedder + per-backend availability + writable dirs.
  1. test gate   — pytest must pass before any *paid* generation (STOP on fail).
  2. cost est    — estimate paid spend; auto-reduce the matrix to fit the cap.
  3. run matrix  — iterate cells with one shared :class:`CostGovernor`;
                   checkpoint/resume via ``status.json``, retries w/ backoff;
                   a single failed cell never aborts the matrix.
  4. analyze     — per-cell metrics -> cross-cell statistics -> report artifacts.
  5. integrity   — verify expected vs produced; print report path + summary.

Re-running the same ``run_id`` resumes partial cells and continues global cost
accounting (``cost_snapshot.json``), so the operator can ``Ctrl-C`` and restart
without losing work or double-counting spend.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from emergent_divergence.cost.governor import CostGovernor, Price
from emergent_divergence.orchestration.runner import CellConfig, CellResult, CellRunner
from emergent_divergence.providers import build_provider

# ── configuration ──────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "backends": ["ollama", "claude"],
    "conditions": ["A", "B", "C"],
    "seeds": [42, 43, 44, 45],
    "rounds": 50,
    "turns_per_round": 2,
    "temperature": 1.0,
    "max_tokens": 400,
    "num_agents": 3,
    "influence_every_n": 5,
    "k_samples": {"ollama": 1, "claude": 3, "stub": 1},
    "ablation": "neutral",
    "null_baseline": True,
    "retries": 2,
    "retry_backoff_s": 2.0,
    "output_root": "data/raw_logs",
    "report_root": "data/reports",
    "cost": {"cap_usd": 50.0},
    "backends_cfg": {
        "ollama": {"model": "llama3.2:3b", "host": "http://localhost:11434"},
        "claude": {"model": "claude-sonnet-4-6"},
        "stub": {"model": "stub-v1"},
    },
}

# Conservative per-call token figures for the *pre-run* estimate only (real spend
# is metered from provider usage during the run).
_EST_INPUT_TOKENS = 600


@dataclass
class PipelineConfig:
    run_id: str
    backends: list[str]
    conditions: list[str]
    seeds: list[int]
    rounds: int
    turns_per_round: int
    temperature: float
    max_tokens: int
    num_agents: int
    influence_every_n: int
    k_samples: dict[str, int]
    ablation: str
    null_baseline: bool
    cap_usd: float
    retries: int
    retry_backoff_s: float
    output_root: Path
    report_root: Path
    backends_cfg: dict[str, dict]
    prices: dict[str, Price] = field(default_factory=dict)
    smoke: bool = False

    @property
    def run_output_dir(self) -> Path:
        return self.output_root / self.run_id

    @property
    def report_dir(self) -> Path:
        return self.report_root / self.run_id

    def k_for(self, backend: str) -> int:
        return int(self.k_samples.get(backend, 1))

    def to_serializable(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "backends": self.backends,
            "conditions": self.conditions,
            "seeds": self.seeds,
            "rounds": self.rounds,
            "turns_per_round": self.turns_per_round,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "num_agents": self.num_agents,
            "influence_every_n": self.influence_every_n,
            "k_samples": self.k_samples,
            "ablation": self.ablation,
            "null_baseline": self.null_baseline,
            "cap_usd": self.cap_usd,
            "smoke": self.smoke,
            "output_root": str(self.output_root),
            "report_root": str(self.report_root),
            "backends_cfg": self.backends_cfg,
        }


def _coerce_k_samples(raw: Any) -> dict[str, int]:
    """Accept either a flat int (applied to all) or a per-backend mapping."""
    base = dict(_DEFAULTS["k_samples"])
    if isinstance(raw, dict):
        base.update({k: int(v) for k, v in raw.items()})
    elif raw is not None:
        base = {b: int(raw) for b in ("ollama", "claude", "stub")}
    return base


def load_pipeline_config(
    config_path: str | Path | None, *, overrides: dict[str, Any] | None = None
) -> PipelineConfig:
    """Build a :class:`PipelineConfig` from YAML + env + CLI overrides.

    Precedence (low → high): packaged defaults → ``configs/pipeline.yaml`` →
    environment (``ROUNDS``/``SEEDS``/``COST_CAP_USD``/``INFLUENCE_EVERY_N``/
    ``K_SAMPLES``) → explicit ``overrides`` (CLI flags) → ``--smoke`` clamps.
    """
    data: dict[str, Any] = json.loads(json.dumps(_DEFAULTS))  # deep copy
    if config_path:
        p = Path(config_path)
        if p.exists():
            loaded = yaml.safe_load(p.read_text()) or {}
            _deep_update(data, loaded)

    _apply_env(data)

    overrides = overrides or {}
    smoke = bool(overrides.get("smoke"))
    for key in ("backends", "conditions", "seeds", "rounds", "run_id"):
        if overrides.get(key) is not None:
            data[key] = overrides[key]
    if overrides.get("cap_usd") is not None:
        data["cost"]["cap_usd"] = float(overrides["cap_usd"])

    if smoke:
        # Fast, offline, free proof of the whole wiring (brief §9).
        data["backends"] = ["stub"]
        data["conditions"] = ["A", "B", "C"]
        data["seeds"] = [data["seeds"][0] if data["seeds"] else 42]
        data["rounds"] = 2
        data["influence_every_n"] = 1
        data["k_samples"] = {"stub": 1, "ollama": 1, "claude": 1}

    run_id = data.get("run_id") or ("smoke" if smoke else _new_run_id())
    prices = _prices_from_cfg(data.get("backends_cfg", {}), data.get("cost", {}))

    return PipelineConfig(
        run_id=str(run_id),
        backends=list(data["backends"]),
        conditions=list(data["conditions"]),
        seeds=[int(s) for s in data["seeds"]],
        rounds=int(data["rounds"]),
        turns_per_round=int(data["turns_per_round"]),
        temperature=float(data["temperature"]),
        max_tokens=int(data["max_tokens"]),
        num_agents=int(data["num_agents"]),
        influence_every_n=int(data["influence_every_n"]),
        k_samples=_coerce_k_samples(data.get("k_samples")),
        ablation=str(data["ablation"]),
        null_baseline=bool(data.get("null_baseline", True)),
        cap_usd=float(data["cost"]["cap_usd"]),
        retries=int(data["retries"]),
        retry_backoff_s=float(data["retry_backoff_s"]),
        output_root=Path(data["output_root"]),
        report_root=Path(data["report_root"]),
        backends_cfg=dict(data["backends_cfg"]),
        prices=prices,
        smoke=smoke,
    )


def _deep_update(base: dict, new: dict) -> None:
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def _apply_env(data: dict[str, Any]) -> None:
    if os.getenv("ROUNDS"):
        data["rounds"] = int(os.environ["ROUNDS"])
    if os.getenv("SEEDS"):
        data["seeds"] = [int(s) for s in os.environ["SEEDS"].replace(",", " ").split()]
    if os.getenv("COST_CAP_USD"):
        data["cost"]["cap_usd"] = float(os.environ["COST_CAP_USD"])
    if os.getenv("INFLUENCE_EVERY_N"):
        data["influence_every_n"] = int(os.environ["INFLUENCE_EVERY_N"])
    if os.getenv("K_SAMPLES"):
        data["k_samples"] = _coerce_k_samples(int(os.environ["K_SAMPLES"]))


def _prices_from_cfg(backends_cfg: dict, cost_cfg: dict) -> dict[str, Price]:
    """Pull per-backend prices from config if present, else defaults."""
    from emergent_divergence.cost.governor import DEFAULT_PRICES

    prices = dict(DEFAULT_PRICES)
    pricing = cost_cfg.get("prices", {}) if isinstance(cost_cfg, dict) else {}
    for backend, pc in pricing.items():
        if isinstance(pc, dict) and "input_per_mtok" in pc:
            prices[backend] = Price(
                float(pc["input_per_mtok"]), float(pc["output_per_mtok"])
            )
    return prices


def _new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ── matrix expansion ────────────────────────────────────────────────────────────


def expand_matrix(cfg: PipelineConfig, backends: list[str] | None = None) -> list[CellConfig]:
    backends = backends if backends is not None else cfg.backends
    cells: list[CellConfig] = []
    for backend in backends:
        for condition in cfg.conditions:
            for seed in cfg.seeds:
                cells.append(_make_cell(cfg, backend, condition, seed))
    return cells


def _make_cell(cfg: PipelineConfig, backend: str, condition: str, seed: int) -> CellConfig:
    return CellConfig(
        backend=backend,
        condition=condition,
        seed=seed,
        num_rounds=cfg.rounds,
        turns_per_round=cfg.turns_per_round,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        num_agents=cfg.num_agents,
        influence_every_n=cfg.influence_every_n,
        k_samples=cfg.k_for(backend),
        ablation=cfg.ablation,
        null_baseline=cfg.null_baseline,
    )


# ── stage 0: preflight ────────────────────────────────────────────────────────


def preflight(cfg: PipelineConfig) -> dict[str, Any]:
    """Check the shared embedder, per-backend availability, and writable dirs."""
    info: dict[str, Any] = {"backends": {}, "embedder": {}, "dirs_ok": False}

    try:
        from emergent_divergence.embeddings import get_embedder

        embedder = get_embedder()
        info["embedder"] = embedder.info()
    except Exception as e:  # noqa: BLE001
        info["embedder"] = {"backend": "unavailable", "error": str(e)}

    for backend in cfg.backends:
        info["backends"][backend] = _check_backend(backend, cfg.backends_cfg.get(backend, {}))

    try:
        cfg.run_output_dir.mkdir(parents=True, exist_ok=True)
        cfg.report_dir.mkdir(parents=True, exist_ok=True)
        info["dirs_ok"] = True
    except Exception as e:  # noqa: BLE001
        info["dirs_error"] = str(e)

    return info


def _check_backend(backend: str, bcfg: dict) -> dict[str, Any]:
    backend = backend.lower()
    if backend == "stub":
        return {"available": True, "reason": "stub is always available"}
    if backend == "ollama":
        return _check_ollama(bcfg.get("host", "http://localhost:11434"))
    if backend == "claude":
        if os.getenv("ANTHROPIC_API_KEY"):
            return {"available": True, "reason": "ANTHROPIC_API_KEY present"}
        return {"available": False, "reason": "ANTHROPIC_API_KEY not set"}
    return {"available": False, "reason": f"unknown backend {backend!r}"}


def _check_ollama(host: str) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    url = host.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310 — local host
            ok = resp.status == 200
        return {"available": ok, "reason": f"reachable at {host}" if ok else f"HTTP {resp.status}"}
    except (urllib.error.URLError, OSError) as e:
        return {"available": False, "reason": f"unreachable at {host}: {e}"}


def _allow_hashing_fallback() -> bool:
    """Operator opt-in (``ALLOW_HASHING_EMBEDDER``) to run on the lexical fallback."""
    return os.getenv("ALLOW_HASHING_EMBEDDER", "").strip().lower() in ("1", "true", "yes")


# ── stage 1: test gate ──────────────────────────────────────────────────────────


def run_test_gate(*, skip: bool = False) -> dict[str, Any]:
    """Run pytest before any paid generation. Exit-code 5 (no tests) is a soft pass."""
    if skip:
        return {"ran": False, "passed": True, "skipped": True, "returncode": None}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=str(Path.cwd()),
            capture_output=True,
            text=True,
            timeout=900,
        )
    except FileNotFoundError:
        return {"ran": False, "passed": True, "skipped": True, "reason": "pytest not installed"}
    except subprocess.TimeoutExpired:
        return {"ran": True, "passed": False, "returncode": None, "reason": "timeout"}
    rc = proc.returncode
    # pytest exit 5 == "no tests collected": treat as a pass so the pipeline runs
    # before the test suite lands, and naturally enforces once it does.
    passed = rc in (0, 5)
    tail = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    return {"ran": True, "passed": passed, "returncode": rc, "summary": tail[0]}


# ── stage 2: cost estimate + auto-reduce ─────────────────────────────────────────


def _calls_per_cell(cfg: PipelineConfig) -> int:
    """Number of model calls one cell makes (deliberation + influence probes)."""
    n = cfg.num_agents
    k = 1  # resolved per backend below; this is the structural count
    deliberation = cfg.rounds * cfg.turns_per_round * n
    measured = sum(1 for r in range(cfg.rounds) if r % max(1, cfg.influence_every_n) == 0)
    return deliberation, measured, n, k


def estimate_cost(cfg: PipelineConfig, governor: CostGovernor) -> dict[str, Any]:
    """Pre-run spend estimate per backend (free backends cost $0)."""
    deliberation, measured, n, _ = _calls_per_cell(cfg)
    per_backend: dict[str, Any] = {}
    total = 0.0
    for backend in cfg.backends:
        k = cfg.k_for(backend)
        probe_calls = measured * (n + n * k + n * (n - 1) * k)
        if cfg.null_baseline:
            probe_calls += measured * (n * max(2, k))  # same-prompt null probe
        calls_per_cell = deliberation + probe_calls
        n_cells = len(cfg.conditions) * len(cfg.seeds)
        unit = governor.cost_of(backend, _EST_INPUT_TOKENS, cfg.max_tokens)
        cost = calls_per_cell * n_cells * unit
        per_backend[backend] = {
            "n_cells": n_cells,
            "calls_per_cell": calls_per_cell,
            "est_usd": round(cost, 4),
        }
        total += cost
    return {"per_backend": per_backend, "total_est_usd": round(total, 4), "cap_usd": cfg.cap_usd}


def auto_reduce(cfg: PipelineConfig, governor: CostGovernor) -> dict[str, Any]:
    """Shrink the matrix (seeds first, then rounds) until the estimate fits the cap.

    Reductions apply to the *whole* matrix so cross-backend comparisons stay
    balanced; the truncation is disclosed in the manifest.
    """
    info: dict[str, Any] = {"reduced": False, "actions": []}
    est = estimate_cost(cfg, governor)
    if est["total_est_usd"] <= cfg.cap_usd:
        info["final_estimate"] = est
        return info

    # 1) Drop seeds from the end, keep ≥ 1.
    while len(cfg.seeds) > 1 and estimate_cost(cfg, governor)["total_est_usd"] > cfg.cap_usd:
        dropped = cfg.seeds.pop()
        info["reduced"] = True
        info["actions"].append(f"dropped seed {dropped}")

    # 2) Still over: scale rounds down toward a floor of 10 (then 4).
    for floor in (10, 4, 2):
        while cfg.rounds > floor and estimate_cost(cfg, governor)["total_est_usd"] > cfg.cap_usd:
            cfg.rounds = max(floor, int(cfg.rounds * 0.75))
            info["reduced"] = True
            info["actions"].append(f"reduced rounds to {cfg.rounds}")
            if cfg.rounds == floor:
                break

    info["final_estimate"] = estimate_cost(cfg, governor)
    return info


# ── stage 3: run the matrix ──────────────────────────────────────────────────────


def run_matrix(
    cfg: PipelineConfig,
    governor: CostGovernor,
    preflight_info: dict[str, Any],
    *,
    verbose: bool = True,
) -> list[CellResult]:
    """Run every cell of available backends, sharing one cost governor."""
    snapshot_path = cfg.report_dir / "cost_snapshot.json"
    if snapshot_path.exists():
        try:
            governor.load_snapshot(json.loads(snapshot_path.read_text()))
        except Exception:  # noqa: BLE001 — corrupt snapshot shouldn't block a run
            pass

    available = {
        b: preflight_info["backends"].get(b, {}).get("available", False)
        for b in cfg.backends
    }
    providers: dict[str, Any] = {}
    results: list[CellResult] = []
    cells = expand_matrix(cfg)
    total = len(cells)

    for i, cell in enumerate(cells, 1):
        backend = cell.backend
        if not available.get(backend, False):
            results.append(_unavailable_result(cfg, cell, preflight_info))
            if verbose:
                print(f"[{i}/{total}] {cell.cell_id()}: SKIP (backend unavailable)", flush=True)
            continue

        if backend not in providers:
            try:
                providers[backend] = build_provider(backend, cfg.backends_cfg.get(backend, {}))
            except Exception as e:  # noqa: BLE001
                available[backend] = False
                results.append(_unavailable_result(cfg, cell, preflight_info, reason=str(e)))
                if verbose:
                    print(f"[{i}/{total}] {cell.cell_id()}: SKIP (provider error: {e})",
                          flush=True)
                continue

        run_dir = cfg.run_output_dir / cell.cell_id()
        res = _run_cell_with_retries(cfg, cell, providers[backend], run_dir, governor,
                                     verbose=verbose)
        governor.save(snapshot_path)
        results.append(res)
        if verbose:
            print(
                f"[{i}/{total}] {cell.cell_id()}: {res.status} "
                f"({res.rounds_done}/{res.rounds_total} rounds, "
                f"spend ${governor.spent_usd:.4f}/{cfg.cap_usd:.0f})",
                flush=True,
            )
    return results


def _run_cell_with_retries(
    cfg: PipelineConfig,
    cell: CellConfig,
    provider: Any,
    run_dir: Path,
    governor: CostGovernor,
    *,
    verbose: bool,
) -> CellResult:
    last: CellResult | None = None
    for attempt in range(cfg.retries + 1):
        runner = CellRunner(cell, provider, run_dir, governor=governor, verbose=False)
        res = runner.run()
        last = res
        if res.status in ("done", "skipped_due_to_cap"):
            return res
        if res.status == "failed" and attempt < cfg.retries:
            backoff = cfg.retry_backoff_s * (2 ** attempt)
            if verbose:
                print(f"    retry {attempt + 1}/{cfg.retries} after {backoff:.1f}s "
                      f"({res.error})", flush=True)
            time.sleep(backoff)
            continue
        return res
    return last  # type: ignore[return-value]


def _unavailable_result(
    cfg: PipelineConfig, cell: CellConfig, preflight_info: dict, *, reason: str | None = None
) -> CellResult:
    why = reason or preflight_info["backends"].get(cell.backend, {}).get("reason", "unavailable")
    return CellResult(
        cell_id=cell.cell_id(),
        status="skipped_unavailable",
        rounds_done=0,
        rounds_total=cfg.rounds,
        cost_usd=0.0,
        run_dir=str(cfg.run_output_dir / cell.cell_id()),
        error=why,
    )


# ── provenance (reproducibility fingerprint) ─────────────────────────────────────

# A dated snapshot ends in ``-YYYYMMDD``; anything else (e.g. ``claude-sonnet-4-6``)
# is a rolling alias that may be re-pointed by the provider over time.
_DATED_SNAPSHOT_RE = re.compile(r"-\d{8}$")


def _run_git(args: list[str]) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(Path.cwd()),
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _git_provenance() -> dict[str, Any]:
    """Best-effort git fingerprint: commit SHA, branch, and working-tree dirtiness."""
    sha = _run_git(["rev-parse", "HEAD"])
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    porcelain = _run_git(["status", "--porcelain"])
    return {
        "sha": sha,
        "branch": branch,
        "dirty": (bool(porcelain) if porcelain is not None else None),
    }


def _normalize_ollama_tag(name: str) -> str:
    """Ollama implies ``:latest`` when a tag is omitted; normalise for exact match."""
    return name if ":" in name else f"{name}:latest"


def _select_ollama_entry(models: list[dict], model: str) -> dict | None:
    """Exact match on the normalised ``repo:tag``.

    Matching on the bare repo would let a *different* tag of the same repo
    (e.g. ``llama3.2:1b`` vs the requested ``llama3.2:3b``) supply the wrong
    digest when several are installed — so we require the full tag to agree.
    """
    want = _normalize_ollama_tag(model)
    for m in models:
        if _normalize_ollama_tag(str(m.get("name", ""))) == want:
            return m
    return None


def _ollama_provenance(bcfg: dict) -> dict[str, Any]:
    """Resolve the Ollama model's content digest via ``/api/tags`` (best-effort)."""
    import urllib.request

    host = str(bcfg.get("host", "http://localhost:11434")).rstrip("/")
    model = str(bcfg.get("model", "llama3.2:3b"))
    info: dict[str, Any] = {"model": model, "host": host, "digest": None}
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=5) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        entry = _select_ollama_entry(data.get("models", []), model)
        if entry is not None:
            info["digest"] = entry.get("digest")
            info["modified_at"] = entry.get("modified_at")
            info["size"] = entry.get("size")
    except Exception as e:  # noqa: BLE001 — provenance is best-effort, never fatal
        info["error"] = str(e)
    return info


def _claude_provenance(bcfg: dict) -> dict[str, Any]:
    """Record the configured Claude model and whether it is a pinned dated snapshot."""
    model = str(bcfg.get("model", "claude-sonnet-4-6"))
    is_dated = bool(_DATED_SNAPSHOT_RE.search(model))
    return {
        "model": model,
        "is_dated_snapshot": is_dated,
        "pin_warning": None if is_dated else (
            f"{model!r} is a rolling alias, not a dated snapshot; the paid arm "
            "may not reproduce if the provider re-points it. Pin a dated "
            "snapshot (…-YYYYMMDD) for a fully reproducible run."
        ),
    }


def _package_version() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("emergent-divergence")
        except PackageNotFoundError:
            pass
    except Exception:  # noqa: BLE001
        pass
    try:
        import emergent_divergence

        return getattr(emergent_divergence, "__version__", None)
    except Exception:  # noqa: BLE001
        return None


def collect_provenance(cfg: PipelineConfig) -> dict[str, Any]:
    """Reproducibility fingerprint: code version, platform, and per-backend model
    identity (git SHA, Ollama content digest, pinned/aliased Claude snapshot).

    Network/git calls are best-effort and never raise — missing data is recorded
    as ``None`` rather than aborting artifact writing.
    """
    import platform as _platform

    bcfg = cfg.backends_cfg
    prov: dict[str, Any] = {
        "git": _git_provenance(),
        "python": sys.version.split()[0],
        "platform": _platform.platform(),
        "package_version": _package_version(),
        "models": {},
    }
    if "ollama" in cfg.backends:
        prov["models"]["ollama"] = _ollama_provenance(bcfg.get("ollama", {}))
    if "claude" in cfg.backends:
        prov["models"]["claude"] = _claude_provenance(bcfg.get("claude", {}))
    if "stub" in cfg.backends:
        prov["models"]["stub"] = {
            "model": str(bcfg.get("stub", {}).get("model", "stub-v1"))
        }
    return prov


# ── stage 4: metrics + statistics ────────────────────────────────────────────────


def compute_metrics_and_stats(
    cfg: PipelineConfig, results: list[CellResult]
) -> tuple[list[dict], dict[str, dict], dict[str, Any]]:
    """Run per-cell metrics for every cell with data, then cross-cell statistics."""
    from emergent_divergence.embeddings import get_embedder
    from emergent_divergence.metrics.cell import analyze_cell
    from emergent_divergence.metrics.statistics import run_statistics

    embedder = get_embedder()
    summaries: list[dict] = []
    reports: dict[str, dict] = {}
    by_id = {r.cell_id: r for r in results}

    for res in results:
        log_path = Path(res.run_dir) / "events.jsonl"
        if not log_path.exists():
            continue
        out = analyze_cell(Path(res.run_dir), embedder)
        summary = out["summary"]
        # Fold the run-status fields in so results.csv carries provenance.
        cr = by_id.get(summary.get("cell_id", res.cell_id))
        if cr is not None:
            summary["status"] = cr.status
            summary["rounds_done"] = cr.rounds_done
            summary["cost_usd"] = cr.cost_usd
        summaries.append(summary)
        reports[res.cell_id] = out["report"]

    stats = run_statistics(summaries) if summaries else {"n_cells_total": 0, "backends": [],
                                                         "per_backend": {},
                                                         "cross_backend_conditionA": {}}
    return summaries, reports, stats


# ── artifacts ────────────────────────────────────────────────────────────────────

_CSV_FIELDS = [
    "cell_id", "backend", "condition", "seed", "status", "rounds", "rounds_done",
    "cost_usd", "provider", "model",
    "linguistic_mean_jsd", "h1_jsd_rho",
    "behavioral_divergence",
    "semantic_mean", "semantic_rho", "semantic_trend",
    "influence_available", "influence_mean_sem", "influence_gini",
    "influence_hub", "influence_hub_net_positive",
    "influence_precedes", "influence_lag_rho",
    "embedder_backend", "error",
]


def write_artifacts(
    cfg: PipelineConfig,
    *,
    preflight_info: dict,
    test_gate: dict,
    estimate: dict,
    reduction: dict,
    results: list[CellResult],
    summaries: list[dict],
    reports: dict[str, dict],
    stats: dict[str, Any],
    governor: CostGovernor,
    integrity: dict,
) -> dict[str, str]:
    """Write results.csv/json, statistics.json, manifest, and RESULTS_SUMMARY.md."""
    rd = cfg.report_dir
    rd.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    # results.csv
    csv_path = rd / "results.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for s in summaries:
            w.writerow({k: s.get(k) for k in _CSV_FIELDS})
    paths["results_csv"] = str(csv_path)

    # results.json
    (rd / "results.json").write_text(json.dumps(summaries, indent=2, default=str))
    paths["results_json"] = str(rd / "results.json")

    # statistics.json
    (rd / "statistics.json").write_text(json.dumps(stats, indent=2, default=str))
    paths["statistics_json"] = str(rd / "statistics.json")

    # per-cell rich reports (appendix material)
    (rd / "cell_reports.json").write_text(json.dumps(reports, indent=2, default=str))
    paths["cell_reports_json"] = str(rd / "cell_reports.json")

    # RUN_MANIFEST.json
    manifest = {
        "run_id": cfg.run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": collect_provenance(cfg),
        "config": cfg.to_serializable(),
        "preflight": preflight_info,
        "test_gate": test_gate,
        "cost_estimate": estimate,
        "reduction": reduction,
        "cost_actual": governor.snapshot(),
        "cells": [
            {"cell_id": r.cell_id, "status": r.status, "rounds_done": r.rounds_done,
             "rounds_total": r.rounds_total, "cost_usd": r.cost_usd, "error": r.error}
            for r in results
        ],
        "integrity": integrity,
    }
    (rd / "RUN_MANIFEST.json").write_text(json.dumps(manifest, indent=2, default=str))
    paths["manifest"] = str(rd / "RUN_MANIFEST.json")

    # RESULTS_SUMMARY.md
    (rd / "RESULTS_SUMMARY.md").write_text(
        _render_summary_md(cfg, results, stats, governor, integrity)
    )
    paths["summary_md"] = str(rd / "RESULTS_SUMMARY.md")

    return paths


def _render_summary_md(
    cfg: PipelineConfig,
    results: list[CellResult],
    stats: dict[str, Any],
    governor: CostGovernor,
    integrity: dict,
) -> str:
    lines: list[str] = []
    lines.append(f"# Results summary — run `{cfg.run_id}`\n")
    lines.append(f"Generated {datetime.now(timezone.utc).isoformat()}\n")

    status_counts: dict[str, int] = {}
    for r in results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
    lines.append("## Cells\n")
    lines.append(f"- Total cells: {len(results)}")
    for st, n in sorted(status_counts.items()):
        lines.append(f"- {st}: {n}")
    lines.append(f"- Spend: ${governor.spent_usd:.4f} / ${cfg.cap_usd:.2f} cap "
                 f"({governor.calls} calls)\n")

    lines.append("## Hypothesis verdicts\n")
    per_backend = stats.get("per_backend", {})
    if not per_backend:
        lines.append("_No cells produced analyzable data._\n")
    for backend, bstats in sorted(per_backend.items()):
        lines.append(f"### Backend: `{backend}` ({bstats.get('n_cells', 0)} cells)\n")
        hyps = bstats.get("hypotheses", {})
        lines.append("| Hypothesis | Verdict | Statement |")
        lines.append("| --- | --- | --- |")
        for hid in ("H1", "H2", "H3", "H4", "H5", "H-I1", "H-I2", "H-I3"):
            h = hyps.get(hid, {})
            lines.append(
                f"| {hid} | {h.get('verdict', '—')} | {h.get('statement', '')} |"
            )
        lines.append("")

    lines.append("## Integrity\n")
    lines.append(f"- OK: {integrity.get('ok')}")
    for k in ("expected", "attempted", "done", "skipped_due_to_cap",
              "skipped_unavailable", "failed", "analyzable"):
        if k in integrity:
            lines.append(f"- {k}: {integrity[k]}")
    lines.append("\n> Influence-delta measures **influence, not manipulation** "
                 "(see report Limitations).\n")
    return "\n".join(lines)


# ── stage 5: integrity ───────────────────────────────────────────────────────────


def integrity_check(
    cfg: PipelineConfig, results: list[CellResult], summaries: list[dict]
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    done = counts.get("done", 0)
    capped = counts.get("skipped_due_to_cap", 0)
    attempted = sum(1 for r in results if r.status != "skipped_unavailable")
    out = {
        "expected": len(results),
        "attempted": attempted,
        "done": done,
        "skipped_due_to_cap": capped,
        "skipped_unavailable": counts.get("skipped_unavailable", 0),
        "failed": counts.get("failed", 0),
        "analyzable": len(summaries),
        # The matrix is "ok" if at least one cell produced data and nothing
        # crashed the driver itself; partial completion is acceptable (§7).
        "ok": len(summaries) > 0,
    }
    return out


# ── orchestrator ────────────────────────────────────────────────────────────────


def run_pipeline(
    *,
    config_path: str | Path | None = "configs/pipeline.yaml",
    overrides: dict[str, Any] | None = None,
    skip_tests: bool = False,
    no_report: bool = False,
    verbose: bool = True,
) -> int:
    """Drive all stages. Returns a process exit code (0 = success)."""
    cfg = load_pipeline_config(config_path, overrides=overrides)
    governor = CostGovernor(cap_usd=cfg.cap_usd, prices=cfg.prices)

    def banner(msg: str) -> None:
        if verbose:
            print(f"\n{'=' * 64}\n  {msg}\n{'=' * 64}", flush=True)

    banner(f"PIPELINE  run_id={cfg.run_id}  smoke={cfg.smoke}")
    if verbose:
        print(f"  backends={cfg.backends} conditions={cfg.conditions} "
              f"seeds={cfg.seeds} rounds={cfg.rounds}", flush=True)

    # Stage 0 — preflight
    banner("Stage 0: preflight")
    pf = preflight(cfg)
    if verbose:
        print(f"  embedder: {pf['embedder'].get('backend')}", flush=True)
        for b, st in pf["backends"].items():
            mark = "OK " if st["available"] else "-- "
            print(f"  {mark}{b}: {st['reason']}", flush=True)
    if not any(st["available"] for st in pf["backends"].values()):
        print("  No backend available; nothing to run. Aborting.", flush=True)
        return 2

    # Embedder integrity gate — semantic divergence/influence are only *semantic*
    # on MiniLM; on the lexical hashing fallback they silently reduce to word
    # overlap. Abort real runs before any spend unless the operator explicitly
    # accepts lexical-only results.
    emb = pf.get("embedder", {})
    emb_backend = emb.get("backend")
    if emb_backend != "minilm" and not cfg.smoke and not _allow_hashing_fallback():
        print(
            f"  Embedder backend is {emb_backend!r}, not 'minilm' — semantic "
            "metrics would be lexical, not semantic. Aborting before any spend.\n"
            "  Fix: install sentence-transformers and cache the all-MiniLM-L6-v2 "
            "weights. To proceed anyway with explicitly lexical-only results, set "
            "ALLOW_HASHING_EMBEDDER=1.",
            flush=True,
        )
        return 4

    # Stage 1 — test gate (before any paid spend)
    banner("Stage 1: test gate")
    gate = run_test_gate(skip=skip_tests)
    if verbose:
        print(f"  pytest: {'PASS' if gate['passed'] else 'FAIL'} "
              f"(rc={gate.get('returncode')}) {gate.get('summary', '')}", flush=True)
    paid_backends = [b for b in cfg.backends
                     if b == "claude" and pf["backends"].get(b, {}).get("available")]
    if not gate["passed"] and paid_backends:
        print("  Tests failed and a paid backend is enabled — STOP before API budget.",
              flush=True)
        return 3
    if not gate["passed"]:
        print("  Tests failed but no paid backend — continuing (free run).", flush=True)

    # Stage 2 — cost estimate + auto-reduce
    banner("Stage 2: cost estimate")
    estimate = estimate_cost(cfg, governor)
    reduction = auto_reduce(cfg, governor)
    if verbose:
        print(f"  estimate: ${estimate['total_est_usd']:.4f} (cap ${cfg.cap_usd:.2f})",
              flush=True)
        if reduction["reduced"]:
            print(f"  auto-reduced: {', '.join(reduction['actions'])}", flush=True)
            print(f"  new estimate: ${reduction['final_estimate']['total_est_usd']:.4f}",
                  flush=True)

    # Stage 3 — run the matrix
    banner("Stage 3: run matrix")
    results = run_matrix(cfg, governor, pf, verbose=verbose)

    # Stage 4 — metrics + statistics
    banner("Stage 4: metrics + statistics")
    summaries, reports, stats = compute_metrics_and_stats(cfg, results)
    if verbose:
        print(f"  analyzed {len(summaries)} cells; backends={stats.get('backends')}",
              flush=True)

    # Stage 5 — integrity + artifacts
    banner("Stage 5: integrity + report")
    integrity = integrity_check(cfg, results, summaries)
    paths = write_artifacts(
        cfg, preflight_info=pf, test_gate=gate, estimate=estimate, reduction=reduction,
        results=results, summaries=summaries, reports=reports, stats=stats,
        governor=governor, integrity=integrity,
    )

    if not no_report:
        _maybe_build_report(cfg, paths, summaries, stats, reports, results)

    if verbose:
        print(f"\n  Report dir: {cfg.report_dir}", flush=True)
        print(f"  Summary:    {paths['summary_md']}", flush=True)
        print(f"  Cells: done={integrity['done']} capped={integrity['skipped_due_to_cap']} "
              f"failed={integrity['failed']} unavailable={integrity['skipped_unavailable']}",
              flush=True)
        print(f"  Spend: ${governor.spent_usd:.4f} / ${cfg.cap_usd:.2f}", flush=True)

    return 0 if integrity["ok"] else 1


def _maybe_build_report(
    cfg: PipelineConfig,
    paths: dict[str, str],
    summaries: list[dict],
    stats: dict[str, Any],
    reports: dict[str, dict],
    results: list[CellResult],
) -> None:
    """Render the full REPORT package if the report module is present (todo #7)."""
    try:
        from emergent_divergence import report as report_mod
    except Exception:  # noqa: BLE001 — report module not built yet
        return
    builder = getattr(report_mod, "build_report", None)
    if builder is None:
        return
    try:
        builder(
            report_dir=cfg.report_dir,
            run_id=cfg.run_id,
            summaries=summaries,
            stats=stats,
            reports=reports,
            results=[r.__dict__ for r in results],
        )
    except Exception as e:  # noqa: BLE001 — a report glitch must not fail the run
        print(f"  (report rendering skipped: {e})", flush=True)
