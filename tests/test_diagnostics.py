import math
from pathlib import Path

import pytest

from backtest import kalshi_one_trade as one
from core.math_engine import SECONDS_PER_YEAR, binary_call_delta
from reports import diagnostics as dg


def test_realized_vol_known_returns() -> None:
    r = [0.01, -0.01] * 12
    closes, px = [], 100.0
    for x in r:
        px *= math.exp(x)
        closes.append(px)
    expected = 0.01 * math.sqrt(24 / 23) * math.sqrt(24 * 365)
    assert dg.realized_vol(100.0, closes) == pytest.approx(expected)


def test_hourly_hedge_equals_static_at_t0_and_is_long() -> None:
    legs = [(70000.0, 1000.0)]
    sigma, s0 = 0.5, 70250.0
    t = (one.T1_MS - one.T0_MS) / 1000 / SECONDS_PER_YEAR
    static = round(1000 * binary_call_delta(s0, 70000.0, sigma, t), one.HL_SZ_DECIMALS)
    hourly = dg.hourly_hedge(legs, sigma, [s0] * 24)
    assert hourly[0] == pytest.approx(static, abs=1e-5)
    assert all(h > 0 for h in hourly)


def test_final_funding_is_minus_sum_of_funding_paid(tmp_path: Path) -> None:
    def rows(structure: str, source: str) -> list[dict[str, str]]:
        return [{"date": f"2026-03-{d:02d}", "structure": structure, "sigma_source": source, "funding_paid": f,
                 "hedge_btc": "0.2"} for d, f in ((19, "1.5"), (20, "-0.25"), (21, "0.5"))]

    stats = dg.funding(rows("single", "dvol") + rows("strip", "dvol"),
                       rows("put_spread", "") + rows("put", ""), tmp_path / "f.png")
    assert {v["funding_cumul_final"] for v in stats.values()} == {-1.75}
