"""Value types exchanged between the engine and the hedging strategies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from api.models import MarketSpec, OrderBook, PerpSpec

Venue = Literal["hyperliquid", "polymarket"]
Side = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Market state built by the engine at each event."""

    ts_ms: int
    hl_book: OrderBook
    pm_book: OrderBook
    spec: MarketSpec
    perp: PerpSpec
    sigma: float | None
    sigmas: Mapping[str, float | None]


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """Order a strategy asks the engine to simulate."""

    venue: Venue
    kind: Literal["limit", "market", "cancel_all"]
    side: Side | None
    size: float
    limit_price: float | None
    tag: str


@dataclass(frozen=True, slots=True)
class Fill:
    """Simulated execution reported back to the strategy and the ledger."""

    ts_ms: int
    venue: Venue
    side: Side
    size: float
    price: float
    fee: float
    maker: bool
    tag: str
