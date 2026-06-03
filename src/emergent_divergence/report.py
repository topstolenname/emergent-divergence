"""Report package builder (brief §8).

Turns the pipeline's per-cell summaries + cross-cell statistics into a
self-contained documentation bundle in ``data/reports/<run_id>/``:

* ``REPORT.html`` — self-contained: inline CSS, figures embedded as base64 SVG.
* ``REPORT.md``   — the same narrative in Markdown (figures linked from ``figures/``).
* ``REPORT.pdf``  — best-effort (rendered only if a PDF engine is available).
* ``figures/``    — vector SVG charts (dependency-free; no matplotlib required).

The narrative follows the required structure: Abstract → Methods → Results (per
backend) → Cross-backend → Hypothesis verdicts → Limitations → Reproducibility.

Figures are hand-rolled SVG so the bundle renders identically with a bare install
(numpy/scipy only); installing the ``analysis`` extra is *not* required.
"""

from __future__ import annotations

import base64
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Headline metrics that live on a comparable [0, 1]-ish scale (safe to bar-chart).
_DIVERGENCE_METRICS = [
    ("linguistic_mean_jsd", "Linguistic JSD"),
    ("semantic_mean", "Semantic cosine"),
    ("behavioral_divergence", "Behavioral div."),
]
_INFLUENCE_METRICS = [
    ("influence_mean_sem", "Influence μ (sem)"),
    ("influence_gini", "Influence Gini"),
]
_CONDITION_COLORS = {"A": "#2c6fbb", "B": "#b8b8b8", "C": "#e08a3c"}
_BACKEND_COLORS = ["#2c6fbb", "#3a9d5d", "#e08a3c", "#a65fb0"]
_HYP_ORDER = ["H1", "H2", "H3", "H4", "H5", "H-I1", "H-I2", "H-I3"]


# ── public entry points ──────────────────────────────────────────────────────


def build_report(
    *,
    report_dir: str | Path,
    run_id: str,
    summaries: list[dict],
    stats: dict[str, Any],
    reports: dict[str, dict] | None = None,
    results: list[dict] | None = None,
) -> dict[str, str]:
    """Render REPORT.md/html (+ best-effort pdf) and figures. Returns written paths."""
    rd = Path(report_dir)
    fig_dir = rd / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    reports = reports or {}
    results = results or []

    figures = _build_figures(summaries, stats, reports, fig_dir)

    md = _render_markdown(run_id, summaries, stats, results, figures)
    (rd / "REPORT.md").write_text(md)

    html_doc = _render_html(run_id, summaries, stats, results, figures)
    (rd / "REPORT.html").write_text(html_doc)

    paths = {
        "report_md": str(rd / "REPORT.md"),
        "report_html": str(rd / "REPORT.html"),
        "figures_dir": str(fig_dir),
    }
    pdf_path = _try_pdf(html_doc, rd / "REPORT.pdf")
    if pdf_path:
        paths["report_pdf"] = pdf_path
    return paths


def build_report_from_dir(report_dir: str | Path) -> dict[str, str]:
    """Regenerate the report from a run's existing JSON artifacts (no rerun)."""
    rd = Path(report_dir)
    summaries = _load_json(rd / "results.json", [])
    stats = _load_json(rd / "statistics.json", {})
    reports = _load_json(rd / "cell_reports.json", {})
    manifest = _load_json(rd / "RUN_MANIFEST.json", {})
    run_id = manifest.get("run_id", rd.name)
    results = manifest.get("cells", [])
    return build_report(
        report_dir=rd, run_id=run_id, summaries=summaries, stats=stats,
        reports=reports, results=results,
    )


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return default


# ── figures (hand-rolled SVG) ─────────────────────────────────────────────────


