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
NAMES = {"strip": "Strip binaire Kalshi", "put_spread": "Put spread Deribit", "put": "Put vanille Deribit"}
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
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def report(data: Rows) -> str:
    dates = sorted(data["strip"])
    pnl = {k: np.array([data[k][d]["total_pnl"] for d in dates]) for k in data}
    out = [f"# Strip Kalshi contre options Deribit ({len(dates)} échéances, {dates[0]} → {dates[-1]})", "",
           "Même fenêtre partout : T0 = J−1 21:00 UTC → T1 = J 21:00 UTC. Deribit : journalière J+1 08:00 UTC valorisée à T1 "
           "(smile des trades [T−3 h, T] en log-moneyness, ± demi-spread mesuré), quantité q = n/p BTC exacte, p étant le pas des strikes Kalshi (250 $ sur 177 jours, 500 $ sur 30 ; "
           "Deribit impose en réalité un pas de 0,1 BTC). "
           "Hedge statique Hyperliquid, fundings réels. Strip Kalshi : σ DVOL, budget = prime du strike unique. "
           "Barème des frais : [deribit_friction.md](deribit_friction.md).", "",
           "## PnL total couvert par échéance ($)", "",
           "| Structure | Moyenne | Médiane | Écart-type | % jours gagnants | Cumul |", "|---|---|---|---|---|---|"]
    out += [f"| {NAMES[k]} | {fmt(v.mean())} | {fmt(float(np.median(v)))} | {fmt(v.std(ddof=1))} | "
            f"{fmt(100 * float((v > 0).mean()))} | {fmt(v.sum(), 0)} |" for k, v in pnl.items()]
    out += ["", "## Tests appariés contre le strip Kalshi", "",
            "| Comparaison | Écart moyen ($/jour) | p (t apparié) | IC 95 % bootstrap | Écart-type / strip | p Pitman-Morgan |",
            "|---|---|---|---|---|---|"]
    for k in ("put_spread", "put"):
        m, p, lo, hi, ratio, pm = paired(pnl["strip"], pnl[k])
        out.append(f"| {NAMES[k]} − strip | {fmt(m)} | {fmt(p, 3)} | [{fmt(lo)} ; {fmt(hi)}] | {fmt(ratio, 2)} | {"< 0,001" if pm < 0.001 else fmt(pm, 3)} |")
    out += ["", "## Friction sur les 7 mois", "",
            "Frais et spread de l'option seulement : les frais du hedge Hyperliquid (même perp des deux côtés) sont exclus. "
            "Kalshi paie ses frais une fois (le contrat va au règlement) et son spread à l'entrée ; Deribit paie frais et "
            "demi-spread à l'entrée et à la sortie (clôture à T1).", "",
            "| Plateforme | Frais ($) | Spread ($) | Friction totale ($) | Friction / prime | Friction par jour ($) |",
            "|---|---|---|---|---|---|"]
    for k, combo, label in (("strip", False, "Kalshi, strip"), ("put_spread", False, "Deribit, put spread (frais pleins)"),
                            ("put_spread", True, "Deribit, put spread (remise combo, non confirmée)"),
                            ("put", False, "Deribit, put vanille")):
        fr = friction_by_day(data, k, combo)
        fee, spr = sum(f for f, _ in fr.values()), sum(s for _, s in fr.values())
        prem = sum(r["premium"] if k == "strip" else r["premium_entry"] for r in data[k].values())
        out.append(f"| {label} | {fmt(fee, 0)} | {fmt(spr, 0)} | {fmt(fee + spr, 0)} | {fmt(100 * (fee + spr) / prem)} % | "
                   f"{fmt((fee + spr) / len(dates))} |")
    out += ["", "## Avant friction d'option (frais et spread rajoutés)", "",
            "| Structure | Moyenne ($) | Écart-type ($) |", "|---|---|---|"]
    for k, v in pnl.items():
        fr = friction_by_day(data, k)
        g = v + np.array([sum(fr[d]) for d in dates])
        out.append(f"| {NAMES[k]} | {fmt(g.mean())} | {fmt(g.std(ddof=1))} |")
    out += robustness(data, dates, pnl)
    out += ["", f"Bootstrap : {fmt(N_BOOT, 0)} tirages, graine {SEED}. Pitman-Morgan : corrélation entre (b − a) et (b + a), "
            "t de Student à n − 2 ddl."]
    return "\n".join(out) + "\n"


