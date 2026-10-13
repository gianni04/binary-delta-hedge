"""Strip backtest: N long-NO legs on KXBTCD-26OCT1117 strikes around ATM, one static Hyperliquid perp hedge.

Same window as ``kalshi_one_trade`` (entry 2026-10-10 21:00 UTC, exit 2026-10-11 21:00 UTC). The strip is a put
spread replica: K_ATM + k*250, k in -(N-1)/2..(N-1)/2, equal contracts per strike at a fixed premium budget
(or Gaussian-weighted). One common sigma (DVOL at entry) feeds the aggregate delta; per-strike implied vols are
only logged. Raw inputs are cached under ``data/kalshi_strip_trade/``::

    python -m backtest.kalshi_strip_trade [--n-strikes 9] [--budget 510] [--weights uniform] [--refresh]
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from backtest.kalshi_one_trade import (
    CACHE as ONE_TRADE_CACHE,
)
from backtest.kalshi_one_trade import (
    HL,
    CANDLE_MS,
    HL_SZ_DECIMALS,
    T0_MS,
    T1_MS,
    kalshi_fee,
)
from backtest import kalshi_one_trade as one
from core.math_engine import SECONDS_PER_YEAR, binary_call_delta, implied_vol
from risk.fees import hl_fee

CACHE = Path("data/kalshi_strip_trade")
STRIKE_STEP = 250.0
SERIES = "KXBTCD"


def _cached(directory: Path, name: str, fetch: Any, refresh: bool) -> Any:
    path = directory / f"{name}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    for attempt in range(6):  # public endpoints rate-limit (Kalshi 429): back off, never cache an error body
        data = fetch()
        if data and not (isinstance(data, dict) and "error" in data):
            break
        time.sleep(2 ** attempt)
    else:
        raise ValueError(f"no usable response for {name}: {str(data)[:120]}")
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def _shared(name: str, fetch: Any, refresh: bool) -> Any:
    """Read an input the one-trade backtest already cached; fetch into our own cache if missing."""
    own = CACHE / f"{name}.json"
    src = own if own.exists() else ONE_TRADE_CACHE / f"{name}.json"
    return _cached(src.parent, name, fetch, refresh)


def select_strikes(markets: list[dict[str, Any]], s0: float, n_strikes: int) -> list[dict[str, Any]]:
    """Markets at K_ATM + k*250 (K_ATM = floor_strike nearest S0), k in -(N-1)/2..(N-1)/2, when listed."""
    atm = min((float(m["floor_strike"]) for m in markets), key=lambda k: abs(k - s0))
    half = n_strikes // 2
    out: list[dict[str, Any]] = []
    for k in range(-half, half + 1):
        target = atm + k * STRIKE_STEP
        m = min(markets, key=lambda x: abs(float(x["floor_strike"]) - target))
        if abs(float(m["floor_strike"]) - target) < STRIKE_STEP / 2 and m not in out:
            out.append(m)
    return out


def load(refresh: bool, n_strikes: int) -> dict[str, Any]:
    """Fetch (or read from cache) every raw input of the strip backtest."""
    with httpx.Client(timeout=30) as c:
        event = _shared("event", lambda: one.fetch_event(c), refresh)
        candles = _shared("hl_candles_1h", lambda: c.post(HL, json={"type": "candleSnapshot", "req": {
            "coin": "BTC", "interval": "1h", "startTime": T0_MS, "endTime": T1_MS}}).json(), refresh)
        funding = _shared("hl_funding", lambda: c.post(HL, json={
            "type": "fundingHistory", "coin": "BTC", "startTime": T0_MS, "endTime": T1_MS}).json(), refresh)
        dvol = _shared("deribit_dvol", lambda: one.fetch_dvol(c), refresh)
        chosen = select_strikes(one.event_markets(event), float(candles[0]["o"]), n_strikes)

        kalshi = {m["ticker"]: _cached(CACHE, f"kalshi_{m['ticker']}", lambda t=m["ticker"]: one.fetch_candles(c, t),
                                       refresh)["candlesticks"]
                  for m in chosen}
    return {"markets": chosen, "candles": candles, "kalshi": kalshi, "funding": funding, "dvol": one.dvol_known(dvol)}


def _price(candle: dict[str, Any] | None, side: str) -> float | None:
    q = (candle or {}).get(side, {})
    v = q.get("close_dollars", q.get("close"))  # live vs historical candlestick schema
    return float(v) if v is not None else None


def _phi(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


@dataclass(frozen=True, slots=True)
class Leg:
    """One strike of the strip."""

    ticker: str
    strike: float
    price: float
    contracts: int
    premium: float
    fee: float
    delta: float
    result: str
    payoff: float
    sigma_implied: float | None


@dataclass(frozen=True, slots=True)
class Result:
    """Strip totals, in USD unless stated."""

    weights: str
    budget: float
    sigma: float
    hl_entry: float
    hl_exit: float
    delta_total: float
    hedge_btc: float
    kalshi_premium: float
    kalshi_fee: float
    kalshi_payoff: float
    kalshi_pnl: float
    perp_pnl: float
    hl_fees: float
    funding_paid: float
    funding_hours: int
    total_pnl: float
    unhedged_pnl: float
    excluded: list[str]
    legs: list[Leg]


def contracts_per_strike(prices: list[float], strikes: list[float], s0: float, sigma: float, t: float,
                         budget: float, weights: str) -> list[int]:
    """n_i = round(B*w_i / sum_j w_j p_j); w = 1 (uniform in dK) or phi((K-S0)/(S0*sigma*sqrt(T))) (gaussian)."""
    if weights == "uniform":
        w = [1.0] * len(prices)
    elif weights == "gaussian":
        w = [_phi((k - s0) / (s0 * sigma * math.sqrt(t))) for k in strikes]
    else:
        raise ValueError(f"unknown weights {weights!r}")
    denom = sum(wi * p for wi, p in zip(w, prices, strict=True))
    return [round(budget * wi / denom) for wi in w]


def backtest(raw: dict[str, Any], budget: float, weights: str = "uniform",
             sigma_override: float | None = None) -> tuple[Result, list[dict[str, float]]]:
    """Price the strip at T0, size the single hedge, settle every leg and return the result plus an hourly MtM path."""
    candles = {int(k["t"]): k for k in raw["candles"]}
    s0, s1 = float(candles[T0_MS]["o"]), float(candles[T1_MS - CANDLE_MS]["c"])
    t_years = (T1_MS - T0_MS) / 1000 / SECONDS_PER_YEAR
    sigma = sigma_override if sigma_override is not None else float(raw["dvol"][-1][4]) / 100

    quotes: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    legs_in: list[tuple[dict[str, Any], float, float | None]] = []
    excluded: list[str] = []
    for m in sorted(raw["markets"], key=lambda x: float(x["floor_strike"])):
        cs = raw["kalshi"].get(m["ticker"], [])
        live = [k for k in cs if T0_MS - 3_600_000 <= k["end_period_ts"] * 1000 <= T0_MS and _price(k, "yes_bid") is not None]
        entry = max(live, key=lambda k: k["end_period_ts"]) if live else None  # last quote at or before T0
        bid, ask = _price(entry, "yes_bid"), _price(entry, "yes_ask")
        if bid is None:
            excluded.append(m["ticker"])
            continue
        quotes[m["ticker"]] = sorted((k["end_period_ts"] * 1000, k) for k in cs if _price(k, "yes_bid") is not None)
        iv = implied_vol((bid + ask) / 2, s0, float(m["floor_strike"]), t_years) if ask is not None else None
        legs_in.append((m, 1.0 - bid, iv))

    strikes = [float(m["floor_strike"]) for m, _, _ in legs_in]
    prices = [p for _, p, _ in legs_in]
    sizes = contracts_per_strike(prices, strikes, s0, sigma, t_years, budget, weights)

    legs = []
    for (m, p, iv), n, k in zip(legs_in, sizes, strikes, strict=True):
        delta = -binary_call_delta(s0, k, sigma, t_years)
        legs.append(Leg(ticker=m["ticker"], strike=k, price=p, contracts=n, premium=n * p, fee=kalshi_fee(n, p),
                        delta=n * delta, result=m["result"], payoff=float(n) if one.settled_no(m) else 0.0,
                        sigma_implied=iv))
    delta_total = sum(leg.delta for leg in legs)
    hedge = round(-delta_total, HL_SZ_DECIMALS)

    premium = sum(leg.premium for leg in legs)
    payoff = sum(leg.payoff for leg in legs)
    k_fee = sum(leg.fee for leg in legs)
    perp = hedge * (s1 - s0)
    hl_fees = hl_fee(hedge * s0, maker=False) + hl_fee(hedge * s1, maker=False)

    funding_paid, n_funding = 0.0, 0
    for f in raw["funding"]:
        t = int(f["time"])
        if T0_MS <= t < T1_MS:
            px = float(candles.get(t - t % CANDLE_MS, candles[T0_MS])["o"])  # price at the funding instant
            funding_paid += hedge * px * float(f["fundingRate"])
            n_funding += 1

    path = []
    for t in range(T0_MS, T1_MS + 1, 3_600_000):
        if t == T1_MS:
            value = payoff
        else:
            value = 0.0
            for leg in legs:
                q = next((k for ts, k in reversed(quotes[leg.ticker]) if ts <= t), None)
                bid, ask = _price(q, "yes_bid"), _price(q, "yes_ask")
                no_mid = 1 - (bid + ask) / 2 if bid is not None and ask is not None else leg.price
                value += leg.contracts * no_mid
        s = float(candles.get(t, candles[T1_MS - CANDLE_MS])["o" if t < T1_MS else "c"])
        path.append({"ts_ms": float(t), "S": s, "kalshi_mtm": value - premium, "perp_mtm": hedge * (s - s0)})

    kalshi_pnl = payoff - premium - k_fee
    res = Result(weights=weights, budget=budget, sigma=sigma, hl_entry=s0, hl_exit=s1, delta_total=delta_total,
                 hedge_btc=hedge, kalshi_premium=premium, kalshi_fee=k_fee, kalshi_payoff=payoff,
                 kalshi_pnl=kalshi_pnl, perp_pnl=perp, hl_fees=hl_fees, funding_paid=funding_paid,
                 funding_hours=n_funding, total_pnl=kalshi_pnl + perp - hl_fees - funding_paid,
                 unhedged_pnl=kalshi_pnl, excluded=excluded, legs=legs)
    return res, path


def main() -> None:
    """CLI entry point: fetch, backtest, write result.json and path.json, print totals and the per-leg table."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-strikes", type=int, default=9)
    ap.add_argument("--budget", type=float, default=510.0)
    ap.add_argument("--weights", choices=("uniform", "gaussian"), default="uniform")
    ap.add_argument("--refresh", action="store_true", help="re-download the raw inputs")
    args = ap.parse_args()
    if args.n_strikes % 2 == 0 or args.n_strikes < 1:
        ap.error("--n-strikes must be odd")
    res, path = backtest(load(args.refresh, args.n_strikes), args.budget, args.weights)
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "result.json").write_text(json.dumps(asdict(res), indent=2), encoding="utf-8")
    (CACHE / "path.json").write_text(json.dumps(path), encoding="utf-8")
    for e in res.excluded:
        print(f"excluded (no quote at T0): {e}")
    print(f"{'ticker':<30}{'K':>10}{'p':>7}{'n':>6}{'prime':>9}{'frais':>7}{'delta_i':>11}{'sig_impl':>9}{'payoff':>9}")
    for g in res.legs:
        iv = f"{g.sigma_implied:.3f}" if g.sigma_implied is not None else "n/a"
        print(f"{g.ticker:<30}{g.strike:>10.2f}{g.price:>7.2f}{g.contracts:>6}{g.premium:>9.2f}{g.fee:>7.2f}"
              f"{g.delta:>11.6f}{iv:>9}{g.payoff:>9.2f}")
    for k, v in asdict(res).items():
        if k not in ("legs", "excluded"):
            print(f"{k:>18} : {v}")


if __name__ == "__main__":
    main()
