"""Single-cell coordination loop: sync providers, checkpoint/resume, ablation hook.

A *cell* is one ``(backend, condition, seed)`` point of the 2×3×4 matrix. This
module runs exactly one cell to completion (or resumes a partial one). The matrix
driver in ``pipeline.py`` owns iterating over cells, the cost governor, and the
metrics/report stages.

What this runner does per cell:

- Runs ``num_rounds`` of multi-turn deliberation with starting-agent rotation,
  logging every message/memory-write/round boundary to ``events.jsonl``.
- On *subsampled* rounds (``influence_every_n``), runs a counterfactual influence
  probe: build a canonical context where every other agent's contribution is
  visible to a target, then ablate one source and re-generate the target. The
  factual vs. ablated samples are logged for the metrics layer to turn into the
  influence matrix (``rerun_target_with_ablation`` is the named hook).
- Is **resumable**: ``status.json`` tracks ``rounds_done``; the event log is the
  source of truth and memory is reconstructed from it on resume.
- Is **cost-gated**: before each paid generation it asks the governor; if the next
  call could cross the cap the cell stops and is marked ``skipped_due_to_cap``.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from emergent_divergence.agents.agent import Agent, AgentConfig
from emergent_divergence.cost.governor import CostGovernor
from emergent_divergence.logging_.events import ExperimentLogger, load_events
from emergent_divergence.memory.store import MemoryStore
from emergent_divergence.providers.base import Message, ModelProvider
from emergent_divergence.tasks.generator import TaskGenerator

# Condition -> (memory_enabled, role list). A: memory + weak priors;
# B: no memory + weak priors; C: memory + zero priors (generic identical agents).
CONDITIONS: dict[str, dict[str, Any]] = {
    "A": {"memory_enabled": True, "roles": ["proposer", "critic", "synthesizer"]},
    "B": {"memory_enabled": False, "roles": ["proposer", "critic", "synthesizer"]},
    "C": {"memory_enabled": True, "roles": ["generic", "generic", "generic"]},
}

_ABLATION_MARKER = "[no input]"
_CONTINUE_PROMPT = "Continue the discussion. Respond to what was said."
# Disjoint seed stream for the same-prompt null probe so its common-random-number
# samples never collide with the influence-probe seeds (which span
# ``seed + 7919*round_id + k``). A large prime keeps the two streams independent.
_NULL_SEED_OFFSET = 104729


@dataclass
class CellConfig:
    """Everything needed to run one matrix cell."""

    backend: str           # "ollama" | "claude" | "stub"
    condition: str         # "A" | "B" | "C"
    seed: int
    num_rounds: int = 50
    turns_per_round: int = 2
    temperature: float = 1.0
    max_tokens: int = 400
    num_agents: int = 3
    memory_max_entries: int = 200
    # Influence probe controls (the cost driver).
    influence_every_n: int = 5
    k_samples: int = 1          # MC samples for token-JSD (Claude uses 3).
    ablation: str = "neutral"   # "neutral" (replace with [no input]) | "drop".
    # Same-prompt resampling null: resample each agent on the *identical* task
    # prompt to log the intra-agent (pure-sampling) divergence floor that genuine
    # between-agent divergence must exceed.
    null_baseline: bool = True

    def cell_id(self) -> str:
        return f"{self.backend}_{self.condition}_seed{self.seed}"

    def null_k(self) -> int:
        """Samples for the null probe; >= 2 so an intra-agent spread is estimable."""
        return max(2, self.k_samples)


@dataclass
class CellResult:
    cell_id: str
    status: str                 # done | failed | skipped_due_to_cap
    rounds_done: int
    rounds_total: int
    cost_usd: float
    run_dir: str
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class CellRunner:
    """Runs (or resumes) a single matrix cell."""

    def __init__(
        self,
        config: CellConfig,
        provider: ModelProvider,
        run_dir: Path,
        *,
        governor: CostGovernor | None = None,
        verbose: bool = True,
    ):
        if config.condition not in CONDITIONS:
            raise ValueError(f"Unknown condition {config.condition!r}; use A/B/C.")
        self.config = config
        self.provider = provider
        self.governor = governor
        self.verbose = verbose
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.cond = CONDITIONS[config.condition]
        self.memory_enabled: bool = self.cond["memory_enabled"]
        roles = list(self.cond["roles"])
        if len(roles) < config.num_agents:
            roles = [roles[i % len(roles)] for i in range(config.num_agents)]
        self.roles = roles[: config.num_agents]

        self.status_path = self.run_dir / "status.json"
        self.events_path = self.run_dir / "events.jsonl"
        self.cell_id = config.cell_id()

        self.agents: list[Agent] = []
        self._cost_this_cell = 0.0

    # ── public entry point ─────────────────────────────────────────────────────

    def run(self) -> CellResult:
        rounds_done = self._resume_point()
        if rounds_done >= self.config.num_rounds:
            self._log_v(f"[{self.cell_id}] already complete ({rounds_done} rounds).")
            return self._result("done", rounds_done)

        # Truncate any events from an incomplete round, then rebuild agents/memory.
        self._truncate_events_to(rounds_done)
        self._build_agents()
        self._replay_memory_from_log(rounds_done)

        logger = ExperimentLogger(self.run_dir, self.cell_id, self.config.condition)
        task_gen = TaskGenerator(seed=self.config.seed)
        # Advance the task generator deterministically to the resume round.
        for r in range(rounds_done):
            task_gen.generate(r)

        if rounds_done == 0:
            logger.log(
                "experiment_config",
                backend=self.config.backend,
                condition=self.config.condition,
                seed=self.config.seed,
                roles=self.roles,
                memory_enabled=self.memory_enabled,
                num_agents=self.config.num_agents,
                num_rounds=self.config.num_rounds,
                turns_per_round=self.config.turns_per_round,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                influence_every_n=self.config.influence_every_n,
                k_samples=self.config.k_samples,
                ablation=self.config.ablation,
                null_baseline=self.config.null_baseline,
                null_k=self.config.null_k(),
                provider=self.provider.name,
                model=self.provider.model,
            )

        self._write_status("running", rounds_done)

        try:
            for round_id in range(rounds_done, self.config.num_rounds):
                task = task_gen.generate(round_id)
                if not self._afford_round(round_id):
                    logger.log("skipped_due_to_cap", round_id=round_id,
                               cost_usd=round(self._cost_this_cell, 6))
                    logger.close()
                    self._write_status("skipped_due_to_cap", round_id)
                    self._log_v(f"[{self.cell_id}] cap reached at round {round_id}; stopping.")
                    return self._result("skipped_due_to_cap", round_id)

                self._run_round(logger, round_id, task)

                if self._is_measured_round(round_id):
                    self._run_influence_probe(logger, round_id, task)
                    self._run_null_baseline_probe(logger, round_id, task)

                self._write_status("running", round_id + 1)
                self._log_v(
                    f"[{self.cell_id}] round {round_id + 1}/{self.config.num_rounds} "
                    f"done (cell cost ${self._cost_this_cell:.4f})"
                )
        except Exception as e:  # noqa: BLE001 — one cell failing must not abort matrix
            logger.log("experiment_error", error=str(e))
            logger.close()
            self._write_status("failed", self._resume_point(), error=str(e))
            self._log_v(f"[{self.cell_id}] FAILED: {e}")
            return self._result("failed", self._resume_point(), error=str(e))

        logger.close()
        self._write_status("done", self.config.num_rounds)
        return self._result("done", self.config.num_rounds)

    # ── deliberation ───────────────────────────────────────────────────────────

    def _run_round(self, logger: ExperimentLogger, round_id: int, task) -> None:
        logger.log("round_start", round_id=round_id, task_id=task.task_id,
                   claim=task.claim, domain=task.domain, difficulty=task.difficulty)

        conversation: list[Message] = [{"role": "user", "content": task.instructions}]

        num_agents = len(self.agents)
        offset = round_id % num_agents
        rotated = self.agents[offset:] + self.agents[:offset]

        for turn in range(self.config.turns_per_round):
            for agent in rotated:
                seed = self._turn_seed(round_id, turn, agent.agent_id)
                result = agent.respond(
                    conversation, round_id, task.task_id, seed=seed, turn=turn
                )
                self._record_cost(result["input_tokens"], result["output_tokens"])

                if agent.memory is not None and agent.memory_enabled:
                    recalled = result.get("recalled_memories", [])
                    logger.log(
                        "memory_read",
                        round_id=round_id,
                        task_id=task.task_id,
                        agent_id=agent.agent_id,
                        turn=turn,
                        count=len(recalled),
                        memory_size=agent.memory.count(),
                        entries=[
                            {
                                "round_id": m.get("round_id"),
                                "source": m.get("source", "self"),
                                "preview": (m.get("content", "") or "")[:80],
                            }
                            for m in recalled
                        ],
                    )

                logger.log(
                    "agent_message",
                    round_id=round_id,
                    task_id=task.task_id,
                    agent_id=agent.agent_id,
                    agent_role_bias=agent.role_bias,
                    turn=turn,
                    response_text=result["response_text"],
                    latency_s=result["latency_s"],
                    input_tokens=result["input_tokens"],
                    output_tokens=result["output_tokens"],
                    model=result["model"],
                    seed=seed,
                )

                tagged = f"[{agent.agent_id} ({agent.role_bias})]:\n{result['response_text']}"
                conversation.append({"role": "assistant", "content": tagged})
                conversation.append({"role": "user", "content": _CONTINUE_PROMPT})

                if agent.memory is not None and agent.memory_enabled:
                    summary = result["response_text"][:300]
                    agent.write_memory(round_id, summary, source="self")
                    logger.log(
                        "memory_write",
                        round_id=round_id,
                        task_id=task.task_id,
                        agent_id=agent.agent_id,
                        content=summary,
                        memory_size=agent.memory.count(),
                    )

        logger.log("round_end", round_id=round_id, task_id=task.task_id,
                   messages_in_round=len(conversation))

    # ── influence probe ──────────────────────────────────────────────────────────

    def _run_influence_probe(self, logger: ExperimentLogger, round_id: int, task) -> None:
        """Counterfactual probe: factual vs. source-ablated regenerations.

        For each target j we build a canonical context containing every *other*
        agent's base contribution, generate ``k_samples`` factual continuations,
        then for each source i!=j regenerate with i ablated. Both are logged; the
        metrics layer computes id_sem (embedding cosine) and id_tok (token JSD).
        """
        base_texts = self._base_contributions(round_id, task)

        logger.log("influence_probe_start", round_id=round_id, task_id=task.task_id,
                   agents=[a.agent_id for a in self.agents],
                   ablation=self.config.ablation, k_samples=self.config.k_samples)

        for target in self.agents:
            full_ctx = self._canonical_context(task, base_texts, exclude=None)
            factual = self._samples(target, round_id, full_ctx)
            logger.log(
                "influence_probe_factual",
                round_id=round_id, task_id=task.task_id,
                agent_id=target.agent_id, samples=factual,
            )
            for source in self.agents:
                if source.agent_id == target.agent_id:
                    continue
                ablated_ctx = self._canonical_context(
                    task, base_texts, exclude=source.agent_id
                )
                ablated = self._samples(target, round_id, ablated_ctx)
                logger.log(
                    "influence_probe_ablated",
                    round_id=round_id, task_id=task.task_id,
                    target=target.agent_id, source=source.agent_id,
                    samples=ablated,
                )

    def _run_null_baseline_probe(
        self, logger: ExperimentLogger, round_id: int, task
    ) -> None:
        """Same-prompt resampling null: the intra-agent variation floor.

        Each agent answers the *identical* bare task prompt ``null_k`` times. The
        spread among those samples is pure decoding stochasticity (temperature)
        given the agent's fixed disposition — the floor that genuine *between-agent*
        divergence must exceed to be more than sampling noise. The seed stream is
        offset from the influence probe so the two estimates are independent
        (common random numbers *within* the null, not shared *across* probes).

        Logging only: the metrics layer turns ``null_baseline_samples`` into an
        intra-agent JSD/cosine floor it can compare against the between-agent
        divergence series.
        """
        if not self.config.null_baseline:
            return
        k = self.config.null_k()
        ctx: list[Message] = [{"role": "user", "content": task.instructions}]
        seed_base = self.config.seed + _NULL_SEED_OFFSET
        logger.log(
            "null_baseline_start",
            round_id=round_id, task_id=task.task_id,
            k_samples=k, agents=[a.agent_id for a in self.agents],
        )
        for agent in self.agents:
            samples = self._samples(
                agent, round_id, ctx, k=k, seed_base=seed_base
            )
            logger.log(
                "null_baseline_samples",
                round_id=round_id, task_id=task.task_id,
                agent_id=agent.agent_id, samples=samples,
            )

    def rerun_target_with_ablation(
        self,
        target: str,
        source: str,
        round_id: int,
        *,
        k_samples: int | None = None,
        ablation: str | None = None,
        seed: int | None = None,
    ) -> dict[str, list[str]]:
        """Named counterfactual hook (brief §4.3).

        Self-contained: rebuilds the canonical context for ``round_id`` and returns
        both the factual continuations of ``target`` and the continuations with
        ``source`` ablated. ``ablation`` defaults to the cell's mode; ``seed``
        overrides the probe seed base (common random numbers across factual/ablated).
        """
        if not self.agents:
            self._build_agents()
        k = k_samples if k_samples is not None else self.config.k_samples
        abl = ablation if ablation is not None else self.config.ablation

        task_gen = TaskGenerator(seed=self.config.seed)
        task = None
        for r in range(round_id + 1):
            task = task_gen.generate(r)

        base_texts = self._base_contributions(round_id, task, seed=seed)
        target_agent = self._agent(target)

        full_ctx = self._canonical_context(task, base_texts, exclude=None)
        ablated_ctx = self._canonical_context(
            task, base_texts, exclude=source, ablation=abl
        )
        factual = self._samples(target_agent, round_id, full_ctx, k=k, seed_base=seed)
        ablated = self._samples(target_agent, round_id, ablated_ctx, k=k, seed_base=seed)
        return {"factual": factual, "ablated": ablated}

    def _base_contributions(
        self, round_id: int, task, *, seed: int | None = None
    ) -> dict[str, str]:
        """One representative response per agent to the task alone (for the context)."""
        out: dict[str, str] = {}
        ctx: list[Message] = [{"role": "user", "content": task.instructions}]
        for agent in self.agents:
            s = (seed if seed is not None else self.config.seed) + self._aidx(agent.agent_id)
            result = agent.respond(ctx, round_id, task.task_id, seed=s, turn=0)
            self._record_cost(result["input_tokens"], result["output_tokens"])
            out[agent.agent_id] = result["response_text"]
        return out

    def _canonical_context(
        self,
        task,
        base_texts: dict[str, str],
        *,
        exclude: str | None,
        ablation: str | None = None,
    ) -> list[Message]:
        """Task + every other agent's tagged base contribution (one ablated)."""
        abl = ablation if ablation is not None else self.config.ablation
        ctx: list[Message] = [{"role": "user", "content": task.instructions}]
        for agent in self.agents:
            body = base_texts.get(agent.agent_id, "")
            if agent.agent_id == exclude:
                if abl == "drop":
                    continue
                body = _ABLATION_MARKER
            tagged = f"[{agent.agent_id} ({agent.role_bias})]:\n{body}"
            ctx.append({"role": "assistant", "content": tagged})
        ctx.append({"role": "user", "content": _CONTINUE_PROMPT})
        return ctx

    def _samples(
        self,
        agent: Agent,
        round_id: int,
        context: list[Message],
        *,
        k: int | None = None,
        seed_base: int | None = None,
    ) -> list[str]:
        """Generate ``k`` continuations of ``agent`` over ``context`` (CRN seeds)."""
        k = k if k is not None else self.config.k_samples
        base = (seed_base if seed_base is not None else self.config.seed) + 7919 * round_id
        texts: list[str] = []
        for s in range(k):
            result = agent.respond(
                context, round_id, "probe", seed=base + s, turn=0
            )
            self._record_cost(result["input_tokens"], result["output_tokens"])
            texts.append(result["response_text"])
        return texts

    # ── cost ─────────────────────────────────────────────────────────────────────

    def _afford_round(self, round_id: int) -> bool:
        """Conservatively check whether a whole round + probe fits under the cap."""
        if self.governor is None:
            return True
        calls = self.config.turns_per_round * self.config.num_agents
        if self._is_measured_round(round_id):
            n = self.config.num_agents
            calls += n + (n * self.config.k_samples) + (n * (n - 1) * self.config.k_samples)
            if self.config.null_baseline:
                calls += n * self.config.null_k()
        est_in = self._estimate_input_tokens()
        est_out = self.config.max_tokens
        est = calls * self.governor.cost_of(self.config.backend, est_in, est_out)
        return not self.governor.would_exceed(est)

    def _record_cost(self, input_tokens: int, output_tokens: int) -> None:
        if self.governor is not None:
            self._cost_this_cell += self.governor.record(
                self.config.backend, input_tokens, output_tokens
            )

    def _estimate_input_tokens(self) -> int:
        # Rough: context grows with turns; use a flat conservative figure.
        return 600

    # ── agents / memory ────────────────────────────────────────────────────────

    def _build_agents(self) -> None:
        self.agents = []
        for i in range(self.config.num_agents):
            agent_id = f"agent_{i}"
            cfg = AgentConfig(
                agent_id=agent_id,
                role_bias=self.roles[i],
                memory_enabled=self.memory_enabled,
            )
            memory = (
                MemoryStore(agent_id=agent_id, persist_path=None,
                            max_entries=self.config.memory_max_entries)
                if self.memory_enabled else None
            )
            self.agents.append(
                Agent(cfg, self.provider, memory,
                      temperature=self.config.temperature,
                      max_tokens=self.config.max_tokens)
            )

    def _replay_memory_from_log(self, rounds_done: int) -> None:
        """Rebuild in-RAM memory from logged memory_write events (resume)."""
        if not self.memory_enabled or rounds_done == 0 or not self.events_path.exists():
            return
        for ev in load_events(self.events_path):
            if ev.get("event_type") != "memory_write":
                continue
            data = ev.get("data", {})
            agent_id = ev.get("agent_id") or data.get("agent_id")
            content = data.get("content", "")
            round_id = ev.get("round_id")
            agent = self._agent(agent_id) if agent_id else None
            if agent is not None and content:
                agent.write_memory(round_id, content, source="self")

    def _agent(self, agent_id: str) -> Agent:
        for a in self.agents:
            if a.agent_id == agent_id:
                return a
        raise KeyError(f"No agent {agent_id!r} in cell {self.cell_id}")

    @staticmethod
    def _aidx(agent_id: str) -> int:
        return int(agent_id.split("_")[1])

    def _turn_seed(self, round_id: int, turn: int, agent_id: str) -> int:
        return self.config.seed + round_id * 100 + turn * 10 + self._aidx(agent_id)

    def _is_measured_round(self, round_id: int) -> bool:
        return round_id % max(1, self.config.influence_every_n) == 0

    # ── status / resume ──────────────────────────────────────────────────────────

    def _resume_point(self) -> int:
        if not self.status_path.exists():
            return 0
        try:
            st = json.loads(self.status_path.read_text())
            return int(st.get("rounds_done", 0))
        except Exception:
            return 0

    def _truncate_events_to(self, rounds_done: int) -> None:
        """Drop events from rounds >= ``rounds_done`` (incomplete-round cleanup)."""
        if not self.events_path.exists():
            return
        if rounds_done == 0:
            self.events_path.unlink()
            return
        kept: list[str] = []
        with open(self.events_path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = ev.get("round_id")
                if rid is not None and rid >= rounds_done:
                    continue
                kept.append(line)
        tmp = self.events_path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(kept) + ("\n" if kept else ""))
        os.replace(tmp, self.events_path)

    def _write_status(self, status: str, rounds_done: int, *, error: str | None = None) -> None:
        payload = {
            "cell_id": self.cell_id,
            "backend": self.config.backend,
            "condition": self.config.condition,
            "seed": self.config.seed,
            "status": status,
            "rounds_done": rounds_done,
            "rounds_total": self.config.num_rounds,
            "cost_usd": round(self._cost_this_cell, 6),
            "updated": time.time(),
        }
        if error:
            payload["error"] = error
        tmp = self.status_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, self.status_path)

    def _result(self, status: str, rounds_done: int, *, error: str | None = None) -> CellResult:
        return CellResult(
            cell_id=self.cell_id,
            status=status,
            rounds_done=rounds_done,
            rounds_total=self.config.num_rounds,
            cost_usd=round(self._cost_this_cell, 6),
            run_dir=str(self.run_dir),
            error=error,
        )

    def _log_v(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)
