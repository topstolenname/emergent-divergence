"""Live, token-based spend tracking with a hard USD cap.

One ``CostGovernor`` is shared across the whole matrix. Free backends (``ollama``,
``stub``) have zero price, so only the Claude arm accrues spend. The pipeline
checks ``would_exceed`` *before* each paid call and records *real* usage after;
when the next call could cross ``cap_usd`` the cell is stopped and marked
``skipped_due_to_cap`` and the report discloses the truncation. State is JSON and
round-trips through the pipeline checkpoint so the cap stays global across resume.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Price:
    """Per-million-token prices for a backend."""

    input_per_mtok: float
    output_per_mtok: float


# Defaults; the paid arm's price is pinned in configs/pipeline.yaml and must be
# verified against current Anthropic listings before a paid run.
DEFAULT_PRICES: dict[str, Price] = {
    "claude": Price(input_per_mtok=3.0, output_per_mtok=15.0),
    "ollama": Price(input_per_mtok=0.0, output_per_mtok=0.0),
    "stub": Price(input_per_mtok=0.0, output_per_mtok=0.0),
}


class CostGovernor:
    """Tracks USD spend from token usage and enforces ``cap_usd``."""

    def __init__(
        self,
        cap_usd: float = 50.0,
        prices: dict[str, Price] | None = None,
    ):
        self.cap_usd = float(cap_usd)
        self.prices = dict(prices) if prices else dict(DEFAULT_PRICES)
        self.spent_usd: float = 0.0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.calls: int = 0

    # ── pricing ────────────────────────────────────────────────────────────────

    def cost_of(self, backend: str, input_tokens: int, output_tokens: int) -> float:
        price = self.prices.get(backend, Price(0.0, 0.0))
        return (
            input_tokens / 1_000_000 * price.input_per_mtok
            + output_tokens / 1_000_000 * price.output_per_mtok
        )

    def remaining(self) -> float:
        return max(0.0, self.cap_usd - self.spent_usd)

    def would_exceed(self, additional_usd: float) -> bool:
        """True if committing ``additional_usd`` more would cross the cap."""
        return (self.spent_usd + additional_usd) > self.cap_usd

    def can_afford(self, backend: str, est_input: int, est_output: int) -> bool:
        return not self.would_exceed(self.cost_of(backend, est_input, est_output))

    # ── recording ──────────────────────────────────────────────────────────────

    def record(self, backend: str, input_tokens: int, output_tokens: int) -> float:
        """Record real usage; returns the USD cost of this call."""
        cost = self.cost_of(backend, input_tokens, output_tokens)
        self.spent_usd += cost
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1
        return cost

    # ── state (resume) ───────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "cap_usd": self.cap_usd,
            "spent_usd": round(self.spent_usd, 6),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "calls": self.calls,
            "prices": {
                b: {"input_per_mtok": p.input_per_mtok, "output_per_mtok": p.output_per_mtok}
                for b, p in self.prices.items()
            },
        }

    def load_snapshot(self, snap: dict) -> None:
        self.cap_usd = float(snap.get("cap_usd", self.cap_usd))
        self.spent_usd = float(snap.get("spent_usd", 0.0))
        self.input_tokens = int(snap.get("input_tokens", 0))
        self.output_tokens = int(snap.get("output_tokens", 0))
        self.calls = int(snap.get("calls", 0))
        prices = snap.get("prices")
        if prices:
            self.prices = {
                b: Price(v["input_per_mtok"], v["output_per_mtok"])
                for b, v in prices.items()
            }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.snapshot(), indent=2))
        os.replace(tmp, path)

    @classmethod
    def from_file(cls, path: Path) -> "CostGovernor":
        gov = cls()
        snap = json.loads(Path(path).read_text())
        gov.load_snapshot(snap)
        return gov
