"""Tests for sim.ledger."""

from __future__ import annotations

import io
import json

import pytest

from sim.ledger import HOUR_MS, Ledger
from strategies.types import Fill


def lines(buf: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(x) for x in buf.getvalue().splitlines()]


def test_cash_pnl_and_fees() -> None:
    buf = io.StringIO()
    lg = Ledger("x", buf)
    lg.on_fill(Fill(1, "polymarket", "buy", 100.0, 0.5, 1.5, False, "entry_pm"))
    lg.on_fill(Fill(2, "hyperliquid", "sell", 0.2, 100_000.0, 0.9, False, "dyn_rebal"))
    assert lg.pm_shares == 100.0 and lg.hl_position == -0.2
    assert lg.pnl_pm(0.6) == pytest.approx(10.0)
    assert lg.pnl_hl(101_000.0) == pytest.approx(-200.0)
    lg.mark(3, 101_000.0, 0.6, 0.5, {"implied": 0.5, "dvol": None, "ewma": None}, "implied", 0.15)
    rec = lines(buf)[-1]
    assert rec["pnl_total"] == pytest.approx(10.0 - 200.0 - 1.5 - 0.9)
    assert rec["net_delta_btc"] == pytest.approx(0.15 - 0.2)
    assert rec["sigma_used_source"] == "implied"
    assert [r["type"] for r in lines(buf)] == ["fill", "fill", "mark"]


def test_funding_on_hour_crossing() -> None:
    lg = Ledger("x", io.StringIO())
    lg.funding_rate = 1e-4
    lg.on_fill(Fill(0, "hyperliquid", "buy", 0.5, 100_000.0, 0.0, False, "t"))
    lg.advance(HOUR_MS - 10, 100_000.0)
    assert lg.funding == 0.0
    lg.advance(HOUR_MS + 5, 100_000.0)
    assert lg.funding == pytest.approx(0.5 * 100_000.0 * 1e-4)
    lg.advance(HOUR_MS + 10_000, 100_000.0)
    assert lg.funding == pytest.approx(5.0)


def test_mark_throttled_to_one_per_second() -> None:
    buf = io.StringIO()
    lg = Ledger("x", buf)
    args: tuple[float, float, float | None, dict[str, float | None], str | None, float] = (100.0, 0.5, None, {}, None, 0.0)
    assert lg.mark(1000, *args)
    assert not lg.mark(1500, *args)
    assert lg.mark(2000, *args)
    assert lg.mark(2001, *args, force=True)
    assert len(lines(buf)) == 3