PERIODS = (("Mars-mai", "2026-03-01", "2026-05-31"), ("Juin-août", "2026-06-01", "2026-08-31"),
           ("Septembre-octobre", "2026-09-01", "2026-10-31"))


def pv(p: float) -> str:
    return "< 0,001" if p < 0.001 else fmt(p, 3)


def ttest(x: np.ndarray) -> tuple[float, float]:
    return float(x.mean()), float(stats.ttest_1samp(x, 0.0).pvalue)


def robustness(data: Rows, dates: list[str], pnl: dict[str, np.ndarray]) -> list[str]:
    """Sub-periods, extreme days, strike-grid mismatch and capital: every step-2 figure quoted in the README."""
    spread_k = np.array([data["put"][d]["kalshi_spread"] for d in dates])
    fr = {k: np.array([sum(friction_by_day(data, k)[d]) for d in dates]) for k in ("strip", "put_spread")}
    out = ["", "## Par sous-période (Deribit − strip, $/jour)", "",
           "| Période | n | Put spread − strip | p | Put vanille − strip | p | Spread Kalshi par jour ($) |",
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
    out += ["", "## Décomposition et robustesse (put spread − strip)", "",
            f"- Écart total : {fmt(float(diff.mean()))} $/jour, dont friction d'option {fmt(mf)} $ (p {pv(pf)}) "
            f"et reste avant friction {fmt(mr)} $ (p {pv(pr)}).",
            f"- Régression de l'écart quotidien sur le spread Kalshi du jour : écart = {fmt(float(icpt))} + {fmt(float(slope), 2)} × spread "
            f"(corrélation {fmt(float(np.corrcoef(spread_k, diff)[0, 1]), 2)}).",
            f"- Septembre-octobre sans les jours |S1/S0 − 1| > 5 % (n = {int((late & calm).sum())}) : {fmt(ml)} $/jour, p {pv(pl)}.",
            f"- Écart de payoff maximal dû à la grille Deribit (pas de 500 $) : |écart| médian {fmt(float(np.median(np.abs(gap))), 0)} $, "
            f"médiane signée {fmt(float(np.median(gap)), 0)} $ ; corrélation avec l'écart de PnL {fmt(float(np.corrcoef(gap, diff)[0, 1]), 2)}.",
            f"- Capital : le put spread est acheté (débit net médian {fmt(float(np.median(debit)), 0)} $, perte maximale de l'option) ; "
            f"nominal médian du hedge perp {fmt(float(np.median(notional)) / 1000)} k$."]
    return out


def figure(data: Rows) -> None:
    dates = sorted(data["strip"])
    x = [mdates.date2num(date.fromisoformat(d)) for d in dates]  # type: ignore[no-untyped-call]
    style = {"strip": (ORANGE, "-", "Binary Strip Kalshi"), "put_spread": (BLUE, "-", "Put spread Deribit"),
             "put": (BLUE, "--", "Vanilla Put Deribit")}
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    for k, (c, ls, lab) in style.items():
        fr = friction_by_day(data, k)
        a1.plot(x, np.cumsum([data[k][d]["total_pnl"] for d in dates]), color=c, ls=ls, lw=2, label=lab)
        a2.plot(x, np.cumsum([sum(fr[d]) for d in dates]), color=c, ls=ls, lw=2, label=lab)
    a1.axhline(0, color="#888888", lw=0.8)
    a1.set_ylabel("PnL cumulé couvert ($)")
    a1.set_title(f"Strip Kalshi contre options Deribit, n = {len(dates)} échéances journalières (hedge statique Hyperliquid)")
    a2.set_ylabel("Friction cumulée ($)\nfrais + spread d'option")
    a1.legend(loc="lower left", frameon=False)
    a2.legend(loc="upper left", frameon=False)
    for ax in (a1, a2):
        ax.grid(alpha=0.25)
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))  # type: ignore[no-untyped-call]
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