def _build_figures(
    summaries: list[dict], stats: dict[str, Any], reports: dict[str, dict], fig_dir: Path
) -> list[dict[str, str]]:
    """Produce the figure set; each figure is best-effort and isolated."""
    figs: list[dict[str, str]] = []
    per_backend = stats.get("per_backend", {})

    for backend, bstats in sorted(per_backend.items()):
        hcis = bstats.get("headline_cis", {})
        figs += _safe_fig(
            fig_dir, f"divergence_by_condition_{backend}",
            f"Divergence metrics by condition — {backend}",
            lambda: _grouped_bars_by_condition(hcis, _DIVERGENCE_METRICS),
        )
        figs += _safe_fig(
            fig_dir, f"influence_by_condition_{backend}",
            f"Influence metrics by condition — {backend}",
            lambda: _grouped_bars_by_condition(hcis, _INFLUENCE_METRICS),
        )
        mat = _representative_matrix(summaries, reports, backend)
        if mat is not None:
            agents, m = mat
            figs += _safe_fig(
                fig_dir, f"influence_heatmap_{backend}",
                f"Influence matrix M[source→target] (condition A) — {backend}",
                lambda a=agents, mm=m: _heatmap(a, mm),
            )

    cross = stats.get("cross_backend_conditionA", {})
    if cross and len(stats.get("backends", [])) >= 2:
        figs += _safe_fig(
            fig_dir, "cross_backend_conditionA",
            "Cross-backend headline means (condition A)",
            lambda: _grouped_bars_cross_backend(cross),
        )
    return figs


def _safe_fig(fig_dir: Path, fid: str, title: str, render) -> list[dict[str, str]]:
    try:
        svg = render()
        if not svg:
            return []
        (fig_dir / f"{fid}.svg").write_text(svg)
        return [{"id": fid, "title": title, "svg": svg, "file": f"figures/{fid}.svg"}]
    except Exception:  # noqa: BLE001 — a single bad figure never breaks the report
        return []


def _representative_matrix(
    summaries: list[dict], reports: dict[str, dict], backend: str
):
    """Pick a condition-A cell of ``backend`` with an influence matrix."""
    for s in summaries:
        if s.get("backend") != backend or s.get("condition") != "A":
            continue
        rep = reports.get(s.get("cell_id"), {})
        sem = (rep.get("influence") or {}).get("semantic") or {}
        m = sem.get("matrix")
        agents = sem.get("agents")
        if m and agents:
            return agents, m
    return None


def _collect(hcis: dict, metric: str):
    """For one metric, return ([conds], [means], [(lo,hi)]) across conditions A/B/C."""
    conds, means, errs = [], [], []
    for cond in ("A", "B", "C"):
        ci = (hcis.get(cond, {}) or {}).get(metric, {})
        if ci.get("mean") is None:
            continue
        conds.append(cond)
        means.append(float(ci["mean"]))
        lo = ci.get("ci_low")
        hi = ci.get("ci_high")
        errs.append((float(lo) if lo is not None else float(ci["mean"]),
                     float(hi) if hi is not None else float(ci["mean"])))
    return conds, means, errs


def _grouped_bars_by_condition(hcis: dict, metrics: list[tuple[str, str]]) -> str:
    groups = []  # (group_label, [(series_label, value, (lo,hi), color)])
    for key, label in metrics:
        conds, means, errs = _collect(hcis, key)
        if not conds:
            continue
        bars = [
            (c, means[i], errs[i], _CONDITION_COLORS.get(c, "#888"))
            for i, c in enumerate(conds)
        ]
        groups.append((label, bars))
    if not groups:
        return ""
    return _svg_grouped(groups, legend=[(c, _CONDITION_COLORS[c]) for c in ("A", "B", "C")])


def _grouped_bars_cross_backend(cross: dict) -> str:
    backends = sorted({b for m in cross.values() for b in m})
    colors = {b: _BACKEND_COLORS[i % len(_BACKEND_COLORS)] for i, b in enumerate(backends)}
    groups = []
    for key, label in _DIVERGENCE_METRICS + _INFLUENCE_METRICS:
        m = cross.get(key, {})
        bars = []
        for b in backends:
            ci = m.get(b, {})
            if ci.get("mean") is None:
                continue
            lo = ci.get("ci_low", ci["mean"])
            hi = ci.get("ci_high", ci["mean"])
            bars.append((b, float(ci["mean"]), (float(lo), float(hi)), colors[b]))
        if bars:
            groups.append((label, bars))
    if not groups:
        return ""
    return _svg_grouped(groups, legend=[(b, colors[b]) for b in backends])


