"""One-shot backtest: long NO on a Kalshi BTC daily binary, delta-hedged once with a Hyperliquid BTC perp.

Open 2026-10-10 17:00 EDT (21:00 UTC) on the ATM strike of KXBTCD-26OCT1117, hold to the 2026-10-11 17:00 EDT
close. The hedge is sized once at entry (h = Q·|Δ|, long perp), never rebalanced, closed at the same instant
the Kalshi market closes. Every input is fetched from public historical endpoints and cached as raw JSON under
``data/kalshi_one_trade/`` so the result is reproducible offline::

    python -m backtest.kalshi_one_trade [--quantity 1000] [--refresh]
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

from core.math_engine import SECONDS_PER_YEAR, binary_call_delta, implied_vol
from risk.fees import hl_fee

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
HL = "https://api.hyperliquid.xyz/info"
DERIBIT = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
EVENT = "KXBTCD-26OCT1117"
T0_MS = 1_791_666_000_000  # 2026-10-10T21:00:00Z = 17:00 EDT
T1_MS = 1_791_752_400_000  # 2026-10-11T21:00:00Z = 17:00 EDT, Kalshi close_time
KALSHI_TAKER_RATE = 0.07   # series KXBTCD: fee_type "quadratic", fee_multiplier 1
HL_SZ_DECIMALS = 5
CANDLE_MS = 3_600_000  # 1h HL candles: 1m history is only ~5000 bars (~3.5 days); T0 open / T1 close are identical
CACHE = Path("data/kalshi_one_trade")


def kalshi_fee(contracts: float, price: float) -> float:
    """Kalshi taker fee: round up to the next cent of 0.07 · C · P · (1 − P) (kalshi.com/docs/kalshi-fee-schedule.pdf)."""
    return math.ceil(round(KALSHI_TAKER_RATE * contracts * price * (1 - price) * 100, 9)) / 100


def _cached(name: str, fetch: Any, refresh: bool) -> Any:
    path = CACHE / f"{name}.json"
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
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def event_markets(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Markets of a cached event payload, whichever layout the endpoint used."""
    return list(event.get("markets") or event.get("event", {}).get("markets") or [])


def fetch_event(c: httpx.Client) -> dict[str, Any]:
    """Event with its markets; settled events older than ~2 months only list them under /historical/markets."""
    event: dict[str, Any] = c.get(f"{KALSHI}/events/{EVENT}", params={"with_nested_markets": "true"}).json()
    if not event_markets(event) and "error" not in event:
        hist = c.get(f"{KALSHI}/historical/markets", params={"event_ticker": EVENT, "limit": 200}).json()
        if "error" in hist or not hist.get("markets"):
            return {"error": hist.get("error", "no markets yet")}  # _cached retries instead of caching an empty grid
        event["markets"] = hist["markets"]
    return event


