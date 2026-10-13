from __future__ import annotations

import math
from datetime import date
from statistics import NormalDist
from typing import Any

import pytest

from backtest import kalshi_strip_trade as strip

from backtest.deribit_benchmark import (
    Excluded,
    Snap,
    bs_put,
    bs_put_delta,
    deribit_fee,
    evaluate,
    instrument_name,
    resolve_strike,
    grid_strike,
    strip_params,
    snapshot,
)

T0 = 1_000_000_000_000
T1 = T0 + 86_400_000
EXPIRY = T1 + 11 * 3_600_000
S = 66_000.0


def trade(ts: int, k: float, iv: float = 50.0, price: float = 0.01, mark: float = 0.0095, index: float = S
          ) -> dict[str, Any]:
    return {"instrument_name": f"BTC-5APR26-{k:.0f}-P", "timestamp": ts, "price": price, "mark_price": mark,
            "iv": iv, "index_price": index, "amount": 1.0, "direction": "buy"}


def book(t: int, trades: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    tr = trades or [trade(t - 60_000 * i, 66_000 + 1000 * i, iv=50 + i) for i in range(5)]
    return {"trades": tr, "spot": [t - 1000, S], "other_hs": None}


def hl() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hours = range(T0, T1, 3_600_000)
    candles = [{"t": t, "o": str(S), "c": str(S + 500)} for t in hours]
    return candles, [{"time": t, "fundingRate": "0.00001"} for t in hours]


def test_instrument_name_no_leading_zero() -> None:
    assert instrument_name(date(2026, 4, 4), 66000, "P") == "BTC-4APR26-66000-P"
    assert instrument_name(date(2026, 7, 14), 70500.0, "P") == "BTC-14JUL26-70500-P"


def test_resolve_strike_nearest() -> None:
    ks = [65000.0, 65500.0, 66500.0, 67500.0]
    assert resolve_strike(ks, 66200) == 66500.0
    assert resolve_strike(ks, 60000) == 65000.0
    assert resolve_strike(ks, 66000) == 65500.0  # tie -> lower


def test_put_call_parity_and_delta_sign() -> None:
    s, k, sig, tau = 66_000.0, 67_000.0, 0.5, 35 / 8760
    v = sig * tau**0.5
    call = s * NormalDist().cdf((math.log(s / k) + 0.5 * v * v) / v) - k * NormalDist().cdf(
        (math.log(s / k) - 0.5 * v * v) / v)
    assert call - bs_put(s, k, sig, tau) == pytest.approx(s - k)
    assert -1 < bs_put_delta(s, k, sig, tau) < 0


def test_fee_cap_at_12_5_percent() -> None:
    assert deribit_fee(66_000, 1.0, 1000.0) == pytest.approx(19.8)
    assert deribit_fee(66_000, 1.0, 50.0) == pytest.approx(6.25)


def leg(k: float, n: int = 40) -> strip.Leg:
    return strip.Leg("T", k, 0.5, n, 0.5 * n, 0.0, 0.0, "no", 0.0, None)


def test_grid_strike_and_five_leg_day() -> None:
    assert grid_strike(66_250.0) == 66_500.0 and grid_strike(65_749.0) == 65_500.0
    legs = [leg(65_000.0 + 500 * i) for i in range(5)]  # 5 legs, step 500
    p = strip_params(legs)
    assert p["step"] == 500 and p["q"] == 40 / 500
    k_long, k_short = grid_strike(p["k_hi"] + 250), grid_strike(p["k_lo"] - 250)
    assert (k_long, k_short) == (67_500.0, 65_000.0)
    with pytest.raises(ValueError):
        strip_params([leg(65_000.0, 40), leg(65_250.0, 41)])


def test_snapshot_ignores_future_trades_and_needs_three() -> None:
    past = book(T0)["trades"]
    future = [trade(T0 + 10_000, 70_000, iv=300, index=99_999.0, price=1.0, mark=0.0)]
    a = snapshot(book(T0, past), T0)
    b = snapshot({**book(T0, past + future), "spot": [T0 + 10_000, 99_999.0]}, T0)
    assert a == b and b.spot == S and b.n_trades == 5
    with pytest.raises(Excluded):
        snapshot(book(T0, past[:2] + future), T0)


def test_total_identity_and_hedge_sign() -> None:
    candles, funding = hl()
    r = evaluate([(1, 67_000.0)], 1.0, snapshot(book(T0), T0), snapshot(book(T1), T1), EXPIRY, candles, funding)
    assert r["hedge_btc"] > 0  # long put -> long perp
    fees = r["fee_deribit_entry"] + r["fee_deribit_exit"] + r["hl_fees"]
    assert r["total_pnl"] == pytest.approx(r["option_pnl"] + r["perp_pnl"] - fees - r["funding_paid"])
    assert r["premium_entry"] > 0 and r["funding_paid"] > 0


def test_put_spread_hedge_smaller_than_long_leg() -> None:
    candles, funding = hl()
    s0, s1 = snapshot(book(T0), T0), snapshot(book(T1), T1)
    one = evaluate([(1, 67_000.0)], 1.0, s0, s1, EXPIRY, candles, funding)
    spread = evaluate([(1, 67_000.0), (-1, 64_000.0)], 1.0, s0, s1, EXPIRY, candles, funding)
    assert 0 < spread["hedge_btc"] < one["hedge_btc"]


def test_smile_log_moneyness_interpolation() -> None:
    sn = Snap(T0, 100.0, ((math.log(0.9), 0.4), (math.log(1.1), 0.6)), 0.0, 2, "expiry")
    assert sn.iv(100.0) == pytest.approx(0.5, abs=0.01)  # x = 0 sits near the midpoint
    assert sn.iv(50.0) == 0.4 and sn.iv(200.0) == 0.6  # flat outside
    wide = Snap(T0, 200.0, sn.smile, 0.0, 2, "expiry")
    assert wide.iv(200.0) == sn.iv(100.0)  # same moneyness, same IV whatever the spot


def test_spread_fallback_and_combo_discount() -> None:
    d = book(T0)
    d["trades"] = [trade(T0 - 1000 * i, 66_000 + 500 * i, price=None, mark=None) for i in range(4)]  # type: ignore[arg-type]
    d["other_hs"] = 0.002
    sn = snapshot(d, T0)
    assert sn.spread_source == "other_expiries" and sn.half_spread_btc == 0.002
    candles, funding = hl()
    r = evaluate([(1, 67_000.0), (-1, 64_000.0)], 1.0, snapshot(book(T0), T0), snapshot(book(T1), T1), EXPIRY,
                 candles, funding)
    assert r["fee_combo_variant"] < r["fee_deribit_entry"] + r["fee_deribit_exit"]