def _svg_grouped(groups, *, legend, width: int = 720, height: int = 380) -> str:
    """Grouped vertical bar chart with error whiskers. Pure SVG string."""
    pad_l, pad_r, pad_t, pad_b = 56, 16, 28, 64
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    all_vals = [v for _, bars in groups for (_, v, (lo, hi), _) in bars for v in (v, lo, hi)]
    vmax = max(all_vals + [0.0])
    vmin = min(all_vals + [0.0])
    if vmax == vmin:
        vmax += 1.0
    span = vmax - vmin

    def y(val: float) -> float:
        return pad_t + plot_h * (1.0 - (val - vmin) / span)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
             f'font-family="system-ui,Arial,sans-serif" font-size="12">']
    parts.append(f'<rect width="{width}" height="{height}" fill="white"/>')

    # axes + zero line
    y0 = y(0.0)
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + plot_h}" '
                 f'stroke="#333" stroke-width="1"/>')
    parts.append(f'<line x1="{pad_l}" y1="{y0:.1f}" x2="{pad_l + plot_w}" y2="{y0:.1f}" '
                 f'stroke="#999" stroke-width="1" stroke-dasharray="3,3"/>')
    # y ticks (5)
    for t in range(6):
        val = vmin + span * t / 5
        yy = y(val)
        parts.append(f'<text x="{pad_l - 6}" y="{yy + 4:.1f}" text-anchor="end" '
                     f'fill="#555">{val:.2f}</text>')
        parts.append(f'<line x1="{pad_l - 3}" y1="{yy:.1f}" x2="{pad_l}" y2="{yy:.1f}" '
                     f'stroke="#333"/>')

    n_groups = len(groups)
    group_w = plot_w / n_groups
    for gi, (glabel, bars) in enumerate(groups):
        gx = pad_l + gi * group_w
        nb = len(bars)
        bar_w = min(46.0, (group_w * 0.8) / max(1, nb))
        block_w = bar_w * nb
        start = gx + (group_w - block_w) / 2
        for bi, (slabel, val, (lo, hi), color) in enumerate(bars):
            bx = start + bi * bar_w
            top = y(max(val, 0.0))
            bot = y(min(val, 0.0))
            parts.append(f'<rect x="{bx:.1f}" y="{top:.1f}" width="{bar_w - 4:.1f}" '
                         f'height="{abs(bot - top):.1f}" fill="{color}"/>')
            # error whisker
            if hi > lo:
                cx = bx + (bar_w - 4) / 2
                parts.append(f'<line x1="{cx:.1f}" y1="{y(hi):.1f}" x2="{cx:.1f}" '
                             f'y2="{y(lo):.1f}" stroke="#222" stroke-width="1"/>')
                parts.append(f'<line x1="{cx - 3:.1f}" y1="{y(hi):.1f}" x2="{cx + 3:.1f}" '
                             f'y2="{y(hi):.1f}" stroke="#222"/>')
                parts.append(f'<line x1="{cx - 3:.1f}" y1="{y(lo):.1f}" x2="{cx + 3:.1f}" '
                             f'y2="{y(lo):.1f}" stroke="#222"/>')
        parts.append(f'<text x="{gx + group_w / 2:.1f}" y="{pad_t + plot_h + 16}" '
                     f'text-anchor="middle" fill="#333">{html.escape(glabel)}</text>')

    # legend
    lx = pad_l
    ly = height - 18
    for label, color in legend:
        parts.append(f'<rect x="{lx}" y="{ly - 10}" width="11" height="11" fill="{color}"/>')
        parts.append(f'<text x="{lx + 15}" y="{ly}" fill="#333">{html.escape(str(label))}</text>')
        lx += 22 + 8 * len(str(label)) + 14
    parts.append("</svg>")
    return "".join(parts)


