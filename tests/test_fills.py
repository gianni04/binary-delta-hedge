"""Tests for sim.fills."""

from __future__ import annotations

import pytest

from api.models import BookLevel, OrderBook, Trade
from sim.fills import RestingOrder, maker_fill, sweep, sweep_levels

BOOK = OrderBook(
    "hyperliquid", "BTC", 0,
    bids=(BookLevel(99.0, 1.0), BookLevel(98.0, 2.0)),
    asks=(BookLevel(101.0, 1.0), BookLevel(102.0, 2.0)),
)


def trade(side: str, price: float, size: float) -> Trade:
    return Trade("hyperliquid", "BTC", 0, price, size, side)  # type: ignore[arg-type]


def test_sweep_walks_levels() -> None:
    assert sweep_levels(BOOK, "buy", 2.0) == [(101.0, 1.0), (102.0, 1.0)]
    px, filled = sweep(BOOK, "buy", 2.0)
    assert filled == 2.0 and px == pytest.approx(101.5)
    assert sweep_levels(BOOK, "sell", 0.5) == [(99.0, 0.5)]


def test_sweep_partial_and_empty() -> None:
    px, filled = sweep(BOOK, "sell", 10.0)
    assert filled == 3.0 and px == pytest.approx((99 + 196) / 3)
    assert sweep(BOOK, "buy", 0.0) == (0.0, 0.0)


def test_maker_sell_needs_strictly_higher_buy() -> None:
    o = RestingOrder("sell", 101.0, 1.0, "t")
    assert maker_fill(o, trade("buy", 101.0, 5)) == 0.0
    assert maker_fill(o, trade("buy", 100.9, 5)) == 0.0
    assert maker_fill(o, trade("sell", 105.0, 5)) == 0.0
    assert maker_fill(o, trade("buy", 101.01, 5)) == 1.0


def test_maker_buy_needs_strictly_lower_sell_and_partial() -> None:
    o = RestingOrder("buy", 99.0, 1.0, "t")
    assert maker_fill(o, trade("sell", 99.0, 5)) == 0.0
    assert maker_fill(o, trade("buy", 90.0, 5)) == 0.0
    assert maker_fill(o, trade("sell", 98.0, 0.4)) == 0.4