def fetch_candles(c: httpx.Client, ticker: str) -> Any:
    """1m candlesticks of one market around the window, from the live or the historical (archived) endpoint."""
    params = {"start_ts": T0_MS // 1000 - 3600, "end_ts": T1_MS // 1000, "period_interval": 1}
    r = c.get(f"{KALSHI}/series/KXBTCD/markets/{ticker}/candlesticks", params=params)
    if r.status_code == 404:
        r = c.get(f"{KALSHI}/historical/markets/{ticker}/candlesticks", params=params)
    return r.json()


def fetch_dvol(c: httpx.Client) -> Any:
    """DVOL up to T0: 1m bars, else (Deribit keeps 1m ~6 months) hourly bars ending with the one whose close is T0."""
    params: dict[str, Any] = {"currency": "BTC", "start_timestamp": T0_MS - 3_600_000, "end_timestamp": T0_MS, "resolution": "60"}
    r = c.get(DERIBIT, params=params).json()
    if r.get("result", {}).get("data"):
        return r
    params.update(start_timestamp=T0_MS - 3 * 3_600_000, end_timestamp=T0_MS - 3_600_000, resolution="3600")
    r = c.get(DERIBIT, params=params).json()
    return r if r.get("result", {}).get("data") else {"error": "no DVOL before T0"}


def load(refresh: bool) -> dict[str, Any]:
    """Fetch (or read from cache) every raw input of the backtest."""
    with httpx.Client(timeout=30) as c:
        event = _cached("event", lambda: fetch_event(c), refresh)
        candles = _cached("hl_candles_1h", lambda: c.post(HL, json={"type": "candleSnapshot", "req": {
            "coin": "BTC", "interval": "1h", "startTime": T0_MS, "endTime": T1_MS}}).json(), refresh)
        s0 = float(candles[0]["o"])
        atm = min(event_markets(event), key=lambda m: abs(float(m["floor_strike"]) - s0))
        kalshi = _cached("kalshi_candles_1m", lambda: fetch_candles(c, atm["ticker"]), refresh)
        funding = _cached("hl_funding", lambda: c.post(HL, json={
            "type": "fundingHistory", "coin": "BTC", "startTime": T0_MS, "endTime": T1_MS}).json(), refresh)
        dvol = _cached("deribit_dvol", lambda: fetch_dvol(c), refresh)
    return {"market": atm, "candles": candles, "kalshi": kalshi["candlesticks"], "funding": funding, "dvol": dvol_known(dvol)}


def dvol_known(dvol: dict[str, Any]) -> list[list[float]]:
    """Bars whose close is known at T0: a bar stamped t closes at t + resolution, so keep t < T0."""
    return [b for b in dvol["result"]["data"] if b[0] < T0_MS]


def settled_no(market: dict[str, Any]) -> bool:
    """True if the market settled NO; an unsettled or unknown result is an error, never a silent zero payoff."""
    if market.get("result") not in ("yes", "no"):
        raise ValueError(f"{market.get('ticker')}: unsettled result {market.get('result')!r}")
    return bool(market["result"] == "no")


def _price(candle: dict[str, Any], side: str) -> float | None:
    q = candle.get(side, {})
    v = q.get("close_dollars", q.get("close"))  # live vs historical candlestick schema
    return float(v) if v is not None else None


@dataclass(frozen=True, slots=True)
class Result:
    """Every number of the trade, in USD unless stated."""

    ticker: str
    strike: float
    settlement_brti: float
    result: str
    contracts: float
    no_entry: float
    yes_mid_entry: float
    sigma: float
    sigma_source: str
    delta_no_per_contract: float
    hedge_btc: float
    hl_entry: float
    hl_exit: float
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


def backtest(raw: dict[str, Any], contracts: float, sigma_override: float | None = None) -> tuple[Result, list[dict[str, float]]]:
    """Price the entry, size the one-off hedge, settle both legs and return the result plus an hourly MtM path."""
    m = raw["market"]
    strike = float(m["floor_strike"])
    candles = {int(k["t"]): k for k in raw["candles"]}
    s0, s1 = float(candles[T0_MS]["o"]), float(candles[T1_MS - CANDLE_MS]["c"])
    # Kalshi only emits a 1m candle when something changed: the live quote at T0 is the last one at or before T0
    entry = max((k for k in raw["kalshi"] if T0_MS - 3_600_000 <= k["end_period_ts"] * 1000 <= T0_MS
                 and _price(k, "yes_bid") is not None), key=lambda k: k["end_period_ts"])
    yes_bid, yes_ask = _price(entry, "yes_bid"), _price(entry, "yes_ask")
    assert yes_bid is not None and yes_ask is not None, "no Kalshi quote at entry"
    no_entry = 1.0 - yes_bid                     # buy NO = hit the YES bid
    yes_mid = (yes_bid + yes_ask) / 2
    t_years = (T1_MS - T0_MS) / 1000 / SECONDS_PER_YEAR

    sigma, source = implied_vol(yes_mid, s0, strike, t_years), "kalshi implied"
    if sigma_override is not None:
        sigma, source = sigma_override, "override"
    elif sigma is None:  # S < K and mid above N(-sqrt(2|ln S/K|)): no implied root
        sigma, source = float(raw["dvol"][-1][4]) / 100, "deribit DVOL"
    delta_no = -binary_call_delta(s0, strike, sigma, t_years)
    hedge = round(contracts * -delta_no, HL_SZ_DECIMALS)

    payoff = contracts * (1.0 if settled_no(m) else 0.0)
    premium = contracts * no_entry
    k_fee = kalshi_fee(contracts, no_entry)
    perp = hedge * (s1 - s0)
    hl_fees = hl_fee(hedge * s0, maker=False) + hl_fee(hedge * s1, maker=False)

    funding_paid, path = 0.0, []
    for f in raw["funding"]:
        t = int(f["time"])
        if T0_MS <= t < T1_MS:  # paid while held: the print stamped at T0 counts, the one at T1 is after the close
            px = float(candles.get(t - t % CANDLE_MS, candles[T0_MS])["o"])  # price at the funding instant
            funding_paid += hedge * px * float(f["fundingRate"])  # positive rate: longs pay
    n_funding = sum(1 for f in raw["funding"] if T0_MS <= int(f["time"]) < T1_MS)

    quoted = sorted((k["end_period_ts"] * 1000, k) for k in raw["kalshi"] if _price(k, "yes_bid") is not None)
    for t in range(T0_MS, T1_MS + 1, 3_600_000):
        k = next((q for ts, q in reversed(quoted) if ts <= t), None)  # last quote at or before t
        bid = _price(k, "yes_bid") if k else None
        ask = _price(k, "yes_ask") if k else None
        s = float(candles.get(t, candles[T1_MS - CANDLE_MS])["o" if t < T1_MS else "c"])
        no_mark = payoff / contracts if t == T1_MS else (1 - (bid + ask) / 2 if bid is not None and ask is not None else None)
        path.append({"ts_ms": float(t), "S": s, "no_mark": no_mark if no_mark is not None else float("nan"),
                     "kalshi_mtm": contracts * no_mark - premium if no_mark is not None else float("nan"),
                     "perp_mtm": hedge * (s - s0)})

    kalshi_pnl = payoff - premium - k_fee
    res = Result(
        ticker=m["ticker"], strike=strike, settlement_brti=float(m["expiration_value"]), result=m["result"],
        contracts=contracts, no_entry=no_entry, yes_mid_entry=yes_mid, sigma=sigma, sigma_source=source,
        delta_no_per_contract=delta_no, hedge_btc=hedge, hl_entry=s0, hl_exit=s1,
        kalshi_premium=premium, kalshi_fee=k_fee, kalshi_payoff=payoff, kalshi_pnl=kalshi_pnl,
        perp_pnl=perp, hl_fees=hl_fees, funding_paid=funding_paid, funding_hours=n_funding,
        total_pnl=kalshi_pnl + perp - hl_fees - funding_paid, unhedged_pnl=kalshi_pnl,
    )
    return res, path


def plot(res: Result, path: list[dict[str, float]], out: Path) -> None:
    """Two panels on one time axis: BTC vs strike and settlement, then cumulative PnL per leg."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from datetime import UTC, datetime

    t = [datetime.fromtimestamp(p["ts_ms"] / 1000, tz=UTC) for p in path]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    for ax in (a1, a2):
        ax.set_facecolor("#fcfcfb")
        ax.grid(axis="y", color="#e4e3df", lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.patch.set_facecolor("#fcfcfb")
    a1.plot(t, [p["S"] for p in path], color="#2a78d6", lw=1.4, label="BTC (Hyperliquid perp)")
    a1.axhline(res.strike, color="#52514e", lw=0.9, ls=(0, (4, 3)), label=f"strike {res.strike:,.2f}")
    a1.plot(t[-1], res.settlement_brti, "o", color="#e34948", ms=6, label=f"settlement BRTI {res.settlement_brti:,.2f}")
    a1.set_title("BTC, 2026-10-10 17:00 EDT → 2026-10-11 17:00 EDT", loc="left", fontsize=10)
    a1.legend(fontsize=8, frameon=False)
    kal = [p["kalshi_mtm"] for p in path]
    perp = [p["perp_mtm"] for p in path]
    a2.plot(t, kal, color="#eb6834", lw=1.4, label="Kalshi long NO (mid, before fees)")
    a2.plot(t, perp, color="#1baf7a", lw=1.4, label=f"Hyperliquid long perp {res.hedge_btc} BTC")
    a2.plot(t, [k + p for k, p in zip(kal, perp)], color="#0b0b0b", lw=1.6, label="combined")
    a2.axhline(0, color="#52514e", lw=0.6)
    a2.set_ylabel("$", fontsize=9)
    a2.set_title("Mark-to-market per leg (hourly)", loc="left", fontsize=10)
    a2.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=300, facecolor="#fcfcfb")
    plt.close(fig)


def main() -> None:
    """CLI entry point: fetch, backtest, write JSON result and hourly path."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quantity", type=float, default=1000.0)
    ap.add_argument("--refresh", action="store_true", help="re-download the raw inputs")
    args = ap.parse_args()
    res, path = backtest(load(args.refresh), args.quantity)
    (CACHE / "result.json").write_text(json.dumps(asdict(res), indent=2), encoding="utf-8")
    (CACHE / "path.json").write_text(json.dumps(path), encoding="utf-8")
    plot(res, path, Path("reports/kalshi_one_trade.png"))
    for k, v in asdict(res).items():
        print(f"{k:>24} : {v}")


if __name__ == "__main__":
    main()
