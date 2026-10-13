"""Multi-day report: single NO vs NO strip, DVOL vs Kalshi-implied sigma, over daily expiries.

Reads ``data/kalshi_multi/results.csv`` and writes ``docs/multi_day_report.md`` plus
``reports/multi_day.png``. Usage::

    python -m reports.multi_day [--csv PATH] [--md PATH] [--png PATH]
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
from matplotlib.axes import Axes
from scipy import stats

Arr = npt.NDArray[np.float64]

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
ORANGE = "#eb6834"
STRUCTURES = ("single", "strip")
SIGMAS = ("dvol", "kalshi_iv")
COLOR = {"single": INK, "strip": ORANGE}
STYLE = {"dvol": "-", "kalshi_iv": ":"}
N_BOOT = 10_000
SEED = 20261012
EXTREME_MOVE = 0.05
NUM_FIELDS = (
    "s0", "s1", "strip_legs", "kalshi_fee", "kalshi_pnl", "perp_pnl", "hl_fees",
    "funding_paid", "total_pnl", "hedged_std_hourly",
)  # fmt: skip

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Table:
    """Rows of results.csv, as columns sorted by (structure, sigma_source, date)."""

    date: list[str]
    structure: list[str]
    sigma: list[str]
    cols: dict[str, Arr]


@dataclass(frozen=True)
class Summary:
    n: int
    mean: float
    median: float
    std: float
    se: float
    sharpe_day: float
    sharpe_ann: float
    min: float
    max: float
    win_pct: float


@dataclass(frozen=True)
class Paired:
    """Paired comparison b - a on the same days."""

    n: int
    mean_diff: float
    t: float
    p: float
    ci_lo: float
    ci_hi: float


@dataclass(frozen=True)
class VarTest:
    """Variance of b relative to a, Pitman-Morgan test and bootstrap CI of the sd ratio."""

    var_ratio: float
    sd_ratio: float
    pm_t: float
    pm_p: float
    sd_ci_lo: float
    sd_ci_hi: float


def load(path: Path) -> Table:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: (r["structure"], r["sigma_source"], r["date"]))
    cols = {k: np.array([float(r[k]) for r in rows], dtype=np.float64) for k in NUM_FIELDS}
    return Table(
        [r["date"] for r in rows],
        [r["structure"] for r in rows],
        [r["sigma_source"] for r in rows],
        cols,
    )


def select(tbl: Table, structure: str, sigma: str, field: str, days: set[str] | None = None) -> Arr:
    """Column ``field`` for one (structure, sigma), date-ordered, optionally on a subset of days."""
    idx = [
        i
        for i in range(len(tbl.date))
        if tbl.structure[i] == structure
        and tbl.sigma[i] == sigma
        and (days is None or tbl.date[i] in days)
    ]
    return tbl.cols[field][idx]


def dates_of(tbl: Table, structure: str = "single", sigma: str = "dvol") -> list[str]:
    return [
        tbl.date[i]
        for i in range(len(tbl.date))
        if tbl.structure[i] == structure and tbl.sigma[i] == sigma
    ]


def extreme_days(tbl: Table, threshold: float = EXTREME_MOVE) -> set[str]:
    """Days with |s1/s0 - 1| > threshold."""
    ds = dates_of(tbl)
    s0, s1 = select(tbl, "single", "dvol", "s0"), select(tbl, "single", "dvol", "s1")
    return {d for d, a, b in zip(ds, s0, s1, strict=True) if abs(b / a - 1.0) > threshold}


def nine_leg_days(tbl: Table) -> set[str]:
    ds = dates_of(tbl, "strip")
    legs = select(tbl, "strip", "dvol", "strip_legs")
    return {d for d, g in zip(ds, legs, strict=True) if int(g) == 9}


def summarize(x: Arr) -> Summary:
    n = len(x)
    sd = float(np.std(x, ddof=1)) if n > 1 else float("nan")
    mean = float(np.mean(x))
    sharpe = mean / sd if sd > 0 else float("nan")
    return Summary(
        n=n,
        mean=mean,
        median=float(np.median(x)),
        std=sd,
        se=sd / float(np.sqrt(n)),
        sharpe_day=sharpe,
        sharpe_ann=sharpe * float(np.sqrt(365.0)),
        min=float(np.min(x)),
        max=float(np.max(x)),
        win_pct=100.0 * float(np.mean(x > 0)),
    )


def bootstrap_mean_ci(
    d: Arr, n_boot: int = N_BOOT, seed: int = SEED, level: float = 0.95
) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean, fixed seed."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    means = d[idx].mean(axis=1)
    a = (1.0 - level) / 2.0
    return float(np.quantile(means, a)), float(np.quantile(means, 1.0 - a))


def paired_test(a: Arr, b: Arr, n_boot: int = N_BOOT, seed: int = SEED) -> Paired:
    """Paired t-test and bootstrap CI of the mean of ``b - a``."""
    d = b - a
    res = stats.ttest_rel(b, a)
    lo, hi = bootstrap_mean_ci(d, n_boot, seed)
    return Paired(len(d), float(np.mean(d)), float(res.statistic), float(res.pvalue), lo, hi)


def variance_test(a: Arr, b: Arr, n_boot: int = N_BOOT, seed: int = SEED) -> VarTest:
    """Var(b)/Var(a) with Pitman-Morgan (paired variances) and bootstrap of the sd ratio."""
    n = len(a)
    r = float(np.corrcoef(b - a, b + a)[0, 1])
    t = r * float(np.sqrt((n - 2) / max(1.0 - r * r, 1e-300)))
    p = float(2.0 * stats.t.sf(abs(t), n - 2))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    ratio = b[idx].std(axis=1, ddof=1) / a[idx].std(axis=1, ddof=1)
    sd_ratio = float(np.std(b, ddof=1) / np.std(a, ddof=1))
    return VarTest(
        sd_ratio**2, sd_ratio, t, p, float(np.quantile(ratio, 0.025)), float(np.quantile(ratio, 0.975))
    )


def decomposition(tbl: Table, structure: str, sigma: str, days: set[str] | None = None) -> dict[str, float]:
    """Mean total_pnl split into Kalshi, perp, -HL fees, -funding."""

    def m(f: str) -> float:
        return float(np.mean(select(tbl, structure, sigma, f, days)))

    return {
        "kalshi_pnl": m("kalshi_pnl"),
        "perp_pnl": m("perp_pnl"),
        "-hl_fees": -m("hl_fees"),
        "-funding_paid": -m("funding_paid"),
        "total_pnl": m("total_pnl"),
        "kalshi_fee": m("kalshi_fee"),
    }


# ----------------------------------------------------------------------------- markdown


def _f(x: float, nd: int = 2) -> str:
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def _p(p: float) -> str:
    return "<0,001" if p < 0.001 else f"{p:.3f}".replace(".", ",")


def summary_table(tbl: Table, days: set[str] | None = None) -> list[str]:
    out = [
        "| Structure | σ | n | Moyenne | Médiane | Écart-type | Err.-type | Sharpe/j | Sharpe ann. "
        "| Min | Max | % gagnants | σ horaire moy. |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for st in STRUCTURES:
        for sg in SIGMAS:
            s = summarize(select(tbl, st, sg, "total_pnl", days))
            h = float(np.mean(select(tbl, st, sg, "hedged_std_hourly", days)))
            out.append(
                f"| {st} | {sg} | {s.n} | {_f(s.mean)} | {_f(s.median)} | {_f(s.std)} | {_f(s.se)} "
                f"| {_f(s.sharpe_day, 3)} | {_f(s.sharpe_ann, 2)} | {_f(s.min)} | {_f(s.max)} "
                f"| {_f(s.win_pct, 1)} | {_f(h)} |"
            )
    return out


def _paired_rows(
    tbl: Table, a: tuple[str, str], b: tuple[str, str], label: str, days: set[str] | None
) -> list[str]:
    rows: list[str] = []
    for fld, name in (("total_pnl", "total_pnl"), ("hedged_std_hourly", "σ horaire couvert")):
        x, y = select(tbl, a[0], a[1], fld, days), select(tbl, b[0], b[1], fld, days)
        pt = paired_test(x, y)
        rows.append(
            f"| {label} | {name} | {_f(pt.mean_diff)} | {_f(pt.t, 2)} | {_p(pt.p)} "
            f"| [{_f(pt.ci_lo)} ; {_f(pt.ci_hi)}] |"
        )
    return rows


def _var_row(tbl: Table, a: tuple[str, str], b: tuple[str, str], label: str, days: set[str] | None) -> str:
    vt = variance_test(select(tbl, a[0], a[1], "total_pnl", days), select(tbl, b[0], b[1], "total_pnl", days))
    return (
        f"| {label} | {_f(vt.var_ratio, 3)} | {_f(vt.sd_ratio, 3)} "
        f"| [{_f(vt.sd_ci_lo, 3)} ; {_f(vt.sd_ci_hi, 3)}] | {_f(vt.pm_t, 2)} | {_p(vt.pm_p)} |"
    )


def comparisons(tbl: Table, days: set[str] | None) -> list[str]:
    out = [
        "| Comparaison | Variable | Diff. moyenne | t | p | IC 95 % bootstrap |",
        "|---|---|---|---|---|---|",
    ]
    for sg in SIGMAS:
        out += _paired_rows(tbl, ("single", sg), ("strip", sg), f"strip − single ({sg})", days)
    for st in STRUCTURES:
        out += _paired_rows(tbl, (st, "dvol"), (st, "kalshi_iv"), f"kalshi_iv − dvol ({st})", days)
    out += [
        "",
        "| Comparaison | Var(b)/Var(a) | σ(b)/σ(a) | IC 95 % bootstrap σ(b)/σ(a) | t Pitman-Morgan | p |",
        "|---|---|---|---|---|---|",
    ]
    for sg in SIGMAS:
        out.append(_var_row(tbl, ("single", sg), ("strip", sg), f"strip / single ({sg})", days))
    for st in STRUCTURES:
        out.append(_var_row(tbl, (st, "dvol"), (st, "kalshi_iv"), f"kalshi_iv / dvol ({st})", days))
    return out


def decomposition_table(tbl: Table) -> list[str]:
    out = [
        "| Structure | σ | Kalshi | Perp | −Frais HL | −Funding | = PnL total | Frais Kalshi moy. |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for st in STRUCTURES:
        for sg in SIGMAS:
            d = decomposition(tbl, st, sg)
            out.append(
                f"| {st} | {sg} | {_f(d['kalshi_pnl'])} | {_f(d['perp_pnl'])} | {_f(d['-hl_fees'])} "
                f"| {_f(d['-funding_paid'])} | {_f(d['total_pnl'])} | {_f(d['kalshi_fee'])} |"
            )
    return out


def build_report(tbl: Table) -> str:
    ext = extreme_days(tbl)
    all_days = set(dates_of(tbl))
    ex_ext = all_days - ext
    nine = nine_leg_days(tbl)
    moves = {
        d: abs(b / a - 1.0)
        for d, a, b in zip(
            dates_of(tbl), select(tbl, "single", "dvol", "s0"), select(tbl, "single", "dvol", "s1"), strict=True
        )
    }
    ext_txt = ", ".join(f"{d} ({_f(100 * moves[d], 1)} %)" for d in sorted(ext))
    lines = [
        "# Validation multi-jours : strike unique contre binary strip",
        "",
        f"{len(all_days)} échéances journalières KXBTCD ({min(all_days)} → {max(all_days)}), "
        "2 structures × 2 sources de σ. PnL en $ par échéance, net de frais Kalshi, frais Hyperliquid et funding. "
        f"Bootstrap : {N_BOOT} tirages, graine {SEED}. Test apparié sur le même jour et la même σ.",
        "",
        f"Jours extrêmes (|S1/S0 − 1| > {100 * EXTREME_MOVE:.0f} %) : {ext_txt}. "
        f"Jours au pas de 250 $ (9 pattes) : {len(nine)} sur {len(all_days)}.",
        "",
        "## Statistiques par combinaison (total_pnl)",
        "",
        *summary_table(tbl),
        "",
        "## Décomposition de la moyenne de total_pnl",
        "",
        *decomposition_table(tbl),
        "",
        "## Tests appariés, tous les jours",
        "",
        "Différence = b − a (strip − single, ou kalshi_iv − dvol).",
        "",
        *comparisons(tbl, None),
        "",
        f"## Robustesse : sans les {len(ext)} jours extrêmes (n = {len(ex_ext)})",
        "",
        *summary_table(tbl, ex_ext),
        "",
        *comparisons(tbl, ex_ext),
        "",
        f"## Robustesse : jours à 9 pattes seulement (n = {len(nine)})",
        "",
        *summary_table(tbl, nine),
        "",
        *comparisons(tbl, nine),
        "",
    ]
    periods = (
        ("mars-mai", ("-03-", "-04-", "-05-")),
        ("juin-août", ("-06-", "-07-", "-08-")),
        ("septembre-octobre", ("-09-", "-10-")),
    )
    for title, months in periods:
        sub = {d for d in all_days if any(m in d for m in months)}
        if len(sub) > 3:
            lines += [f"## Sous-période {title} (n = {len(sub)})", "", *summary_table(tbl, sub), "", *comparisons(tbl, sub), ""]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- figure


def _style(ax: Axes, title: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=10, color=INK)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.tick_params(colors=INK_2, labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)


def make_figure(tbl: Table, out: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), facecolor=SURFACE)
    ax1, ax2, ax3 = axes
    ds = dates_of(tbl)
    x = np.arange(len(ds))
    for st in STRUCTURES:
        for sg in SIGMAS:
            ax1.plot(
                x, np.cumsum(select(tbl, st, sg, "total_pnl")), STYLE[sg], color=COLOR[st],
                lw=1.6, label=f"{st}, {sg}",
            )  # fmt: skip
    ax1.axhline(0, color=INK_2, lw=0.6)
    step = max(1, len(ds) // 6)
    ax1.set_xticks(x[::step], [d[5:] for d in ds[::step]])
    ax1.set_ylabel("Cumulative net PnL ($)", color=INK_2, fontsize=9)
    ax1.legend(frameon=False, fontsize=8)
    _style(ax1, "Cumulative PnL by expiry")

    a = select(tbl, "single", "dvol", "total_pnl")
    b = select(tbl, "strip", "dvol", "total_pnl")
    lim = (min(a.min(), b.min()) - 20, max(a.max(), b.max()) + 20)
    ax2.plot(lim, lim, color=INK_2, lw=0.8, ls="--", label="strip = single")
    ax2.scatter(a, b, s=26, color=ORANGE, edgecolor=INK, linewidth=0.5, zorder=3)
    ax2.set_xlim(lim)
    ax2.set_ylim(lim)
    ax2.set_xlabel("Single NO, daily PnL ($)", color=INK_2, fontsize=9)
    ax2.set_ylabel("Strip, daily PnL ($)", color=INK_2, fontsize=9)
    ax2.legend(frameon=False, fontsize=8, loc="upper left")
    _style(ax2, "Strip vs single, same day (DVOL sigma)")

    data = [select(tbl, st, sg, "total_pnl") for st in STRUCTURES for sg in SIGMAS]
    labels = [f"{st}\n{sg}" for st in STRUCTURES for sg in SIGMAS]
    cols = [COLOR[st] for st in STRUCTURES for _ in SIGMAS]
    pos = np.arange(1, len(data) + 1)
    bp = ax3.boxplot(data, positions=pos, widths=0.5, showfliers=False, patch_artist=True)
    rng = np.random.default_rng(SEED)
    for i, (box, med) in enumerate(zip(bp["boxes"], bp["medians"], strict=True)):
        box.set(facecolor=SURFACE, edgecolor=cols[i], linewidth=1.3)
        med.set(color=cols[i], linewidth=1.8)
        ax3.scatter(pos[i] + rng.uniform(-0.14, 0.14, len(data[i])), data[i], s=12, color=cols[i], alpha=0.7, zorder=3)
    for k in ("whiskers", "caps"):
        for j, ln in enumerate(bp[k]):
            ln.set(color=cols[j // 2], linewidth=1.0)
    ax3.axhline(0, color=INK_2, lw=0.6)
    ax3.set_xticks(pos, labels)
    ax3.set_ylabel("Daily net PnL ($)", color=INK_2, fontsize=9)
    _style(ax3, "Distribution of daily PnL")

    fig.tight_layout()
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=ROOT / "data" / "kalshi_multi" / "results.csv")
    ap.add_argument("--md", type=Path, default=ROOT / "docs" / "multi_day_report.md")
    ap.add_argument("--png", type=Path, default=ROOT / "reports" / "multi_day.png")
    args = ap.parse_args()
    tbl = load(args.csv)
    args.md.write_text(build_report(tbl), encoding="utf-8")
    make_figure(tbl, args.png)
    print(f"wrote {args.md} and {args.png}")


if __name__ == "__main__":
    main()
