"""Kalshi binary strip vs Deribit put spread / vanilla put over the 207 daily windows (step 2).

Reads ``data/kalshi_multi/results.csv`` (strip, DVOL) and ``data/deribit/results.csv``; writes
``docs/deribit_benchmark_report.md`` and ``reports/deribit_vs_kalshi.png``::

    python -m reports.deribit_compare
"""

from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.dates as mdates
from scipy import stats

KALSHI_CSV = Path("data/kalshi_multi/results.csv")
DERIBIT_CSV = Path("data/deribit/results.csv")
OUT_MD = Path("docs/deribit_benchmark_report.md")
OUT_PNG = Path("reports/deribit_vs_kalshi.png")
SEED, N_BOOT = 20261012, 10_000
ORANGE, BLUE = "#E8710A", "#1A73E8"
TEXT_COLS = ("date", "expiry", "structure", "sigma_source", "strikes", "spread_source_t0", "spread_source_t1")
NAMES = {"strip": "Kalshi binary strip", "put_spread": "Deribit put spread", "put": "Deribit vanilla put"}
Rows = dict[str, dict[str, dict[str, float]]]


def load() -> Rows:
    """{structure: {date: row}} for 'strip' (Kalshi, DVOL), 'put_spread' and 'put' (Deribit), on identical dates."""
    out: Rows = {"strip": {}, "put_spread": {}, "put": {}}
    with KALSHI_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["structure"] == "strip" and r["sigma_source"] == "dvol":
                out["strip"][r["date"]] = {k: float(v) for k, v in r.items() if k not in TEXT_COLS}
    with DERIBIT_CSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["structure"]][r["date"]] = {k: float(v) for k, v in r.items() if k not in TEXT_COLS}
    if not (set(out["strip"]) == set(out["put_spread"]) == set(out["put"])):
        raise ValueError("structures do not cover the same dates")
    for d, row in out["put"].items():  # the strip carried in the Deribit run must be the phase-1 strip, day by day
        if abs(row["kalshi_total_pnl"] - out["strip"][d]["total_pnl"]) > 0.01:
            raise ValueError(f"{d}: strip PnL differs between the two runs")
    return out


def friction_by_day(data: Rows, k: str, combo: bool = False) -> dict[str, tuple[float, float]]:
    """(fees, option spread) in $ per day; the Hyperliquid hedge fees are left out (same perp venue on both sides)."""
    if k == "strip":
        return {d: (r["kalshi_fee"], data["put"][d]["kalshi_spread"]) for d, r in data["strip"].items()}
    return {d: (r["fee_combo_variant"] if combo else r["fee_deribit_entry"] + r["fee_deribit_exit"], r["spread_cost"])
            for d, r in data[k].items()}


def paired(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float, float, float, float]:
    """Mean of b − a, paired-t p, bootstrap 95 % CI, std ratio b/a and its Pitman-Morgan p."""
    d = b - a
    idx = np.random.default_rng(SEED).integers(0, len(d), (N_BOOT, len(d)))
    lo, hi = np.percentile(d[idx].mean(axis=1), [2.5, 97.5])
    r = float(np.corrcoef(b - a, b + a)[0, 1])
    t = r * math.sqrt((len(d) - 2) / (1 - r * r))
    return (float(d.mean()), float(stats.ttest_rel(b, a).pvalue), float(lo), float(hi),
            float(b.std(ddof=1) / a.std(ddof=1)), float(2 * stats.t.sf(abs(t), len(d) - 2)))


def fmt(x: float, nd: int = 1) -> str:
    return f"{x:,.{nd}f}"


