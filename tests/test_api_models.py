"""Models round-trip and client parsers on real captured messages."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api import deribit, hyperliquid, polymarket
from api.models import (
    BookLevel, Event, FundingQuote, MarketSpec, OrderBook, Trade, VolQuote,
    event_from_dict, event_to_dict,
)

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((FIX / name).read_text(encoding="utf-8"))
    return data


def test_order_book_properties() -> None:
    book = OrderBook("polymarket", "x", 1, (BookLevel(0.4, 1), BookLevel(0.3, 2)), (BookLevel(0.5, 1),))
    assert (book.best_bid, book.best_ask) == (0.4, 0.5)
    assert book.mid == pytest.approx(0.45)
    empty = OrderBook("polymarket", "x", 1, (), ())
    assert empty.best_bid is None and empty.best_ask is None and empty.mid is None


def test_event_roundtrip() -> None:
    events: list[Event] = [
        OrderBook("hyperliquid", "BTC", 5, (BookLevel(10.0, 1.5),), (BookLevel(11.0, 2.0),)),
        Trade("polymarket", "tok", 6, 0.42, 10.0, "sell"),
        VolQuote("dvol", 7, 0.38),
        FundingQuote(8, 1.25e-5),
    ]
    for e in events:
        d = event_to_dict(e)
        assert event_from_dict(json.loads(json.dumps(d))) == e


def test_unknown_kind() -> None:
    with pytest.raises(ValueError):
        event_from_dict({"kind": "nope", "ts_ms": 1})


def test_hyperliquid_real_messages() -> None:
    fx = load("hyperliquid_ws.json")
    book = hyperliquid.parse_l2book(json.loads(str(fx["l2Book"]))["data"])
    assert book.venue == "hyperliquid" and book.instrument == "BTC"
    assert book.best_bid is not None and book.best_ask is not None and book.best_bid < book.best_ask
    assert [lv.price for lv in book.bids] == sorted((lv.price for lv in book.bids), reverse=True)
    trades = hyperliquid.parse_trades(json.loads(str(fx["trades"]))["data"])
    assert trades and all(t.side in ("buy", "sell") and t.size > 0 for t in trades)
    assert trades[0].side == "buy"
    funding = hyperliquid.parse_funding(json.loads(str(fx["activeAssetCtx"]))["data"], 123)
    assert funding == FundingQuote(123, 0.0000125)


def test_deribit_real_message() -> None:
    msg = json.loads(str(load("deribit_ws.json")["subscription"]))
    q = deribit.parse_dvol(msg["params"])
    assert q.source == "dvol" and q.value == pytest.approx(0.3799)
    assert q.ts_ms == 1791793170417


def test_polymarket_real_stream() -> None:
    fx = load("polymarket_ws.json")
    book_msg = json.loads(str(fx["book"]))[0]
    local = polymarket.LocalBook(book_msg["asset_id"])
    first = polymarket.handle_message(local, book_msg)
    assert isinstance(first, OrderBook) and first.bids and first.asks
    assert first.venue == "polymarket" and first.ts_ms == 1791793170942
    before = {lv.price: lv.size for lv in first.bids}
    for raw in fx["price_change"]:  # type: ignore[attr-defined]
        polymarket.handle_message(local, json.loads(raw))
    assert before != {lv.price: lv.size for lv in local.book(0).bids}
    last = polymarket.handle_message(local, json.loads(str(fx["last_trade_price"])))
    assert last is None  # trade belongs to another token than the captured book


def test_polymarket_trade_and_delta() -> None:
    local = polymarket.LocalBook("T")
    local.snapshot({"bids": [{"price": "0.4", "size": "5"}], "asks": [{"price": "0.5", "size": "5"}]})
    out = polymarket.handle_message(local, {
        "event_type": "price_change", "timestamp": "9",
        "price_changes": [
            {"asset_id": "T", "price": "0.41", "size": "7", "side": "BUY"},
            {"asset_id": "T", "price": "0.5", "size": "0", "side": "SELL"},
            {"asset_id": "OTHER", "price": "0.9", "size": "1", "side": "SELL"},
        ],
    })
    assert isinstance(out, OrderBook) and out.best_bid == 0.41 and out.asks == ()
    trade = polymarket.handle_message(local, {
        "event_type": "last_trade_price", "asset_id": "T", "price": "0.42", "size": "3",
        "side": "SELL", "timestamp": "10",
    })
    assert trade == Trade("polymarket", "T", 10, 0.42, 3.0, "sell")


def test_gamma_market_parsing() -> None:
    event = load("gamma_event.json")
    specs = [s for m in event["markets"] if (s := polymarket.parse_market(m)) is not None]  # type: ignore[attr-defined]
    assert len(specs) == 2
    spec = specs[0]
    assert isinstance(spec, MarketSpec)
    assert spec.slug == "bitcoin-above-82k-on-october-13-2026"
    assert spec.strike == 82_000.0 and spec.expiry_ms == 1_791_907_200_000
    assert spec.tick_size == 0.01 and spec.min_order_size == 5.0
    assert spec.taker_fee_bps == pytest.approx(700.0) and spec.maker_fee_bps == 0.0
    assert spec.yes_token_id.isdigit()


def test_hyperliquid_meta_fixture() -> None:
    btc = load("hyperliquid_meta.json")["BTC"]
    assert btc["szDecimals"] == 5 and btc["maxLeverage"] == 40  # type: ignore[index]


def test_best_mismatch_triggers_resync() -> None:
    polymarket.STATS.update(price_changes=0, book_mismatches=0)
    local = polymarket.LocalBook("T")
    local.snapshot({"bids": [{"price": "0.4", "size": "5"}], "asks": [{"price": "0.5", "size": "5"}]})
    good = {"event_type": "price_change", "timestamp": "1", "price_changes": [
        {"asset_id": "T", "price": "0.41", "size": "7", "side": "BUY", "best_bid": "0.41", "best_ask": "0.5"}]}
    polymarket.handle_message(local, good)
    assert not local.desynced and polymarket.STATS["book_mismatches"] == 0
    bad = {"event_type": "price_change", "timestamp": "2", "price_changes": [
        {"asset_id": "T", "price": "0.3", "size": "7", "side": "BUY", "best_bid": "0.42", "best_ask": "0.5"}]}
    polymarket.handle_message(local, bad)
    assert local.desynced and polymarket.STATS == {"price_changes": 2, "book_mismatches": 1}
    local.snapshot({"bids": [], "asks": []})
    assert not local.desynced


def test_hyperliquid_bbo_merge() -> None:
    fx = load("hyperliquid_ws.json")
    depth = hyperliquid.parse_l2book(json.loads(str(fx["l2Book"]))["data"])
    real = json.loads(str(load("hyperliquid_bbo.json")["bbo"]))["data"]
    merged = hyperliquid.merge_bbo(depth, real)
    assert merged.ts_ms == real["time"] and merged.bids[0].price == 83678.0 and merged.asks[0].price == 83679.0

    base = OrderBook("hyperliquid", "BTC", 1,
                     (BookLevel(100, 1), BookLevel(99, 2), BookLevel(98, 3)),
                     (BookLevel(101, 1), BookLevel(102, 2), BookLevel(103, 3)))
    up = hyperliquid.merge_bbo(base, {"time": 5, "bbo": [{"px": "99", "sz": "7", "n": 1}, {"px": "102", "sz": "4", "n": 1}]})
    assert [(lv.price, lv.size) for lv in up.bids] == [(99, 7), (98, 3)]
    assert [(lv.price, lv.size) for lv in up.asks] == [(102, 4), (103, 3)]
    wide = hyperliquid.merge_bbo(base, {"time": 6, "bbo": [{"px": "100.5", "sz": "1", "n": 1}, None]})
    assert [lv.price for lv in wide.bids] == [100.5, 100, 99, 98] and wide.asks == base.asks
