"""Kalshi strip vs Deribit daily options (put spread, vanilla put), same T0/T1 window, same HL static hedge.

Deribit daily expiring D+1 08:00 UTC is bought at T0 = D-1 21:00 UTC and marked at T1 = D 21:00 UTC (never held to
expiry). No historical book exists, so prices come from the trades of ``history.deribit.com`` in the
3 h up to T (only trades <= T are used, no look-ahead): Black-Scholes (r = 0) on a linear smile (log-moneyness) of the trades' IV, plus/minus the
median |price - mark| as taker half-spread. The HL perp hedge reuses the logic of ``kalshi_one_trade.backtest``::

    python -m backtest.deribit_benchmark --date 2026-04-04 | --all | --collect

Sizing: q = n / step BTC exactly (n contracts per Kalshi leg, step = 250 or 500 between legs), so Kalshi and Deribit
carry the same payoff per dollar of move. Deribit really trades in 0.1 BTC increments (q_rounded is reported for
information); fees and payoff are linear in q, so the paper backtest keeps the exact size. The put spread spans the
grid strikes nearest to K_lo - step/2 and K_hi + step/2.

Deribit fee schedule (docs/deribit_friction.md, read 2026-10-12): per leg and per trade, taker = maker,
q x min(0.0003 BTC, 12.5 % of the option price), i.e. min(0.03 % x index x q, 12.5 % x leg premium) in USD. The combo
rule (cheaper side free on a buy+sell combo) is unconfirmed and NOT applied; daily options: no specific rule found.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
import re
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import NormalDist
from typing import Any

import httpx

from backtest import kalshi_one_trade as one
from backtest import kalshi_strip_trade as strip
from backtest.kalshi_one_trade import CANDLE_MS, HL_SZ_DECIMALS
from backtest.multi_day import CONTRACTS, MONTHS, N_STRIKES, configure
from core.math_engine import year_fraction
from risk.fees import hl_fee

URL = "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"
ROOT = Path("data/deribit")
KALSHI_ROOT = Path("data/kalshi_multi")
WINDOW_MS = 3 * 3_600_000
MIN_TRADES = 3
GRID = 500.0
FEE_RATE, FEE_CAP = 0.0003, 0.125
KEEP = ("instrument_name", "timestamp", "price", "mark_price", "iv", "index_price", "amount", "direction")
N = NormalDist()


class Excluded(Exception):
    """The day cannot be priced (too few trades, no strip); the reason goes to summary.json."""


def instrument_name(expiry: date, strike: float, kind: str) -> str:
    """BTC-4APR26-66000-P: day without leading zero, upper-case month, 2-digit year."""
    return f"BTC-{expiry.day}{MONTHS[expiry.month - 1]}{expiry:%y}-{strike:.0f}-{kind}"


def resolve_strike(strikes: list[float], target: float) -> float:
    """Listed strike closest to ``target`` (ties go to the lower one)."""
    return min(sorted(strikes), key=lambda k: abs(k - target))


def bs_put(s: float, k: float, sigma: float, tau: float) -> float:
    """Black-Scholes put, r = 0, per 1 BTC in USD."""
    if tau <= 0 or sigma <= 0:
        return max(k - s, 0.0)
    v = sigma * math.sqrt(tau)
    d1 = (math.log(s / k) + 0.5 * v * v) / v
    return k * N.cdf(-(d1 - v)) - s * N.cdf(-d1)


def bs_put_delta(s: float, k: float, sigma: float, tau: float) -> float:
    """Put delta N(d1) - 1 (negative)."""
    if tau <= 0 or sigma <= 0:
        return -1.0 if k > s else 0.0
    v = sigma * math.sqrt(tau)
    return N.cdf((math.log(s / k) + 0.5 * v * v) / v) - 1.0


def deribit_fee(index: float, q: float, premium_usd: float, rate: float = FEE_RATE, cap: float = FEE_CAP) -> float:
    """Taker fee of one leg, one trade: min(rate x index x q, cap x premium of the leg)."""
    return min(rate * index * q, cap * premium_usd)


def grid_strike(target: float) -> float:
    """Nearest strike of the Deribit daily grid (500 USD multiples: every one of the 3 710 strikes seen in the cached
    trades is one, 500 apart near the money). The instrument exists as soon as it is on the grid, traded or not."""
    return float(math.floor(target / GRID + 0.5) * GRID)


def strip_params(legs: list[strip.Leg]) -> dict[str, float]:
    """n contracts per leg (all equal), strike step (250 or 500), K_lo, K_hi and q = n / step BTC of the strip."""
    ns = {g.contracts for g in legs}
    if len(legs) < 2 or len(ns) != 1:
        raise ValueError(f"strip legs unusable: {len(legs)} legs, contracts {sorted(ns)}")
    step = float(round(legs[1].strike - legs[0].strike))
    n = float(ns.pop())
    return {"n": n, "step": step, "k_lo": legs[0].strike, "k_hi": legs[-1].strike, "q": n / step}


def _cached(path: Path, fetch: Any) -> Any:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data: Any = None
    for attempt in range(4):  # 429s come back as an error body: back off, never cache an error or an empty answer
        data = fetch()
        if data and not (isinstance(data, dict) and "error" in data):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
            return data
        time.sleep(2 ** attempt)
    if isinstance(data, dict):
        raise RuntimeError(f"{path}: {str(data)[:120]}")
    raise Excluded(f"no trade on the expiry in {path.name}")


@lru_cache(maxsize=None)
def tag_date(tag: str) -> date:
    """Expiry date of a tag such as 4APR26."""
    m = re.fullmatch(r"(\d+)([A-Z]{3})(\d{2})", tag)
    assert m is not None, tag
    return date(2000 + int(m[3]), MONTHS.index(m[2]) + 1, int(m[1]))


def fetch_trades(c: httpx.Client, t_ms: int, tag: str) -> dict[str, Any] | list[Any]:
    """BTC option trades in [t - 3 h, t]: the expiry's trades, the last trade (spot), the median |price - mark|
    of the other daily/weekly expiries (spread fallback). An empty expiry returns [] so it is never cached."""
    out: list[dict[str, Any]] = []
    others: list[float] = []
    spot: list[float] | None = None
    today = datetime.fromtimestamp(t_ms / 1000, UTC).date()
    start = t_ms - WINDOW_MS
    seen: set[str] = set()
    while True:
        try:
            body = c.get(URL, params={"currency": "BTC", "kind": "option", "start_timestamp": start,
                                      "end_timestamp": t_ms, "count": 1000, "include_old": "true",
                                      "sorting": "asc"}).json()
        except (httpx.HTTPError, ValueError):
            return {"error": "http"}
        if "result" not in body:
            return {"error": str(body)[:100]}
        trades = [x for x in body["result"]["trades"] if x["trade_id"] not in seen]
        seen.update(x["trade_id"] for x in trades)
        for x in trades:
            tg = x["instrument_name"].split("-")[1]
            if tg == tag:
                out.append({k: x.get(k) for k in KEEP})
            elif 0 <= (tag_date(tg) - today).days <= 8 and x.get("price") is not None and x.get("mark_price") is not None:
                others.append(abs(float(x["price"]) - float(x["mark_price"])))
        if trades:
            spot = [trades[-1]["timestamp"], trades[-1]["index_price"]]
        if not trades or not body["result"].get("has_more"):
            break
        start = trades[-1]["timestamp"]  # same-millisecond trades may straddle pages: restart there, dedupe by trade_id
        time.sleep(0.1)
    return {"trades": out, "spot": spot, "other_hs": statistics.median(others) if others else None} if out else []


@dataclass(frozen=True, slots=True)
class Snap:
    """What the trades up to t say about the expiry: spot, smile (log-moneyness, IV), taker half-spread (BTC)."""

    t_ms: int
    spot: float
    smile: tuple[tuple[float, float], ...]
    half_spread_btc: float
    n_trades: int
    spread_source: str

    def iv(self, k: float) -> float:
        """Linear interpolation in x = ln(K / spot), flat outside the covered range."""
        x = math.log(k / self.spot)
        xs = [p[0] for p in self.smile]
        i = bisect.bisect_left(xs, x)
        if i == 0:
            return self.smile[0][1]
        if i == len(xs):
            return self.smile[-1][1]
        (x0, v0), (x1, v1) = self.smile[i - 1], self.smile[i]
        return v0 + (v1 - v0) * (x - x0) / (x1 - x0) if x1 > x0 else v1


def snapshot(data: dict[str, Any], t_ms: int) -> Snap:
    """Snapshot at t from trades with timestamp in [t - 3 h, t] only (no look-ahead)."""
    w = sorted((x for x in data["trades"] if t_ms - WINDOW_MS <= x["timestamp"] <= t_ms), key=lambda x: x["timestamp"])
    if len(w) < MIN_TRADES:
        raise Excluded(f"{len(w)} trade(s) on the expiry in [T-3h, T] with T={t_ms}")
    spot_ts, spot = data["spot"] if data["spot"] and data["spot"][0] <= t_ms else (w[-1]["timestamp"], w[-1]["index_price"])
    pts = sorted((math.log(float(x["instrument_name"].split("-")[2]) / float(x["index_price"])), float(x["iv"]) / 100)
                 for x in w if x["iv"])
    if not pts:
        raise Excluded(f"no IV in [T-3h, T] with T={t_ms}")
    gaps = [abs(float(x["price"]) - float(x["mark_price"])) for x in w
            if x["price"] is not None and x["mark_price"] is not None]
    if len(gaps) >= MIN_TRADES:
        hs, src = statistics.median(gaps), "expiry"
    elif data.get("other_hs") is not None:
        hs, src = float(data["other_hs"]), "other_expiries"
    else:
        raise Excluded(f"no half-spread available in [T-3h, T] with T={t_ms}")
    return Snap(t_ms, float(spot), tuple(pts), hs, len(w), src)


def quote(snap: Snap, k: float, tau: float, buy: bool) -> tuple[float, float]:
    """(execution price, BS mid) of one put in USD: mid + half-spread when buying, mid - half-spread when selling."""
    mid = bs_put(snap.spot, k, snap.iv(k), tau)
    hs = snap.half_spread_btc * snap.spot
    return max(mid + hs if buy else mid - hs, 0.0), mid


def hedge_pnl(hedge: float, candles: list[dict[str, Any]], funding: list[dict[str, Any]], t0: int, t1: int
              ) -> tuple[float, float, float]:
    """Static perp (perp_pnl, hl_fees, funding_paid), same logic as kalshi_one_trade.backtest (hour-open funding)."""
    c = {int(k["t"]): k for k in candles}
    s0, s1 = float(c[t0]["o"]), float(c[t1 - CANDLE_MS]["c"])
    fees = hl_fee(hedge * s0, maker=False) + hl_fee(hedge * s1, maker=False)
    paid = sum(hedge * float(c.get(int(f["time"]) - int(f["time"]) % CANDLE_MS, c[t0])["o"]) * float(f["fundingRate"])
               for f in funding if t0 <= int(f["time"]) < t1)
    return hedge * (s1 - s0), fees, paid


def combo_discount(fees: list[tuple[int, float]]) -> float:
    """Combo variant (unconfirmed rule): with buy and sell legs, the cheaper direction is free."""
    buy, sell = sum(f for s, f in fees if s > 0), sum(f for s, f in fees if s < 0)
    return min(buy, sell) if buy and sell else 0.0


def evaluate(legs: list[tuple[int, float]], q: float, s0: Snap, s1: Snap, expiry_ms: int,
             candles: list[dict[str, Any]], funding: list[dict[str, Any]]) -> dict[str, Any]:
    """Open ``legs`` (+1 long / -1 short, strike) of q BTC at s0, close at s1, static HL hedge; all in USD."""
    tau0, tau1 = year_fraction(s0.t_ms, expiry_ms), year_fraction(s1.t_ms, expiry_ms)
    prime = value = fee_in = fee_out = spread = delta = 0.0
    fin: list[tuple[int, float]] = []
    fout: list[tuple[int, float]] = []
    for side, k in legs:
        p_in, m_in = quote(s0, k, tau0, buy=side > 0)
        p_out, m_out = quote(s1, k, tau1, buy=side < 0)
        prime += side * p_in * q
        value += side * p_out * q
        fin.append((side, deribit_fee(s0.spot, q, p_in * q)))
        fout.append((-side, deribit_fee(s1.spot, q, p_out * q)))
        spread += q * (abs(p_in - m_in) + abs(p_out - m_out))
        delta += side * q * bs_put_delta(s0.spot, k, s0.iv(k), tau0)
    fee_in, fee_out = sum(f for _, f in fin), sum(f for _, f in fout)
    combo = fee_in + fee_out - sum(combo_discount(f) for f in (fin, fout))
    hedge = round(-delta, HL_SZ_DECIMALS)
    perp, hl_fees, funding_paid = hedge_pnl(hedge, candles, funding, s0.t_ms, s1.t_ms)
    option_pnl = value - prime
    return {"instruments": [instrument_name(datetime.fromtimestamp(expiry_ms / 1000, UTC).date(), k, "P")
                            for _, k in legs],
            "strikes": [k for _, k in legs], "sides": [s for s, _ in legs], "q": q,
            "iv0": [s0.iv(k) for _, k in legs], "iv1": [s1.iv(k) for _, k in legs], "s0": s0.spot, "s1": s1.spot,
            "premium_entry": prime, "value_exit": value, "fee_deribit_entry": fee_in, "fee_deribit_exit": fee_out, "fee_combo_variant": combo,
            "spread_source_t0": s0.spread_source, "spread_source_t1": s1.spread_source,
            "spread_cost": spread, "option_pnl": option_pnl, "hedge_btc": hedge, "perp_notional_usd": abs(hedge) * s0.spot, "perp_pnl": perp,
            "hl_fees": hl_fees, "funding_paid": funding_paid, "n_trades_t0": s0.n_trades, "n_trades_t1": s1.n_trades,
            "total_pnl": option_pnl + perp - fee_in - fee_out - hl_fees - funding_paid}


def kalshi_spread(raw: dict[str, Any], legs: list[strip.Leg], t0: int) -> float:
    """Entry half-spread paid on the strip (ValueError if a bid or an ask is missing): sum of contracts x (ask - mid) of the YES quote hit at T0."""
    total = 0.0
    for leg in legs:
        live = [k for k in raw["kalshi"][leg.ticker]
                if t0 - 3_600_000 <= k["end_period_ts"] * 1000 <= t0 and strip._price(k, "yes_bid") is not None]
        e = max(live, key=lambda k: k["end_period_ts"])
        bid, ask = strip._price(e, "yes_bid"), strip._price(e, "yes_ask")
        if bid is None or ask is None:
            raise ValueError(f"missing Kalshi bid/ask at T0 for {leg.ticker}")
        total += leg.contracts * (ask - bid) / 2
    return total


def run_day(day: date) -> dict[str, Any]:
    """Backtest both Deribit structures against the Kalshi strip of ``day``; write and return the summary."""
    out = ROOT / day.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"date": day.isoformat()}
    try:
        summary.update(_run(day, out))
    except Excluded as e:
        summary["excluded"] = str(e)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _run(day: date, out: Path) -> dict[str, Any]:
    configure(day)
    t0, t1 = one.T0_MS, one.T1_MS
    raw1, raw2 = one.load(refresh=False), strip.load(refresh=False, n_strikes=N_STRIKES)
    dvol = float(raw1["dvol"][-1][4]) / 100
    r1, _ = one.backtest(raw1, CONTRACTS, sigma_override=dvol)
    r2, _ = strip.backtest(raw2, r1.kalshi_premium, sigma_override=dvol)
    if not r2.legs:
        raise Excluded("no Kalshi strip leg quoted at T0")
    expiry = day + timedelta(days=1)
    expiry_ms = int(datetime(expiry.year, expiry.month, expiry.day, 8, tzinfo=UTC).timestamp() * 1000)
    tag = instrument_name(expiry, 0, "P").split("-")[1]
    with httpx.Client(timeout=30) as c:
        tr0 = _cached(out / "trades_t0.json", lambda: fetch_trades(c, t0, tag))
        tr1 = _cached(out / "trades_t1.json", lambda: fetch_trades(c, t1, tag))
    s0, s1 = snapshot(tr0, t0), snapshot(tr1, t1)
    hl0 = float(next(k for k in raw2["candles"] if int(k["t"]) == t0)["o"])
    hl1 = float(next(k for k in raw2["candles"] if int(k["t"]) == t1 - CANDLE_MS)["c"])
    sp = strip_params(r2.legs)
    n, step, q, k_lo, k_hi = sp["n"], sp["step"], sp["q"], sp["k_lo"], sp["k_hi"]
    k_long, k_short = grid_strike(k_hi + step / 2), grid_strike(k_lo - step / 2)
    if k_long <= k_short:
        raise Excluded(f"degenerate Deribit spread {k_short}/{k_long}")
    k_atm = grid_strike(s0.spot)
    args = (q, s0, s1, expiry_ms, raw2["candles"], raw2["funding"])
    spread_leg = evaluate([(1, k_long), (-1, k_short)], *args)
    width = k_long - k_short
    put_leg = evaluate([(1, k_atm)], *args)
    k_fee, k_spread = sum(g.fee for g in r2.legs), kalshi_spread(raw2, r2.legs, t0)
    return {
        "expiry": expiry.isoformat(), "spot_gap_t0": abs(s0.spot - hl0) / s0.spot,
        "spot_gap_t1": abs(s1.spot - hl1) / s1.spot, "n": n, "step": step, "q": q,
        "q_rounded": round(q, 1), "k_lo": k_lo, "k_hi": k_hi, "width_strip": k_hi - k_lo + step,
        "width_deribit": width, "max_payoff_gap_usd": q * width - n * len(r2.legs),
        "put_spread": {**spread_leg, "max_gain_usd": q * width - spread_leg["premium_entry"]},
        "put": {**put_leg, "max_gain_usd": q * k_atm - put_leg["premium_entry"]},
        "kalshi": {"premium": r2.kalshi_premium, "fees": k_fee, "spread": k_spread, "total_pnl": r2.total_pnl,
                   "hedge_btc": r2.hedge_btc, "legs": len(r2.legs)},
    }


def collect() -> Path:
    """One CSV row per day x structure from every non-excluded summary."""
    rows: list[dict[str, Any]] = []
    for f in sorted(ROOT.glob("*/summary.json")):
        s = json.loads(f.read_text(encoding="utf-8"))
        if "excluded" in s:
            continue
        for name in ("put_spread", "put"):
            r = s[name]
            head = {k: v for k, v in s.items() if k not in ("put_spread", "put", "kalshi")}
            rows.append({**head, "structure": name,
                         **{k: v for k, v in r.items() if k not in ("instruments", "strikes", "sides", "iv0", "iv1")},
                         "strikes": "/".join(f"{k:.0f}" for k in r["strikes"]),
                         "kalshi_fees": s["kalshi"]["fees"], "kalshi_spread": s["kalshi"]["spread"],
                         "kalshi_premium": s["kalshi"]["premium"], "kalshi_total_pnl": s["kalshi"]["total_pnl"]})
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
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--collect", action="store_true")
    args = ap.parse_args()
    days = [args.date] if args.date else []
    if args.all:
        days = [date.fromisoformat(p.name) for p in sorted(KALSHI_ROOT.glob("2026-*")) if p.is_dir()
                and not (ROOT / p.name / "summary.json").exists()]
    for d in days:
        try:
            s = run_day(d)
        except Exception as e:  # noqa: BLE001 - transient failure: leave no summary so a rerun retries the day
            print(f"{d} FAILED {type(e).__name__}: {e}", flush=True)
            continue
        tail = s.get("excluded") or " ".join(f"{k}={s[k]['total_pnl']:+.1f}" for k in ("put_spread", "put"))
        print(f"{d} {tail}", flush=True)
    if args.collect:
        print(collect())


if __name__ == "__main__":
    main()