def _heatmap(agents: list[str], matrix: list[list[float]], width: int = 420) -> str:
    """Square influence heatmap M[source→target] with cell values."""
    n = len(agents)
    if n == 0:
        return ""
    pad = 90
    cell = min(70, (width - pad) / n)
    size = pad + cell * n
    flat = [v for row in matrix for v in row]
    vmax = max(flat + [1e-9])

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size:.0f} {size:.0f}" '
             f'font-family="system-ui,Arial,sans-serif" font-size="11">']
    parts.append(f'<rect width="{size:.0f}" height="{size:.0f}" fill="white"/>')
    for i in range(n):       # source = row
        for j in range(n):   # target = col
            v = float(matrix[i][j])
            inten = max(0.0, min(1.0, v / vmax))
            r = int(255 - inten * (255 - 44))
            g = int(255 - inten * (255 - 111))
            b = int(255 - inten * (255 - 187))
            x = pad + j * cell
            y = pad + i * cell
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" '
                         f'height="{cell:.1f}" fill="rgb({r},{g},{b})" stroke="#eee"/>')
            tc = "#fff" if inten > 0.55 else "#333"
            parts.append(f'<text x="{x + cell / 2:.1f}" y="{y + cell / 2 + 4:.1f}" '
                         f'text-anchor="middle" fill="{tc}">{v:.3f}</text>')
    for k, a in enumerate(agents):
        parts.append(f'<text x="{pad + k * cell + cell / 2:.1f}" y="{pad - 8}" '
                     f'text-anchor="middle" fill="#333">{html.escape(a)}</text>')
        parts.append(f'<text x="{pad - 8}" y="{pad + k * cell + cell / 2 + 4:.1f}" '
                     f'text-anchor="end" fill="#333">{html.escape(a)}</text>')
    parts.append(f'<text x="{pad + cell * n / 2:.1f}" y="{pad - 28}" text-anchor="middle" '
                 f'fill="#555">target →</text>')
    parts.append(f'<text x="22" y="{pad + cell * n / 2:.1f}" text-anchor="middle" '
                 f'fill="#555" transform="rotate(-90 22 {pad + cell * n / 2:.1f})">'
                 f'source →</text>')
    parts.append("</svg>")
    return "".join(parts)


# ── narrative content ──────────────────────────────────────────────────────────


def _fmt_ci(ci: dict) -> str:
    if not ci or ci.get("mean") is None:
        return "—"
    mean = ci["mean"]
    lo, hi = ci.get("ci_low"), ci.get("ci_high")
    n = ci.get("n", 0)
    if lo is None or hi is None or n < 2:
        return f"{mean:.3f} (n={n})"
    return f"{mean:.3f} [{lo:.3f}, {hi:.3f}] (n={n})"


def _abstract(run_id, summaries, stats, results) -> tuple[str, list[str]]:
    backends = stats.get("backends", [])
    n_cells = stats.get("n_cells_total", len(summaries))
    spend = 0.0
    capped = 0
    for r in results:
        spend += float(r.get("cost_usd", 0) or 0)
        if r.get("status") == "skipped_due_to_cap":
            capped += 1
    verdict_lines = []
    for b in backends:
        hyps = stats.get("per_backend", {}).get(b, {}).get("hypotheses", {})
        sup = sum(1 for h in hyps.values() if h.get("verdict") == "Supported")
        mix = sum(1 for h in hyps.values() if h.get("verdict") == "Mixed")
        verdict_lines.append(f"{b}: {sup} supported, {mix} mixed of {len(hyps)} hypotheses")
    emb = summaries[0].get("embedder_backend") if summaries else "unknown"
    text = (
        f"This run (`{run_id}`) measured emergent behavioral divergence and "
        f"cross-agent influence among three same-model agents (Proposer / Critic / "
        f"Synthesizer) coordinating over multi-turn claim-analysis tasks. "
        f"It analyzed **{n_cells} matrix cells** across backends {backends}, "
        f"conditions A/B/C, computing all semantic quantities with a shared "
        f"`{emb}` embedder so the two backends are directly comparable. "
        f"Total spend was **${spend:.2f}**"
        + (f" ({capped} cells truncated at the cost cap)." if capped else ".")
    )
    return text, verdict_lines


