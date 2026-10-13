import math
from typing import Any

import pytest

from backtest.kalshi_one_trade import T0_MS, T1_MS, kalshi_fee
from backtest.kalshi_strip_trade import backtest, contracts_per_strike, select_strikes
from core.math_engine import SECONDS_PER_YEAR, binary_call_delta
from risk.fees import hl_fee

T = (T1_MS - T0_MS) / 1000 / SECONDS_PER_YEAR
SIGMA = 0.40
S0, S1 = 83000.0, 83500.0
# (strike, yes_bid, yes_ask, result): settlement at 83 500 -> strikes below it resolve "no"
STRIKES = [(82750.0, 0.63, 0.65, "no"), (83000.0, 0.49, 0.50, "no"), (83250.0, 0.38, 0.39, "no"), (83750.0, 0.18, 0.19, "yes")]


def _raw(rate: float = 1e-5, missing: str | None = None) -> dict[str, Any]:
    candles = [{"t": t, "o": str(S0), "c": str(S1 if t == T1_MS - 3_600_000 else S0)} for t in range(T0_MS, T1_MS + 1, 3_600_000)]
    markets = [{"ticker": f"M{int(k)}", "floor_strike": k, "result": r} for k, _, _, r in STRIKES]
    kalshi = {f"M{int(k)}": [{"end_period_ts": T0_MS // 1000, "yes_bid": {"close_dollars": str(b)},
                             "yes_ask": {"close_dollars": str(a)}}] for k, b, a, _ in STRIKES}
    if missing:
        kalshi[missing] = []
    return {
        "markets": markets, "candles": candles, "kalshi": kalshi,
        "funding": [{"time": T0_MS + 62 + h * 3_600_000, "fundingRate": str(rate)} for h in range(25)],
        "dvol": [[T0_MS, 0, 0, 0, SIGMA * 100]],
    }


def test_contracts_fit_budget_uniform_and_gaussian() -> None:
    prices = [1 - b for _, b, _, _ in STRIKES]
    ks = [k for k, *_ in STRIKES]
    uni = contracts_per_strike(prices, ks, S0, SIGMA, T, 510.0, "uniform")
    assert uni == [round(510 / sum(prices))] * 4
    assert abs(sum(n * p for n, p in zip(uni, prices, strict=True)) - 510) <= sum(prices) / 2
    gau = contracts_per_strike(prices, ks, S0, SIGMA, T, 510.0, "gaussian")
    assert abs(sum(n * p for n, p in zip(gau, prices, strict=True)) - 510) <= sum(prices) / 2
    assert gau[1] > gau[3]  # density peaks near S0
    with pytest.raises(ValueError):
        contracts_per_strike(prices, ks, S0, SIGMA, T, 510.0, "bogus")


def test_fee_is_sum_of_per_leg_ceils() -> None:
    res, _ = backtest(_raw(), 510.0)
    assert res.kalshi_fee == pytest.approx(sum(kalshi_fee(g.contracts, g.price) for g in res.legs))
    exact = sum(0.07 * g.contracts * g.price * (1 - g.price) for g in res.legs)
    assert res.kalshi_fee != math.ceil(round(exact * 100, 9)) / 100


def test_delta_total_sum_and_hedge_sign() -> None:
    res, _ = backtest(_raw(), 510.0)
    expected = sum(g.contracts * -binary_call_delta(S0, g.strike, SIGMA, T) for g in res.legs)
    assert res.delta_total == pytest.approx(expected)
    assert res.delta_total == pytest.approx(sum(g.delta for g in res.legs))
    assert res.hedge_btc == pytest.approx(-res.delta_total, abs=1e-5) and res.hedge_btc > 0
    assert round(res.hedge_btc, 5) == res.hedge_btc


def test_payoff_by_result_and_total_pnl() -> None:
    res, path = backtest(_raw(), 510.0)
    assert [g.payoff > 0 for g in res.legs] == [True, True, True, False]
    assert res.kalshi_payoff == sum(g.contracts for g in res.legs[:3])
    assert res.kalshi_pnl == pytest.approx(res.kalshi_payoff - res.kalshi_premium - res.kalshi_fee)
    assert res.perp_pnl == pytest.approx(res.hedge_btc * (S1 - S0))
    assert res.hl_fees == pytest.approx(hl_fee(res.hedge_btc * S0, maker=False) + hl_fee(res.hedge_btc * S1, maker=False))
    assert res.funding_hours == 24 and res.funding_paid == pytest.approx(res.hedge_btc * S0 * 1e-5 * 24)
    assert res.total_pnl == pytest.approx(res.kalshi_pnl + res.perp_pnl - res.hl_fees - res.funding_paid)
    assert path[0]["perp_mtm"] == 0 and path[-1]["kalshi_mtm"] == pytest.approx(res.kalshi_payoff - res.kalshi_premium)
    assert path[0]["kalshi_mtm"] == pytest.approx(
        sum(g.contracts * (1 - (b + a) / 2) for g, (_, b, a, _) in zip(res.legs, STRIKES, strict=True)) - res.kalshi_premium)


def test_strike_without_quote_is_excluded() -> None:
    res, _ = backtest(_raw(missing="M83250"), 510.0)
    assert res.excluded == ["M83250"] and len(res.legs) == 3


def test_select_strikes_grid_around_atm() -> None:
    markets = [{"ticker": str(k), "floor_strike": float(k)} for k in range(81000, 85001, 250)]
    got = [float(m["floor_strike"]) for m in select_strikes(markets, 83040.0, 9)]
    assert got == [82000.0 + 250 * i for i in range(9)]
