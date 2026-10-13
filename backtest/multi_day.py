"""Run the single-strike and the binary-strip backtests on one Kalshi daily expiry, under two sigma sources.

For settlement date D (KXBTCD-<D>17, 17:00 EDT = 21:00 UTC) the window is D-1 21:00 UTC -> D 21:00 UTC. The strip
budget equals the single trade's premium (capital-matched). Sigma sources: Deribit DVOL at entry, and the median
Kalshi implied vol of the strip strikes. Raw inputs are cached per day under ``data/kalshi_multi/<D>/``::

    python -m backtest.multi_day --date 2026-10-11      # one day -> data/kalshi_multi/<D>/summary.json
    python -m backtest.multi_day --collect             # all days -> data/kalshi_multi/results.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from backtest import kalshi_one_trade as one
from backtest import kalshi_strip_trade as strip

ROOT = Path("data/kalshi_multi")
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
CONTRACTS = 1000.0
N_STRIKES = 9


def configure(day: date) -> Path:
    """Point both backtest modules at day ``day`` (EDT settlement, valid until the first Sunday of November)."""
    t1 = int(datetime(day.year, day.month, day.day, 21, tzinfo=UTC).timestamp() * 1000)
    t0 = t1 - 86_400_000
    event = f"KXBTCD-{day:%y}{MONTHS[day.month - 1]}{day:%d}17"
    base = ROOT / day.isoformat()
    for mod in (one, strip):
        mod.T0_MS, mod.T1_MS, mod.EVENT = t0, t1, event  # type: ignore[attr-defined]
    one.CACHE = base / "single"
    strip.CACHE, strip.ONE_TRADE_CACHE = base / "strip", base / "single"  # type: ignore[attr-defined]
    return base


def path_stats(path: list[dict[str, float]]) -> tuple[float, float]:
    """Std of the hourly hedged MtM (Kalshi mid + perp) and its largest one-hour move, NaN hours skipped."""
    h = [p["kalshi_mtm"] + p["perp_mtm"] for p in path]
    h = [x for x in h if not math.isnan(x)]
    moves = [abs(b - a) for a, b in zip(h, h[1:])]
    return (statistics.pstdev(h) if len(h) > 1 else float("nan"), max(moves, default=float("nan")))


def _row(structure: str, sigma_source: str, res: Any, path: list[dict[str, float]]) -> dict[str, Any]:
    std, worst = path_stats(path)
    return {"structure": structure, "sigma_source": sigma_source, "sigma": res.sigma, "premium": res.kalshi_premium,
            "kalshi_fee": res.kalshi_fee, "kalshi_payoff": res.kalshi_payoff, "kalshi_pnl": res.kalshi_pnl,
            "hedge_btc": res.hedge_btc, "perp_pnl": res.perp_pnl, "hl_fees": res.hl_fees,
            "funding_paid": res.funding_paid, "total_pnl": res.total_pnl, "hedged_std_hourly": std,
            "worst_hour": worst}


def run_day(day: date) -> dict[str, Any]:
    """Backtest both structures under DVOL and Kalshi-implied sigma; write and return the day summary."""
    base = configure(day)
    raw1 = one.load(refresh=False)
    raw2 = strip.load(refresh=False, n_strikes=N_STRIKES)
    dvol = float(raw1["dvol"][-1][4]) / 100
    r1, p1 = one.backtest(raw1, CONTRACTS, sigma_override=dvol)
    budget = r1.kalshi_premium
    r2, p2 = strip.backtest(raw2, budget, sigma_override=dvol)
    ivs = [g.sigma_implied for g in r2.legs if g.sigma_implied is not None]
    iv = statistics.median(ivs) if ivs else dvol
    r1k, p1k = one.backtest(raw1, CONTRACTS, sigma_override=iv)
    r2k, p2k = strip.backtest(raw2, budget, sigma_override=iv)
    summary = {
        "date": day.isoformat(), "event": one.EVENT, "s0": r1.hl_entry, "s1": r1.hl_exit,
        "settlement": r1.settlement_brti, "atm_strike": r1.strike, "dvol": dvol, "kalshi_iv_median": iv,
        "n_iv": len(ivs), "strip_legs": len(r2.legs), "strip_excluded": r2.excluded,
        "rows": [_row("single", "dvol", r1, p1), _row("strip", "dvol", r2, p2),
                 _row("single", "kalshi_iv", r1k, p1k), _row("strip", "kalshi_iv", r2k, p2k)],
    }
    (base / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def collect() -> Path:
    """Flatten every ``<day>/summary.json`` into ``results.csv`` (one row per day x structure x sigma source)."""
    rows: list[dict[str, Any]] = []
    for f in sorted(ROOT.glob("*/summary.json")):
        s = json.loads(f.read_text(encoding="utf-8"))
        head = {k: s[k] for k in ("date", "s0", "s1", "settlement", "atm_strike", "dvol", "kalshi_iv_median", "strip_legs")}
        rows += [{**head, **r} for r in s["rows"]]
    out = ROOT / "results.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return out


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", type=date.fromisoformat)
    ap.add_argument("--collect", action="store_true")
    args = ap.parse_args()
    if args.date is not None:
        s = run_day(args.date)
        for r in s["rows"]:
            print(f"{s['date']} {r['structure']:>6} {r['sigma_source']:>9} sigma={r['sigma']:.3f} "
                  f"total={r['total_pnl']:+9.2f} std={r['hedged_std_hourly']:7.1f}")
    if args.collect:
        print(collect())


if __name__ == "__main__":
    main()