def _methods_md(summaries) -> str:
    emb = summaries[0].get("embedder_backend") if summaries else "shared MiniLM"
    return (
        "## Methods\n\n"
        "**Design.** A `backends × conditions × seeds` matrix. Conditions: "
        "**A** = memory + weak role priors; **B** = memory disabled (context reset each "
        "round) + weak priors; **C** = memory + zero role priors (generic identical agents). "
        "Each cell runs independent, checkpointed rounds of two-turn deliberation with "
        "starting-agent rotation.\n\n"
        "**Divergence metrics.** Linguistic divergence is the windowed mean pairwise "
        "Jensen-Shannon divergence (JSD, base 2) of agents' word-frequency distributions; "
        "its trend over rounds is a Spearman ρ (H1). Behavioral specialization scores how "
        "agents' message-act profiles differ (H2). Semantic divergence is the mean pairwise "
        f"cosine distance between agent response embeddings (shared `{emb}` embedder), with "
        "its round-trend as a Spearman ρ (H3).\n\n"
        "**Influence-delta.** On every Nth round a counterfactual probe builds a canonical "
        "context where each target sees all other agents, generates factual continuations, "
        "then re-generates with one source ablated. The influence of source *i* on target "
        "*j* is the change between the two continuation pools — semantically (`id_sem`, "
        "centroid cosine distance) and lexically (`id_tok`, token-JSD). Aggregated over "
        "rounds these form an influence matrix `M[source→target]`; row sums give outgoing "
        "influence, `A = M − Mᵀ` gives net directed influence, and the Gini of row sums "
        "measures concentration / hub formation (H-I2). A lagged Spearman correlation tests "
        "whether influence precedes divergence (H-I3).\n\n"
        "**Statistics.** Headline metrics are aggregated over seeds with percentile "
        "bootstrap 95% CIs; the memory contrast (A vs B) uses a bootstrap CI on the mean "
        "difference plus Cohen's *d*. Each hypothesis verdict is **data-driven**: "
        "*Supported* when the relevant CI excludes 0 in the hypothesized direction, "
        "*Mixed* when the point estimate points the right way but the CI straddles 0, "
        "*Not supported* otherwise.\n"
    )


def _headline_table_md(hcis: dict) -> str:
    rows = ["| Metric | A | B | C |", "| --- | --- | --- | --- |"]
    for key, label in _DIVERGENCE_METRICS + _INFLUENCE_METRICS + [
        ("semantic_rho", "Semantic ρ (trend)"),
    ]:
        cells = [_fmt_ci((hcis.get(c, {}) or {}).get(key, {})) for c in ("A", "B", "C")]
        rows.append(f"| {label} | {cells[0]} | {cells[1]} | {cells[2]} |")
    return "\n".join(rows)


def _hyp_table_md(hyps: dict) -> str:
    rows = ["| Hyp | Verdict | Statement | Evidence |", "| --- | --- | --- | --- |"]
    for hid in _HYP_ORDER:
        h = hyps.get(hid, {})
        ev = ""
        if "ci" in h:
            ev = _fmt_ci(h["ci"])
        elif "contrast" in h:
            c = h["contrast"]
            ev = (f"Δ={c.get('diff')}, d={c.get('cohens_d')}, "
                  f"[{c.get('ci_low')}, {c.get('ci_high')}]") if c.get("diff") is not None else "—"
        elif "gini_ci" in h:
            ev = f"Gini {_fmt_ci(h['gini_ci'])}"
        elif "precedes" in h:
            ev = f"proportion {h['precedes'].get('proportion')}"
        rows.append(f"| {hid} | **{h.get('verdict', '—')}** | "
                    f"{h.get('statement', '')} | {ev} |")
    return "\n".join(rows)


def _limitations_md(summaries, results) -> str:
    capped = sum(1 for r in results if r.get("status") == "skipped_due_to_cap")
    emb = summaries[0].get("embedder_backend") if summaries else ""
    items = [
        "- **Influence is not manipulation.** The influence-delta measures how much one "
        "agent's *presence* changes another's output under ablation. It does **not** "
        "measure intent, persuasion, or manipulation, and is never relabelled as such.",
        "- **Small samples.** CIs are bootstrap estimates over a handful of seeds; treat "
        "wide intervals and single-seed cells as suggestive, not conclusive.",
        "- **Claude non-determinism.** The paid backend does not honor a generation seed, "
        "so its variance is absorbed into the seed-level CIs rather than removed.",
    ]
    if emb and "fallback" in str(emb):
        items.append(
            "- **Embedder fallback.** Semantic quantities used the deterministic "
            f"`{emb}` embedder (sentence-transformers not installed). Numbers are "
            "internally consistent and comparable across backends, but are *not* MiniLM "
            "semantic distances; install the `analysis` extra for the primary embedder.")
    if capped:
        items.append(
            f"- **Cost truncation.** {capped} cell(s) stopped early at the cost cap; "
            "their rounds are partial and the affected estimates are correspondingly noisier.")
    return "## Limitations\n\n" + "\n".join(items) + "\n"


