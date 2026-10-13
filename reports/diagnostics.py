"""Three diagnostic figures on the 207 Kalshi KXBTCD daily expiries, plus ``reports/diagnostics.json``.

    python -m reports.diagnostics

1. ``gamma_zoom.png``: BTC and the Hyperliquid perp size over one day, static hedge vs hourly rebalanced -Delta.
   Day rule (deterministic): the date maximising |S1/S0 - 1| over all days, S0 = open of the T0 candle, S1 = close
   of the T1 - 1h candle (= price at T1, as in the backtests); ties go to the earliest date.
2. ``iv_vs_rv.png``: IV = DVOL at T0 (decimal, results.csv) vs RV = sample std (ddof=1) of the 24 hourly log
   returns of HL closes (first return from the T0 open) x sqrt(24*365).
3. ``funding_pnl.png``: cumulative funding PnL = -cumsum(funding_paid; > 0 = cost of the long) per structure.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from backtest import kalshi_one_trade as one
from backtest import kalshi_strip_trade as strip
from backtest.multi_day import CONTRACTS, N_STRIKES, ROOT, configure
from core.math_engine import SECONDS_PER_YEAR, binary_call_delta
from reports.deribit_compare import BLUE, ORANGE
from reports.presentation import GREY, fr

OUT = Path("reports")
DERIBIT_CSV = Path("data/deribit/results.csv")
DARK_ORANGE = "#8A4B08"
HOURS = 24
Rows = list[dict[str, str]]


def read_rows(path: Path) -> Rows:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def candles(day: str) -> list[dict[str, Any]]:
    """The 24 hourly candles of [T0, T1): the cache also holds the T1 candle, which closes an hour after the exit."""
    p = ROOT / day / "single" / "hl_candles_1h.json"
    return sorted(json.loads(p.read_text(encoding="utf-8")), key=lambda c: int(c["t"]))[:HOURS]


def day_move(cs: list[dict[str, Any]]) -> float:
    return float(cs[-1]["c"]) / float(cs[0]["o"]) - 1


def realized_vol(s0: float, closes: list[float]) -> float:
    """Annualised std of the hourly log returns of ``closes``, the first one measured from the T0 open."""
    px = [s0, *closes]
    rets = [math.log(b / a) for a, b in zip(px, px[1:], strict=False)]
    return statistics.stdev(rets) * math.sqrt(HOURS * 365)


def hourly_hedge(legs: list[tuple[float, float]], sigma: float, prices: list[float]) -> list[float]:
    """Perp size (BTC) re-set each hour: -Sum n_i * Delta_NO_i, with Delta_NO = -binary_call_delta, T = time left to T1."""
    step = (one.T1_MS - one.T0_MS) / HOURS
    return [-sum(n * -binary_call_delta(s, k, sigma, (one.T1_MS - one.T0_MS - h * step) / 1000 / SECONDS_PER_YEAR)
                 for k, n in legs) for h, s in enumerate(prices)]


def run_day(day: str) -> dict[str, Any]:
    """Backtest both structures under DVOL (caches only) and add the hourly hedge of each."""
    configure(date.fromisoformat(day))
    raw1, raw2 = one.load(refresh=False), strip.load(refresh=False, n_strikes=N_STRIKES)
    dvol = float(raw1["dvol"][-1][4]) / 100
    r1, _ = one.backtest(raw1, CONTRACTS, sigma_override=dvol)
    r2, _ = strip.backtest(raw2, r1.kalshi_premium, sigma_override=dvol)
    opens = [float(c["o"]) for c in raw1["candles"]][:HOURS]
    legs = {"single": [(r1.strike, r1.contracts)], "strip": [(g.strike, float(g.contracts)) for g in r2.legs]}
    return {"prices": opens + [r1.hl_exit], "sigma": dvol, "legs": legs,
            "static": {"single": r1.hedge_btc, "strip": r2.hedge_btc},
            "hourly": {k: hourly_hedge(v, dvol, opens) for k, v in legs.items()},
            "strikes": {"atm": r1.strike, "lo": min(g.strike for g in r2.legs), "hi": max(g.strike for g in r2.legs)}}


def gamma_zoom(day: str, d: dict[str, Any], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.5))
    t = list(range(HOURS + 1))
    ax.plot(t, d["prices"], color=GREY, lw=1.8, label="BTC (Hyperliquid, horaire)")
    for key, lab in (("atm", "strike ATM"), ("lo", "borne basse du strip"), ("hi", "borne haute du strip")):
        ax.axhline(d["strikes"][key], color=ORANGE, lw=0.7, ls=":", alpha=0.8)
        ax.annotate(f"{lab} {fr(d['strikes'][key])}", (t[-1], d["strikes"][key]), fontsize=7, color=ORANGE,
                    xytext=(-3, 2), textcoords="offset points", ha="right")
    ax.set_ylabel("BTC ($)")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fr(v)))
    ax2 = ax.twinx()
    for key, color, name in (("single", DARK_ORANGE, "strike unique"), ("strip", ORANGE, "strip")):
        ax2.hlines(d["static"][key], t[0], t[-1], color=color, lw=2.2, label=f"Hedge statique, {name} ({fr(d['static'][key], 3)} BTC)")
        ax2.step(t[:HOURS], d["hourly"][key], where="post", color=color, lw=1.3, ls="--", marker="o", ms=3,
                 label=f"Rebalancement horaire, {name}")
    ax2.axhline(0, color=GREY, lw=0.6)
    ax2.set_ylabel("Position perp Hyperliquid (BTC, long > 0)")
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fr(v, 2)))
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", bbox_to_anchor=(0, -0.1), ncol=2, frameon=False, fontsize=8)
    ax.set_xticks(range(0, HOURS + 1, 3))
    ax.set_xlabel("Heures depuis J−1 21:00 UTC (T0) jusqu'à J 21:00 (T1)")
    ax.set_title(f"Mécanique du gamma — {date.fromisoformat(day):%d/%m/%Y}, BTC {100 * (d['prices'][-1] / d['prices'][0] - 1):+.2f} % sur la journée".replace(".", ","))
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def iv_rv(rows: Rows, out: Path) -> dict[str, float]:
    days = [r["date"] for r in rows if r["structure"] == "single" and r["sigma_source"] == "dvol"]
    iv = [float(r["dvol"]) for r in rows if r["structure"] == "single" and r["sigma_source"] == "dvol"]
    rv = [realized_vol(float(candles(d)[0]["o"]), [float(c["c"]) for c in candles(d)]) for d in days]
    gap = [a - b for a, b in zip(iv, rv, strict=True)]
    x = [date.fromisoformat(d) for d in days]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    a1.plot(x, [100 * v for v in iv], color=ORANGE, lw=1.4, label="IV (DVOL à T0)")
    a1.plot(x, [100 * v for v in rv], color=GREY, lw=1.1, label="RV (24 rendements horaires HL)")
    a1.set_ylabel("Volatilité annualisée (%)")
    a1.legend(frameon=False)
    a2.bar(x, [100 * g for g in gap], color=[ORANGE if g > 0 else BLUE for g in gap], width=1.0)
    mean, med, pct = statistics.fmean(gap), statistics.median(gap), 100 * sum(g > 0 for g in gap) / len(gap)
    for v, lab, ls in ((mean, "moyenne", "-"), (med, "médiane", "--")):
        a2.axhline(100 * v, color="k", lw=1, ls=ls, label=f"{lab} : {fr(100 * v, 1)} pts")
    a2.axhline(0, color=GREY, lw=0.6)
    a2.set_ylabel("IV − RV (points de vol)")
    a2.set_ylim(-75, 65)
    a2.legend(frameon=False, loc="upper right", ncol=2)
    a2.set_title(f"IV > RV {fr(pct, 1)} % des jours (orange = vol payée trop chère)", fontsize=9)
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))  # type: ignore[no-untyped-call]
    for a in (a1, a2):
        a.grid(alpha=0.25)
    a1.set_title(f"Prime de risque : IV − RV sur {len(days)} échéances")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return {"iv_mean": statistics.fmean(iv), "iv_median": statistics.median(iv), "rv_mean": statistics.fmean(rv),
            "rv_median": statistics.median(rv), "gap_mean": mean, "gap_median": med, "pct_iv_gt_rv": pct}


def funding(kalshi: Rows, deribit: Rows, out: Path) -> dict[str, Any]:
    series = {
        "single": ("Kalshi strike unique", DARK_ORANGE, "-", [r for r in kalshi if r["structure"] == "single" and r["sigma_source"] == "dvol"]),
        "strip": ("Kalshi strip", ORANGE, "-", [r for r in kalshi if r["structure"] == "strip" and r["sigma_source"] == "dvol"]),
        "put_spread": ("Deribit put spread", BLUE, "-", [r for r in deribit if r["structure"] == "put_spread"]),
        "put": ("Deribit put", BLUE, "--", [r for r in deribit if r["structure"] == "put"]),
    }
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7), gridspec_kw={"height_ratios": [3, 2]})
    stats: dict[str, Any] = {}
    for key, (lab, color, ls, rows) in series.items():
        paid = [float(r["funding_paid"]) for r in rows]
        cum = [-sum(paid[: i + 1]) for i in range(len(paid))]
        a1.plot([date.fromisoformat(r["date"]) for r in rows], cum, color=color, ls=ls, lw=1.6, label=f"{lab} ({fr(cum[-1], 2)} $)")
        hedge = statistics.fmean(float(r["hedge_btc"]) for r in rows)
        a2.bar(lab, hedge, color=color, alpha=0.9 if ls == "-" else 0.5)
        a2.annotate(fr(hedge, 3), (lab, hedge), ha="center", va="bottom", fontsize=8)
        stats[key] = {"funding_cumul_final": round(cum[-1], 2), "somme_funding_paid": round(sum(paid), 2),
                      "hedge_moyen_btc": hedge, "jours": len(rows)}
    a1.axhline(0, color=GREY, lw=0.6)
    a1.set_ylabel("PnL de funding cumulé ($)\n(−funding payé ; < 0 = coût du long)")
    a1.legend(frameon=False, fontsize=9)
    a1.grid(alpha=0.25)
    a1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))  # type: ignore[no-untyped-call]
    a1.set_title("Isolation du funding : 207 échéances, hedge statique long perp")
    a2.set_ylabel("Taille moyenne du hedge (BTC)")
    a2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fr(v, 2)))
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return stats


def main() -> None:
    kalshi = read_rows(ROOT / "results.csv")
    days = sorted({r["date"] for r in kalshi})
    day = max(days, key=lambda x: (abs(day_move(candles(x))), -date.fromisoformat(x).toordinal()))
    d = run_day(day)
    gamma_zoom(day, d, OUT / "gamma_zoom.png")
    out = {"jour": day, "S0": d["prices"][0], "S1": d["prices"][-1], "variation": d["prices"][-1] / d["prices"][0] - 1,
           "hedge_statique_btc": d["static"],
           "delta_horaire_btc": {k: {"min": round(min(v), 5), "max": round(max(v), 5)} for k, v in d["hourly"].items()},
           "iv_rv": iv_rv(kalshi, OUT / "iv_vs_rv.png"),
           "funding": funding(kalshi, read_rows(DERIBIT_CSV), OUT / "funding_pnl.png")}
    (OUT / "diagnostics.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