def report(data: Rows) -> str:
    dates = sorted(data["strip"])
    pnl = {k: np.array([data[k][d]["total_pnl"] for d in dates]) for k in data}
    out = [f"# Kalshi strip against Deribit options ({len(dates)} expiries, {dates[0]} → {dates[-1]})", "",
           "Same window for every structure: T0 = day J−1 at 21:00 UTC, T1 = day J at 21:00 UTC. Deribit: daily expiry at "
           "J+1 08:00 UTC, valued at T1 (trade smile over [T−3 h, T] in log-moneyness, plus or minus the measured half-spread). "
           "Quantity q = n/p BTC exactly, where p is the Kalshi strike step (250 $ on 177 days and 500 $ on 30). "
           "Deribit in practice requires a 0.1 BTC step. "
           "Static Hyperliquid hedge, actual fundings. Kalshi strip: DVOL sigma, budget = premium of the single strike. "
           "Fee schedule: [deribit_friction.md](deribit_friction.md).", "",
           "## Total PnL covered per expiry ($)", "",
           "| Structure | Mean | Median | Std dev | % winning days | Cumulative |", "|---|---|---|---|---|---|"]
    out += [f"| {NAMES[k]} | {fmt(v.mean())} | {fmt(float(np.median(v)))} | {fmt(v.std(ddof=1))} | "
            f"{fmt(100 * float((v > 0).mean()))} | {fmt(v.sum(), 0)} |" for k, v in pnl.items()]
    out += ["", "## Paired tests against the Kalshi strip", "",
            "| Comparison | Mean gap ($/day) | p (paired t) | 95% bootstrap CI | Std dev / strip | Pitman-Morgan p |",
            "|---|---|---|---|---|---|"]
    for k in ("put_spread", "put"):
        m, p, lo, hi, ratio, pm = paired(pnl["strip"], pnl[k])
        out.append(f"| {NAMES[k]} − strip | {fmt(m)} | {fmt(p, 3)} | [{fmt(lo)}, {fmt(hi)}] | {fmt(ratio, 2)} | {'< 0.001' if pm < 0.001 else fmt(pm, 3)} |")
    out += ["", "## Friction over the 7 months", "",
            "Option fees and spread only: the Hyperliquid hedge fees (same perp on both sides) are excluded. "
            "Kalshi pays its fee once (the contract goes to settlement) and its spread at entry; Deribit pays fee and "
            "half-spread at entry and at exit (closed at T1).", "",
            "| Platform | Fees ($) | Spread ($) | Total friction ($) | Friction / premium | Friction per day ($) |",
            "|---|---|---|---|---|---|"]
    for k, combo, label in (("strip", False, "Kalshi, strip"), ("put_spread", False, "Deribit, put spread (full fees)"),
                            ("put_spread", True, "Deribit, put spread (combo rebate, unconfirmed)"),
                            ("put", False, "Deribit, vanilla put")):
        fr = friction_by_day(data, k, combo)
        fee, spr = sum(f for f, _ in fr.values()), sum(s for _, s in fr.values())
        prem = sum(r["premium"] if k == "strip" else r["premium_entry"] for r in data[k].values())
        out.append(f"| {label} | {fmt(fee, 0)} | {fmt(spr, 0)} | {fmt(fee + spr, 0)} | {fmt(100 * (fee + spr) / prem)} % | "
                   f"{fmt((fee + spr) / len(dates))} |")
    out += ["", "## Before option friction (fees and spread added back)", "",
            "| Structure | Mean ($) | Std dev ($) |", "|---|---|---|"]
    for k, v in pnl.items():
        fr = friction_by_day(data, k)
        g = v + np.array([sum(fr[d]) for d in dates])
        out.append(f"| {NAMES[k]} | {fmt(g.mean())} | {fmt(g.std(ddof=1))} |")
    out += robustness(data, dates, pnl)
    out += ["", f"Bootstrap: {fmt(N_BOOT, 0)} draws, seed {SEED}. Pitman-Morgan: correlation between (b − a) and (b + a), "
            "Student t with n − 2 degrees of freedom."]
    return "\n".join(out) + "\n"


PERIODS = (("March-May", "2026-03-01", "2026-05-31"), ("June-August", "2026-06-01", "2026-08-31"),
           ("September-October", "2026-09-01", "2026-10-31"))


def pv(p: float) -> str:
    return "< 0.001" if p < 0.001 else fmt(p, 3)


def ttest(x: np.ndarray) -> tuple[float, float]:
    return float(x.mean()), float(stats.ttest_1samp(x, 0.0).pvalue)


