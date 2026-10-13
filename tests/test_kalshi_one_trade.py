import pytest

from backtest.kalshi_one_trade import T0_MS, T1_MS, backtest, kalshi_fee


def test_kalshi_fee_rounds_up_to_cent() -> None:
    assert kalshi_fee(1000, 0.51) == 17.50
    assert kalshi_fee(100, 0.50) == 1.75
    assert kalshi_fee(1, 0.50) == 0.02


def _raw(result: str, s1: float, rates: list[float]) -> dict[str, object]:
    candles = [{"t": t, "o": "83000", "c": str(s1 if t == T1_MS - 3_600_000 else 83000)} for t in range(T0_MS, T1_MS + 1, 3_600_000)]
    quote = {"yes_bid": {"close_dollars": "0.49"}, "yes_ask": {"close_dollars": "0.50"}}
    return {
        "market": {"ticker": "X", "floor_strike": 83000.0, "result": result, "expiration_value": str(s1)},
        "candles": candles,
        "kalshi": [{"end_period_ts": T0_MS // 1000, **quote}],
        "funding": [{"time": T0_MS + 62 + h * 3_600_000, "fundingRate": str(r)} for h, r in enumerate(rates)],
        "dvol": [[T0_MS, 0, 0, 0, 40.0]],
    }


def test_no_loses_premium_hedge_gains_and_funding_sign() -> None:
    res, path = backtest(_raw("yes", 83500.0, [1e-5] * 25), 1000)
    assert res.no_entry == pytest.approx(0.51) and res.kalshi_pnl == pytest.approx(-527.5)
    assert res.hedge_btc > 0 and res.perp_pnl == pytest.approx(res.hedge_btc * 500)
    assert res.funding_hours == 24 and res.funding_paid == pytest.approx(res.hedge_btc * 83000 * 1e-5 * 24)
    assert res.total_pnl == pytest.approx(res.kalshi_pnl + res.perp_pnl - res.hl_fees - res.funding_paid)
    assert path[0]["perp_mtm"] == 0 and path[-1]["kalshi_mtm"] == pytest.approx(-510.0)


def test_no_wins_and_negative_funding_is_received() -> None:
    res, _ = backtest(_raw("no", 82500.0, [-1e-5] * 25), 1000)
    assert res.kalshi_payoff == 1000 and res.perp_pnl < 0 and res.funding_paid < 0


class _Deribit:
    def __init__(self, by_res: dict[str, list[list[float]]]) -> None:
        self.by_res = by_res
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, params: dict[str, object]) -> object:
        self.calls.append(dict(params))
        rows = self.by_res[str(params["resolution"])]
        data = {"result": {"data": rows}}
        return type("R", (), {"json": lambda _s: data})()


def test_fetch_dvol_falls_back_to_hourly_and_keeps_only_bars_closed_by_t0() -> None:
    from backtest.kalshi_one_trade import dvol_known, fetch_dvol
    c = _Deribit({"60": [], "3600": [[T0_MS - 7_200_000, 0, 0, 0, 50.0], [T0_MS - 3_600_000, 0, 0, 0, 51.13]]})
    raw = fetch_dvol(c)  # type: ignore[arg-type]
    assert [p["resolution"] for p in c.calls] == ["60", "3600"] and c.calls[1]["end_timestamp"] == T0_MS - 3_600_000
    assert dvol_known(raw)[-1][4] == 51.13
    minute = {"result": {"data": [[T0_MS - 60_000, 0, 0, 0, 37.90], [T0_MS, 0, 0, 0, 37.89]]}}
    assert dvol_known(minute)[-1][4] == 37.90  # the bar stamped T0 closes at T0+1m: not known at entry


def test_fetch_dvol_never_caches_an_empty_series() -> None:
    from backtest.kalshi_one_trade import fetch_dvol
    assert "error" in fetch_dvol(_Deribit({"60": [], "3600": []}))  # type: ignore[arg-type]