def _reproducibility_md(run_id, summaries, results) -> str:
    return (
        "## Reproducibility\n\n"
        f"- **Run id:** `{run_id}`\n"
        "- **Command:** `./run_all.sh` (or `python -m emergent_divergence pipeline`).\n"
        "- **Config:** `configs/pipeline.yaml` (single source of truth); environment "
        "overrides `ROUNDS`/`SEEDS`/`COST_CAP_USD`/`INFLUENCE_EVERY_N`/`K_SAMPLES`.\n"
        "- **Artifacts:** `results.csv`, `results.json`, `statistics.json`, "
        "`cell_reports.json`, `RUN_MANIFEST.json` (full config, prices, per-cell status, "
        "actual spend), and these figures.\n"
        "- **Determinism:** Ollama and the stub honor per-call seeds; the matrix is "
        "checkpointed per cell (`status.json`) and resumes without double-counting spend.\n"
    )


# ── markdown + html assembly ─────────────────────────────────────────────────


def _render_markdown(run_id, summaries, stats, results, figures) -> str:
    abstract, verdict_lines = _abstract(run_id, summaries, stats, results)
    out = [f"# Emergent Divergence — Report (`{run_id}`)\n",
           f"_Generated {datetime.now(timezone.utc).isoformat()}_\n",
           "## Abstract\n", abstract + "\n"]
    if verdict_lines:
        out.append("\n".join(f"- {v}" for v in verdict_lines) + "\n")
    out.append(_methods_md(summaries))

    fig_by_id = {f["id"]: f for f in figures}
    for backend, bstats in sorted(stats.get("per_backend", {}).items()):
        out.append(f"\n## Results — backend `{backend}`\n")
        out.append(f"_{bstats.get('n_cells', 0)} cells; "
                   f"condition n = {bstats.get('by_condition_n', {})}_\n")
        out.append("\n### Headline metrics (95% bootstrap CI)\n")
        out.append(_headline_table_md(bstats.get("headline_cis", {})))
        out.append("\n\n### Hypothesis verdicts\n")
        out.append(_hyp_table_md(bstats.get("hypotheses", {})))
        for fid in (f"divergence_by_condition_{backend}",
                    f"influence_by_condition_{backend}",
                    f"influence_heatmap_{backend}"):
            if fid in fig_by_id:
                f = fig_by_id[fid]
                out.append(f"\n![{f['title']}]({f['file']})\n*{f['title']}*\n")

    cross = stats.get("cross_backend_conditionA", {})
    if cross:
        out.append("\n## Cross-backend comparison (condition A)\n")
        out.append(_cross_table_md(cross, stats.get("backends", [])))
        if "cross_backend_conditionA" in fig_by_id:
            f = fig_by_id["cross_backend_conditionA"]
            out.append(f"\n![{f['title']}]({f['file']})\n*{f['title']}*\n")

    out.append("\n## Hypothesis verdicts (all backends)\n")
    out.append(_combined_hyp_table_md(stats))
    out.append("\n" + _limitations_md(summaries, results))
    out.append("\n" + _reproducibility_md(run_id, summaries, results))
    return "\n".join(out)


def _cross_table_md(cross: dict, backends: list[str]) -> str:
    header = "| Metric | " + " | ".join(backends) + " |"
    sep = "| --- " * (len(backends) + 1) + "|"
    rows = [header, sep]
    for key, label in _DIVERGENCE_METRICS + _INFLUENCE_METRICS:
        cells = [_fmt_ci(cross.get(key, {}).get(b, {})) for b in backends]
        rows.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _combined_hyp_table_md(stats: dict) -> str:
    backends = stats.get("backends", [])
    header = "| Hyp | Statement | " + " | ".join(backends) + " |"
    sep = "| --- | --- " + "| --- " * len(backends) + "|"
    rows = [header, sep]
    pb = stats.get("per_backend", {})
    for hid in _HYP_ORDER:
        stmt = ""
        verdicts = []
        for b in backends:
            h = pb.get(b, {}).get("hypotheses", {}).get(hid, {})
            stmt = stmt or h.get("statement", "")
            verdicts.append(h.get("verdict", "—"))
        rows.append(f"| {hid} | {stmt} | " + " | ".join(verdicts) + " |")
    return "\n".join(rows)


_CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:920px;margin:2rem auto;
padding:0 1rem;color:#1a1a1a;line-height:1.55}
h1{border-bottom:3px solid #2c6fbb;padding-bottom:.3rem}
h2{margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:.2rem}
h3{margin-top:1.4rem;color:#333}
table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.92rem}
th,td{border:1px solid #ccc;padding:.4rem .55rem;text-align:left;vertical-align:top}
th{background:#f0f4fa}
tr:nth-child(even) td{background:#fafbfc}
figure{margin:1.2rem 0;text-align:center}
figcaption{color:#666;font-size:.86rem;margin-top:.3rem}
code{background:#f3f3f3;padding:.1rem .3rem;border-radius:3px}
.verdict-Supported{color:#1a7d3c;font-weight:700}
.verdict-Mixed{color:#b8860b;font-weight:700}
.verdict-Not{color:#b03030;font-weight:700}
.note{background:#fff8e6;border-left:4px solid #e0a93c;padding:.6rem .9rem;margin:1rem 0}
"""


def _verdict_span(v: str) -> str:
    cls = {"Supported": "verdict-Supported", "Mixed": "verdict-Mixed"}.get(
        v, "verdict-Not" if v == "Not supported" else "")
    return f'<span class="{cls}">{html.escape(v)}</span>' if cls else html.escape(v)


def _embed_svg(svg: str) -> str:
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img alt="figure" src="data:image/svg+xml;base64,{b64}" style="max-width:100%"/>'


def _render_html(run_id, summaries, stats, results, figures) -> str:
    abstract, verdict_lines = _abstract(run_id, summaries, stats, results)
    fig_by_id = {f["id"]: f for f in figures}
    p: list[str] = []
    p.append("<!doctype html><html><head><meta charset='utf-8'>")
    p.append(f"<title>Emergent Divergence — {html.escape(run_id)}</title>")
    p.append(f"<style>{_CSS}</style></head><body>")
    p.append("<h1>Emergent Divergence — Report</h1>")
    p.append(f"<p><em>run <code>{html.escape(run_id)}</code> · generated "
             f"{datetime.now(timezone.utc).isoformat()}</em></p>")
    p.append("<h2>Abstract</h2>")
    p.append(f"<p>{_md_inline(abstract)}</p>")
    if verdict_lines:
        p.append("<ul>" + "".join(f"<li>{html.escape(v)}</li>" for v in verdict_lines) + "</ul>")
    p.append(_md_block_to_html(_methods_md(summaries)))

    for backend, bstats in sorted(stats.get("per_backend", {}).items()):
        p.append(f"<h2>Results — backend <code>{html.escape(backend)}</code></h2>")
        p.append(f"<p><em>{bstats.get('n_cells', 0)} cells; condition n = "
                 f"{html.escape(str(bstats.get('by_condition_n', {})))}</em></p>")
        p.append("<h3>Headline metrics (95% bootstrap CI)</h3>")
        p.append(_md_table_to_html(_headline_table_md(bstats.get("headline_cis", {}))))
        p.append("<h3>Hypothesis verdicts</h3>")
        p.append(_hyp_table_html(bstats.get("hypotheses", {})))
        for fid in (f"divergence_by_condition_{backend}",
                    f"influence_by_condition_{backend}",
                    f"influence_heatmap_{backend}"):
            if fid in fig_by_id:
                f = fig_by_id[fid]
                p.append(f"<figure>{_embed_svg(f['svg'])}"
                         f"<figcaption>{html.escape(f['title'])}</figcaption></figure>")

    cross = stats.get("cross_backend_conditionA", {})
    if cross:
        p.append("<h2>Cross-backend comparison (condition A)</h2>")
        p.append(_md_table_to_html(_cross_table_md(cross, stats.get("backends", []))))
        if "cross_backend_conditionA" in fig_by_id:
            f = fig_by_id["cross_backend_conditionA"]
            p.append(f"<figure>{_embed_svg(f['svg'])}"
                     f"<figcaption>{html.escape(f['title'])}</figcaption></figure>")

    p.append("<h2>Hypothesis verdicts (all backends)</h2>")
    p.append(_combined_hyp_table_html(stats))
    p.append('<div class="note"><strong>Honesty:</strong> the influence-delta measures '
             "<em>influence, not manipulation</em> — how much an agent's presence changes "
             "another's output under ablation, with no claim about intent.</div>")
    p.append(_md_block_to_html(_limitations_md(summaries, results)))
    p.append(_md_block_to_html(_reproducibility_md(run_id, summaries, results)))
    p.append("</body></html>")
    return "".join(p)


def _hyp_table_html(hyps: dict) -> str:
    rows = ["<table><tr><th>Hyp</th><th>Verdict</th><th>Statement</th></tr>"]
    for hid in _HYP_ORDER:
        h = hyps.get(hid, {})
        rows.append(f"<tr><td>{hid}</td><td>{_verdict_span(h.get('verdict', '—'))}</td>"
                    f"<td>{html.escape(h.get('statement', ''))}</td></tr>")
    rows.append("</table>")
    return "".join(rows)


def _combined_hyp_table_html(stats: dict) -> str:
    backends = stats.get("backends", [])
    pb = stats.get("per_backend", {})
    head = "".join(f"<th>{html.escape(b)}</th>" for b in backends)
    rows = [f"<table><tr><th>Hyp</th><th>Statement</th>{head}</tr>"]
    for hid in _HYP_ORDER:
        stmt = ""
        cells = []
        for b in backends:
            h = pb.get(b, {}).get("hypotheses", {}).get(hid, {})
            stmt = stmt or h.get("statement", "")
            cells.append(f"<td>{_verdict_span(h.get('verdict', '—'))}</td>")
        rows.append(f"<tr><td>{hid}</td><td>{html.escape(stmt)}</td>{''.join(cells)}</tr>")
    rows.append("</table>")
    return "".join(rows)


# ── tiny markdown helpers (tables + inline emphasis only) ────────────────────


def _md_inline(text: str) -> str:
    import re

    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _md_table_to_html(md: str) -> str:
    lines = [ln for ln in md.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return f"<p>{_md_inline(md)}</p>"
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    body = lines[2:]
    out = ["<table><tr>" + "".join(f"<th>{_md_inline(h)}</th>" for h in header) + "</tr>"]
    for ln in body:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        out.append("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in cells) + "</tr>")
    out.append("</table>")
    return "".join(out)


def _md_block_to_html(md: str) -> str:
    """Render a small markdown block: ## headings, tables, bullet lists, paragraphs."""
    html_parts: list[str] = []
    buf: list[str] = []
    table_buf: list[str] = []
    list_buf: list[str] = []

    def flush_para():
        if buf:
            html_parts.append(f"<p>{_md_inline(' '.join(buf))}</p>")
            buf.clear()

    def flush_table():
        if table_buf:
            html_parts.append(_md_table_to_html("\n".join(table_buf)))
            table_buf.clear()

    def flush_list():
        if list_buf:
            html_parts.append("<ul>" + "".join(f"<li>{_md_inline(i)}</li>"
                                                for i in list_buf) + "</ul>")
            list_buf.clear()

    for raw in md.splitlines():
        ln = raw.rstrip()
        if ln.startswith("|"):
            flush_para()
            flush_list()
            table_buf.append(ln)
            continue
        flush_table()
        if ln.startswith("## "):
            flush_para()
            flush_list()
            html_parts.append(f"<h2>{_md_inline(ln[3:])}</h2>")
        elif ln.startswith("### "):
            flush_para()
            flush_list()
            html_parts.append(f"<h3>{_md_inline(ln[4:])}</h3>")
        elif ln.startswith("- "):
            flush_para()
            list_buf.append(ln[2:])
        elif not ln.strip():
            flush_para()
            flush_list()
        else:
            buf.append(ln.strip())
    flush_para()
    flush_list()
    flush_table()
    return "".join(html_parts)


# ── best-effort PDF ───────────────────────────────────────────────────────────


def _try_pdf(html_doc: str, out_path: Path) -> str | None:
    """Render a PDF if an engine is available; otherwise skip silently (best-effort)."""
    try:
        from weasyprint import HTML  # type: ignore

        HTML(string=html_doc).write_pdf(str(out_path))
        return str(out_path)
    except Exception:  # noqa: BLE001
        pass
    import shutil
    import subprocess
    import tempfile

    wk = shutil.which("wkhtmltopdf")
    if wk:
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tf:
                tf.write(html_doc)
                tmp = tf.name
            subprocess.run([wk, "-q", tmp, str(out_path)], check=True, timeout=120)
            return str(out_path)
        except Exception:  # noqa: BLE001
            return None
    return None
