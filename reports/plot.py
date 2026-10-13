"""CV figure: BTC price, Polymarket-leg delta vs Hyperliquid hedge, and net delta per strategy.

Reads a journal written by ``sim.ledger`` and writes a
300 dpi PNG plus a Markdown PnL table. Usage::

    python -m reports.plot data/journal_<run>.jsonl [--out reports/hedge.png] [--strike K]
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.axes import Axes

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
STRATEGY_COLOR = {"dynamic": ORANGE, "static": AQUA}
PNL_FIELDS = ("pnl_pm", "pnl_hl", "fees_pm", "fees_hl", "funding", "pnl_total")


@dataclass
class Series:
    """Mark records of one strategy, as parallel columns."""

    t: list[datetime] = field(default_factory=list)
    s: list[float] = field(default_factory=list)
    delta_pm: list[float] = field(default_factory=list)
    hl: list[float] = field(default_factory=list)
    net: list[float] = field(default_factory=list)
    last: dict[str, float] = field(default_factory=dict)


def load(path: Path) -> tuple[dict[str, Series], list[datetime]]:
    """Parse marks per strategy and the timestamps of kill-switch fills."""
    series: dict[str, Series] = defaultdict(Series)
    kills: list[datetime] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            t = datetime.fromtimestamp(rec["ts_ms"] / 1000, tz=UTC)
            if rec["type"] == "fill" and str(rec["tag"]).startswith("kill"):
                kills.append(t)
            elif rec["type"] == "mark":
                sr = series[rec["strategy"]]
                sr.t.append(t)
                sr.s.append(rec["S"])
                sr.delta_pm.append(rec["delta_pm_btc"])
                sr.hl.append(rec["hl_position"])
                sr.net.append(rec["net_delta_btc"])
                sr.last = {k: float(rec[k]) for k in PNL_FIELDS}
    if not series:
        raise ValueError(f"no mark records in {path}")
    return dict(series), kills


def color_of(name: str) -> str:
    """Fixed colour per strategy family, so a missing strategy never repaints the other."""
    for key, col in STRATEGY_COLOR.items():
        if key in name.lower():
            return col
    return INK_2


def _style(ax: Axes, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=9)
    ax.tick_params(colors=INK_2, labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


def plot(series: dict[str, Series], kills: list[datetime], out: Path, strike: float | None) -> None:
    """Render the three stacked panels sharing one time axis (no dual y-axis)."""
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 8.5), sharex=True,
                                        gridspec_kw={"height_ratios": [1, 1.2, 1]})
    fig.patch.set_facecolor(SURFACE)
    ref = next(iter(series.values()))

    ax1.plot(ref.t, ref.s, color=BLUE, lw=1.4)
    if strike is not None:
        ax1.axhline(strike, color=INK_2, lw=0.9, ls=(0, (4, 3)))
        ax1.annotate(f"strike K = {strike:,.0f}", (0.005, strike), xycoords=("axes fraction", "data"),
                     xytext=(0, 4), textcoords="offset points", fontsize=8, color=INK_2)
    _style(ax1, "BTC (Hyperliquid mid, $)")
    ax1.set_title("BTC price", loc="left", fontsize=10, color=INK)

    ax2.plot(ref.t, ref.delta_pm, color=BLUE, lw=1.4, label="Polymarket leg  +QΔ")
    for name, sr in series.items():
        ax2.step(sr.t, sr.hl, where="post", color=color_of(name), lw=1.4, label=f"Hyperliquid hedge ({name})")
    ax2.axhline(0, color=INK_2, lw=0.6)
    _style(ax2, "BTC")
    ax2.set_title("Binary delta vs perp position", loc="left", fontsize=10, color=INK)
    ax2.legend(loc="center left", bbox_to_anchor=(0, 0.62), fontsize=8, frameon=False, ncols=3)

    hedged: list[float] = []
    for name, sr in series.items():
        ax3.plot(sr.t, sr.net, color=color_of(name), lw=1.4, label=name)
        start = next((i for i, (n, d) in enumerate(zip(sr.net, sr.delta_pm)) if abs(n) < 0.1 * abs(d)), len(sr.net))
        hedged += [abs(n) for n in sr.net[start:]]
    if hedged:
        lim = 1.15 * max(hedged)
        ax3.set_ylim(-lim, lim)
        ax3.annotate("off-scale: entry, before the first hedge fill", (0.005, 0.97), xycoords="axes fraction",
                     va="top", fontsize=8, color=INK_2)
    ax3.axhline(0, color=INK_2, lw=0.6)
    _style(ax3, "net Δ (BTC)")
    ax3.set_title("Net portfolio delta", loc="left", fontsize=10, color=INK)
    ax3.legend(loc="lower left", fontsize=8, frameon=False, ncols=2)

    if kills:
        kill = min(kills)
        for ax in (ax1, ax2, ax3):
            ax.axvline(kill, color="#d03b3b", lw=0.9, ls=(0, (2, 2)))
        ax1.annotate("gamma kill-switch  T−2h", (mdates.date2num(kill), 1), xycoords=("data", "axes fraction"),
                     xytext=(-4, -10), textcoords="offset points", ha="right", fontsize=8, color=INK_2)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=UTC))
    ax3.set_xlabel("time (UTC)", color=INK_2, fontsize=9)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=300, facecolor=SURFACE)
    plt.close(fig)


def pnl_table(series: dict[str, Series]) -> str:
    """Final PnL decomposition per strategy, in USD, as a Markdown table."""
    head = "| strategy | " + " | ".join(PNL_FIELDS) + " |"
    rows = [head, "|" + "---|" * (len(PNL_FIELDS) + 1)]
    for name, sr in series.items():
        rows.append(f"| {name} | " + " | ".join(f"{sr.last[k]:+.2f}" for k in PNL_FIELDS) + " |")
    return "\n".join(rows) + "\n"


def frontier(sweep_csv: Path, out: Path) -> None:
    """Cost of hedging (−PnL, $) against residual risk (σ of net delta, BTC), one point per run of the sweep."""
    with sweep_csv.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    fig.patch.set_facecolor(SURFACE)
    ladder = [r for r in rows if r["threshold"] not in ("default", "static")]
    xs = [float(r["std_net_delta_btc"]) for r in ladder]
    ys = [-float(r["pnl_total"]) for r in ladder]
    ax.plot(xs, ys, "-o", color=ORANGE, lw=1.4, ms=5, mec=SURFACE, mew=1.5, label="dynamic, σ implied, threshold ladder")
    labels: dict[tuple[float, float], list[str]] = {}
    for r, x, y in zip(ladder, xs, ys):
        labels.setdefault((round(x, 5), round(y, 1)), []).append(f"{float(r['threshold']):g}")
    for (x, y), ths in labels.items():
        ax.annotate(" = ".join(ths) + " BTC", (x, y), xytext=(6, 2), textcoords="offset points", fontsize=8, color=INK)
    marks = {"dvol": ("s", BLUE, "dynamic, σ DVOL"), "ewma": ("D", INK_2, "dynamic, σ EWMA")}
    for r in rows:
        if r["threshold"] == "default" and r["sigma_source"] in marks:
            m, col, lab = marks[r["sigma_source"]]
            ax.plot(float(r["std_net_delta_btc"]), -float(r["pnl_total"]), m, color=col, ms=7, mec=SURFACE, mew=1.5, label=lab)
        elif r["threshold"] == "static":
            ax.plot(float(r["std_net_delta_btc"]), -float(r["pnl_total"]), "^", color=AQUA, ms=8, mec=SURFACE, mew=1.5, label="static (one maker order)")
    _style(ax, "hedging cost  −PnL ($)")
    ax.set_xlabel("residual risk  σ(net Δ) (BTC)", color=INK_2, fontsize=9)
    ax.set_title("Friction vs directional risk", loc="left", fontsize=10, color=INK)
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=300, facecolor=SURFACE)
    plt.close(fig)


def compare_kalshi(single_dir: Path, strip_dir: Path, out: Path) -> None:
    """Hedged PnL path of the single-strike trade against the binary strip (hourly MtM, before fees).

    Each directory holds ``path.json`` (ts_ms, S, kalshi_mtm, perp_mtm) and ``result.json`` (net ``total_pnl``).
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True, gridspec_kw={"height_ratios": [1, 1.4]})
    fig.patch.set_facecolor(SURFACE)
    runs = (("single strike", single_dir, INK), ("binary strip", strip_dir, ORANGE))
    for label, d, col in runs:
        path = json.loads((d / "path.json").read_text(encoding="utf-8"))
        net = json.loads((d / "result.json").read_text(encoding="utf-8"))["total_pnl"]
        t = [datetime.fromtimestamp(p["ts_ms"] / 1000, tz=UTC) for p in path]
        if label == "single strike":
            ax1.plot(t, [p["S"] for p in path], color=BLUE, lw=1.4)
        pnl = [p["kalshi_mtm"] + p["perp_mtm"] for p in path]
        ax2.plot(t, pnl, color=col, lw=1.6, label=f"{label}  (net of all fees at close: {net:+.2f} $)")
        ax2.plot(t, [p["kalshi_mtm"] for p in path], color=col, lw=0.9, ls=(0, (3, 2)), alpha=0.7)
    ax2.plot([], [], color=INK_2, lw=0.9, ls=(0, (3, 2)), label="dashed: Kalshi leg alone")
    ax2.axhline(0, color=INK_2, lw=0.6)
    _style(ax1, "BTC ($)")
    ax1.set_title("BTC (Hyperliquid perp)", loc="left", fontsize=10, color=INK)
    _style(ax2, "hedged PnL ($, before fees)")
    ax2.set_title("Long NO + long perp hedge: one strike vs 9-strike strip", loc="left", fontsize=10, color=INK)
    ax2.legend(fontsize=8, frameon=False, loc="lower left")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M", tz=UTC))
    fig.tight_layout()
    fig.savefig(out, dpi=300, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("journal", type=Path, nargs="?")
    ap.add_argument("--kalshi-compare", nargs=2, type=Path, metavar=("SINGLE_DIR", "STRIP_DIR"),
                    help="overlay the two Kalshi backtests -> reports/kalshi_strip_vs_single.png")
    ap.add_argument("--out", type=Path, default=Path("reports/hedge.png"))
    ap.add_argument("--strike", type=float, default=None)
    ap.add_argument("--sweep", type=Path, default=None, help="sweep CSV from `run.py sweep` -> frontier PNG")
    args = ap.parse_args()
    if args.kalshi_compare is not None:
        single_dir, strip_dir = args.kalshi_compare
        compare_kalshi(single_dir, strip_dir, Path("reports/kalshi_strip_vs_single.png"))
    if args.journal is None:
        return
    series, kills = load(args.journal)
    plot(series, kills, args.out, args.strike)
    if args.sweep is not None:
        frontier(args.sweep, args.out.with_name(args.out.stem + "_frontier.png"))
    table = pnl_table(series)
    args.out.with_suffix(".md").write_text(table, encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
