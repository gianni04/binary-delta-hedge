"""Typed market events and static specs shared by every module."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

Venue = Literal["hyperliquid", "polymarket"]
Side = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class BookLevel:
    """One price level of an order book."""

    price: float
    size: float


@dataclass(frozen=True, slots=True)
class OrderBook:
    """Full-depth snapshot; bids sorted descending, asks ascending."""

    venue: Venue
    instrument: str
    ts_ms: int
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]

    @property
    def best_bid(self) -> float | None:
        """Highest bid price, or None when the bid side is empty."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        """Lowest ask price, or None when the ask side is empty."""
        return self.asks[0].price if self.asks else None

    @property
    def mid(self) -> float | None:
        """Midpoint of best bid and ask, or None if either side is empty."""
        bid, ask = self.best_bid, self.best_ask
        return None if bid is None or ask is None else (bid + ask) / 2.0


@dataclass(frozen=True, slots=True)
class Trade:
    """Executed trade; side is the aggressor's."""

    venue: Venue
    instrument: str
    ts_ms: int
    price: float
    size: float
    side: Side


@dataclass(frozen=True, slots=True)
class VolQuote:
    """Implied-volatility index reading, decimal and annualised."""

    source: Literal["dvol"]
    ts_ms: int
    value: float


@dataclass(frozen=True, slots=True)
class FundingQuote:
    """Hyperliquid hourly funding rate; positive means longs pay."""

    ts_ms: int
    rate_hourly: float


Event = OrderBook | Trade | VolQuote | FundingQuote


@dataclass(frozen=True, slots=True)
class MarketSpec:
    """Polymarket binary 'Bitcoin above K on <date>' market."""

    slug: str
    question: str
    strike: float
    expiry_ms: int
    yes_token_id: str
    tick_size: float
    min_order_size: float
    taker_fee_bps: float
    maker_fee_bps: float


@dataclass(frozen=True, slots=True)
class PerpSpec:
    """Hyperliquid perpetual contract parameters."""

    coin: str
    sz_decimals: int
    max_leverage: int
    min_notional: float = 10.0


def _levels(rows: object) -> tuple[BookLevel, ...]:
    return tuple(BookLevel(float(p), float(s)) for p, s in cast("list[list[float]]", rows))


def event_to_dict(e: Event) -> dict[str, object]:
    """Serialise an event to a JSON-ready dict tagged with a ``kind`` key."""
    if isinstance(e, OrderBook):
        return {
            "kind": "book", "venue": e.venue, "instrument": e.instrument, "ts_ms": e.ts_ms,
            "bids": [[lv.price, lv.size] for lv in e.bids],
            "asks": [[lv.price, lv.size] for lv in e.asks],
        }
    if isinstance(e, Trade):
        return {
            "kind": "trade", "venue": e.venue, "instrument": e.instrument, "ts_ms": e.ts_ms,
            "price": e.price, "size": e.size, "side": e.side,
        }
    if isinstance(e, VolQuote):
        return {"kind": "vol", "source": e.source, "ts_ms": e.ts_ms, "value": e.value}
    return {"kind": "funding", "ts_ms": e.ts_ms, "rate_hourly": e.rate_hourly}


def event_from_dict(d: Mapping[str, object]) -> Event:
    """Rebuild an event from :func:`event_to_dict` output; raises ValueError on unknown kind."""
    kind = d.get("kind")
    ts = int(cast(int, d["ts_ms"]))
    if kind == "book":
        return OrderBook(
            cast(Venue, d["venue"]), str(d["instrument"]), ts, _levels(d["bids"]), _levels(d["asks"])
        )
    if kind == "trade":
        return Trade(
            cast(Venue, d["venue"]), str(d["instrument"]), ts,
            float(cast(float, d["price"])), float(cast(float, d["size"])), cast(Side, d["side"]),
        )
    if kind == "vol":
        return VolQuote("dvol", ts, float(cast(float, d["value"])))
    if kind == "funding":
        return FundingQuote(ts, float(cast(float, d["rate_hourly"])))
    raise ValueError(f"unknown event kind: {kind!r}")
