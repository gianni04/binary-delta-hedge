"""Presentation figures for step 2: payoff replication, friction breakdown, Kalshi liquidity regime.

    python -m reports.presentation
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from reports.deribit_compare import BLUE, ORANGE, Rows, friction_by_day, load

GREY = "#6B6B6B"


def fr(x: float, nd: int = 0) -> str:
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")
EXAMPLE_DAY = "2026-06-15"  # a typical 9-leg day (step 250 $)
WINDOW = 30  # trading days in the rolling means


def payoff(day: str = EXAMPLE_DAY, out: Path = Path("reports/payoff_replication.png")) -> Path:
    """Profit at expiry, unhedged, of the Kalshi strip vs the Deribit put spread and put of one day."""
    s = json.loads(Path(f"data/deribit/{day}/summary.json").read_text(encoding="utf-8"))
    n, step, k_lo, k_hi, q = s["n"], s["step"], s["k_lo"], s["k_hi"], s["q"]
    strikes = np.arange(k_lo, k_hi + step / 2, step)
    k_long, k_short = s["put_spread"]["strikes"]
    k_atm = s["put"]["strikes"][0]
    x = np.linspace(k_lo - 2 * step * 4, k_hi + 2 * step * 4, 2000)
    strip = n * (x[:, None] < strikes[None, :]).sum(axis=1) - s["kalshi"]["premium"]
    spread = q * (np.maximum(k_long - x, 0) - np.maximum(k_short - x, 0)) - s["put_spread"]["premium_entry"]
    put = q * np.maximum(k_atm - x, 0) - s["put"]["premium_entry"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.step(x, strip, where="post", color=ORANGE, lw=2, label=f"Strip Kalshi : {len(strikes)} binaires × {n:.0f} contrats (gamma en escalier)")
    ax.plot(x, spread, color=BLUE, lw=2, label=f"Put spread Deribit {fr(k_short)} / {fr(k_long)}, q = {fr(q, 3)} BTC (gamma continu)")
    ax.plot(x, put, color=BLUE, lw=2, ls="--", label=f"Put vanille Deribit {fr(k_atm)}, q = {fr(q, 3)} BTC (perte non bornée)")
    ax.axhline(0, color=GREY, lw=0.8)
    ax.set_xlabel("BTC à l'échéance ($)")
    ax.set_ylabel("Gain à l'échéance, net de la prime ($)")
    ax.set_title(f"Réplication : un strip de binaires ≈ un put spread (échéance du {date.fromisoformat(day):%d/%m/%Y}, avant couverture)")
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def friction(data: Rows, out: Path = Path("reports/friction_breakdown.png")) -> Path:
    """Average option friction per day, fees vs spread, per platform (Hyperliquid hedge fees excluded)."""
    rows = [("Kalshi\nstrip", "strip", False, ORANGE), ("Deribit\nput spread", "put_spread", False, BLUE),
            ("Deribit put spread\n(remise combo, non confirmée)", "put_spread", True, BLUE), ("Deribit\nput vanille", "put", False, BLUE)]
    n_days = len(data["strip"])
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for i, (label, k, combo, color) in enumerate(rows):
        per_day = friction_by_day(data, k, combo)
        fee, spr = sum(f for f, _ in per_day.values()) / n_days, sum(s for _, s in per_day.values()) / n_days
        ax.barh(i, fee, color=color, height=0.6, edgecolor="white", linewidth=2)
        ax.barh(i, spr, left=fee, color=color, alpha=0.35, height=0.6, edgecolor="white", linewidth=2)
        ax.text(fee / 2, i, f"frais\n{fee:.1f} $", ha="center", va="center", fontsize=8, color="white")
        ax.text(fee + spr / 2, i, f"spread\n{spr:.1f} $", ha="center", va="center", fontsize=8, color="#222222")
        ax.text(fee + spr + 0.8, i, f"{fr(fee + spr, 1)} $/jour", va="center", fontsize=9, color="#222222")
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlabel("Friction d'option moyenne par échéance ($/jour, sur 207 jours)")
    ax.set_title("Kalshi paie du spread, Deribit paie des frais (entrée + sortie)")
    ax.grid(axis="x", alpha=0.25)
    ax.set_xlim(0, 65)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def rolling(v: np.ndarray) -> np.ndarray:
    return np.convolve(v, np.ones(WINDOW) / WINDOW, mode="valid")


def regime(data: Rows, out: Path = Path("reports/kalshi_liquidity_regime.png")) -> Path:
    """Rolling Deribit advantage over the strip next to the rolling Kalshi spread, plus the daily scatter."""
    dates = sorted(data["strip"])
    x = [mdates.date2num(date.fromisoformat(d)) for d in dates]  # type: ignore[no-untyped-call]
    diff = np.array([data["put_spread"][d]["total_pnl"] - data["strip"][d]["total_pnl"] for d in dates])
    spread = np.array([data["put"][d]["kalshi_spread"] for d in dates])
    xr, rd, rs = x[WINDOW - 1:], rolling(diff), rolling(spread)
    fig = plt.figure(figsize=(13, 6.5))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.6, 1], hspace=0.12, wspace=0.22)
    a1, a2, a3 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[:, 1])
    a1.plot(xr, rd, color=BLUE, lw=2)
    a1.axhline(0, color=GREY, lw=0.8)
    a1.fill_between(xr, rd, 0, where=rd < 0, color=ORANGE, alpha=0.25, label="strip Kalshi meilleur")
    a1.fill_between(xr, rd, 0, where=rd >= 0, color=BLUE, alpha=0.15, label="put spread Deribit meilleur")
    a1.set_ylabel(f"Put spread − strip\n(moyenne {WINDOW} j, $/jour)")
    a1.legend(loc="upper right", frameon=False, fontsize=9)
    a1.tick_params(labelbottom=False)
    a2.plot(xr, rs, color=ORANGE, lw=2)
    a2.set_ylabel(f"Spread Kalshi payé\n(moyenne {WINDOW} j, $/jour)")
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))  # type: ignore[no-untyped-call]
    slope, icpt = np.polyfit(spread, diff, 1)
    corr = float(np.corrcoef(spread, diff)[0, 1])
    a3.scatter(spread, diff, s=14, color=BLUE, alpha=0.55, edgecolor="white", linewidth=0.4)
    xs = np.linspace(0, float(spread.max()), 50)
    a3.plot(xs, icpt + slope * xs, color="#222222", lw=1.5, label=f"écart = {fr(icpt, 1)} + {fr(slope, 2)} × spread  (corr. {fr(corr, 2)})")
    a3.axhline(0, color=GREY, lw=0.8)
    a3.axvline(-icpt / slope, color=GREY, lw=0.8, ls=":")
    a3.text(-icpt / slope, a3.get_ylim()[0] * 0.92, f"  équilibre ≈ {-icpt / slope:.0f} $", fontsize=8, color=GREY)
    a3.set_xlabel("Spread Kalshi payé le jour même ($)")
    a3.set_ylabel("Put spread − strip, PnL du jour ($)")
    a3.legend(loc="upper left", frameon=False, fontsize=8)
    for ax in (a1, a2, a3):
        ax.grid(alpha=0.25)
        ax.yaxis.set_major_formatter(lambda v, _: fr(v))
    fig.suptitle("L'avantage Deribit suit la liquidité du carnet Kalshi, et s'inverse quand elle s'améliore", y=0.98)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    data = load()
    for p in (payoff(), friction(data), regime(data)):
        print(p)


if __name__ == "__main__":
    main()