def robustness(data: Rows, dates: list[str], pnl: dict[str, np.ndarray]) -> list[str]:
    """Sub-periods, extreme days, strike-grid mismatch and capital: every step-2 figure quoted in the README."""
    spread_k = np.array([data["put"][d]["kalshi_spread"] for d in dates])
    fr = {k: np.array([sum(friction_by_day(data, k)[d]) for d in dates]) for k in ("strip", "put_spread")}
    out = ["", "## By sub-period (Deribit − strip, $/day)", "",
           "| Period | n | Put spread − strip | p | Vanilla put − strip | p | Kalshi spread per day ($) |",
           "|---|---|---|---|---|---|---|"]
    for lab, a, b in PERIODS:
        m = np.array([a <= d <= b for d in dates])
        (ms, ps), (mv, pvv) = ttest((pnl["put_spread"] - pnl["strip"])[m]), ttest((pnl["put"] - pnl["strip"])[m])
        out.append(f"| {lab} | {int(m.sum())} | {fmt(ms)} | {pv(ps)} | {fmt(mv)} | {pv(pvv)} | {fmt(float(spread_k[m].mean()))} |")
    diff = pnl["put_spread"] - pnl["strip"]
    fdiff = fr["strip"] - fr["put_spread"]
    (mf, pf), (mr, pr) = ttest(fdiff), ttest(diff - fdiff)
    move = np.array([abs(data["strip"][d]["s1"] / data["strip"][d]["s0"] - 1) for d in dates])
    calm = move <= 0.05
    late = np.array([d >= PERIODS[2][1] for d in dates])
    ml, pl = ttest(diff[late & calm])
    slope, icpt = np.polyfit(spread_k, diff, 1)
    gap = np.array([data["put_spread"][d]["max_payoff_gap_usd"] for d in dates])
    debit = np.array([data["put_spread"][d]["premium_entry"] for d in dates])
    notional = np.array([data["put_spread"][d]["perp_notional_usd"] for d in dates])
    out += ["", "## Breakdown (put spread − strip)", "",
            f"- Total gap: {fmt(float(diff.mean()))} $/day, of which option friction {fmt(mf)} $ (p {pv(pf)}) "
            f"and the remainder before friction {fmt(mr)} $ (p {pv(pr)}).",
            f"- Regression of the daily gap on the same-day Kalshi spread: gap = {fmt(float(icpt))} + {fmt(float(slope), 2)} × spread "
            f"(correlation {fmt(float(np.corrcoef(spread_k, diff)[0, 1]), 2)}).",
            f"- September-October without the days with |S1/S0 − 1| > 5% (n = {int((late & calm).sum())}): {fmt(ml)} $/day, p {pv(pl)}.",
            f"- Maximum payoff gap from the Deribit strike grid (500 $ step): median |gap| {fmt(float(np.median(np.abs(gap))), 0)} $, "
            f"median signed gap {fmt(float(np.median(gap)), 0)} $, and correlation with the PnL gap {fmt(float(np.corrcoef(gap, diff)[0, 1]), 2)}.",
            f"- Capital: the put spread is bought (median net debit {fmt(float(np.median(debit)), 0)} $, maximum loss is the option premium); "
            f"median perp hedge notional {fmt(float(np.median(notional)) / 1000)} k$."]
    return out


def figure(data: Rows) -> None:
    dates = sorted(data["strip"])
    x = [mdates.date2num(date.fromisoformat(d)) for d in dates]  # type: ignore[no-untyped-call]
    style = {"strip": (ORANGE, "-", "Kalshi binary strip"), "put_spread": (BLUE, "-", "Deribit put spread"),
             "put": (BLUE, "--", "Deribit vanilla put")}
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    for k, (c, ls, lab) in style.items():
        fr = friction_by_day(data, k)
        a1.plot(x, np.cumsum([data[k][d]["total_pnl"] for d in dates]), color=c, ls=ls, lw=2, label=lab)
        a2.plot(x, np.cumsum([sum(fr[d]) for d in dates]), color=c, ls=ls, lw=2, label=lab)
    a1.axhline(0, color="#888888", lw=0.8)
    a1.set_ylabel("Cumulative hedged PnL ($)")
    a1.set_title(f"Kalshi strip against Deribit options, n = {len(dates)} daily expiries (static Hyperliquid hedge)")
    a2.set_ylabel("Cumulative friction ($)\nfees + option spread")
    a1.legend(loc="lower left", frameon=False)
    a2.legend(loc="upper left", frameon=False)
    for ax in (a1, a2):
        ax.grid(alpha=0.25)
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))  # type: ignore[no-untyped-call]
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)


def main() -> None:
    data = load()
    OUT_MD.write_text(report(data).replace(" $", " $"), encoding="utf-8")  # GitHub reads "<space>$" as math
    figure(data)
    print(OUT_MD, OUT_PNG)


if __name__ == "__main__":
    main()
