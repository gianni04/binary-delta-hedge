"""Hyperliquid perp client: contract metadata and the BTC market-data stream."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx
import websockets

from api.models import BookLevel, Event, FundingQuote, OrderBook, PerpSpec, Side, Trade
from api.recorder import resilient

log = logging.getLogger(__name__)

WS_URL = "wss://api.hyperliquid.xyz/ws"
INFO_URL = "https://api.hyperliquid.xyz/info"
PING_INTERVAL_S = 30.0
FUNDING_BUCKET_MS = 3_600_000


async def perp_spec(coin: str = "BTC") -> PerpSpec:
    """Fetch lot decimals and max leverage for ``coin`` from the ``meta`` info endpoint."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(INFO_URL, json={"type": "meta"})
        resp.raise_for_status()
    for asset in resp.json()["universe"]:
        if asset["name"] == coin:
            return PerpSpec(coin, int(asset["szDecimals"]), int(asset["maxLeverage"]))
    raise ValueError(f"{coin} not found in Hyperliquid universe")


def parse_l2book(data: Mapping[str, Any]) -> OrderBook:
    """Convert an ``l2Book`` payload (``levels`` = [bids, asks]) into an OrderBook."""
    bids, asks = data["levels"]

    def levels(rows: list[Mapping[str, str]]) -> tuple[BookLevel, ...]:
        return tuple(BookLevel(float(r["px"]), float(r["sz"])) for r in rows)

    return OrderBook("hyperliquid", str(data["coin"]), int(data["time"]), levels(bids), levels(asks))


def merge_bbo(depth: OrderBook, data: Mapping[str, Any]) -> OrderBook:
    """Overlay a ``bbo`` update on the last ``l2Book``: level 1 = bbo, deeper levels = strictly worse ones."""
    raw_bid, raw_ask = data["bbo"]
    bids, asks = depth.bids, depth.asks
    if raw_bid is not None:
        top = BookLevel(float(raw_bid["px"]), float(raw_bid["sz"]))
        bids = (top, *(lv for lv in depth.bids if lv.price < top.price))
    if raw_ask is not None:
        top = BookLevel(float(raw_ask["px"]), float(raw_ask["sz"]))
        asks = (top, *(lv for lv in depth.asks if lv.price > top.price))
    return OrderBook("hyperliquid", depth.instrument, int(data["time"]), bids, asks)


def parse_trades(data: list[Mapping[str, Any]]) -> list[Trade]:
    """Convert a ``trades`` payload; side ``B`` is a buy aggressor, ``A`` a sell aggressor."""
    out: list[Trade] = []
    for t in data:
        side: Side = "buy" if t["side"] == "B" else "sell"
        out.append(Trade("hyperliquid", str(t["coin"]), int(t["time"]), float(t["px"]), float(t["sz"]), side))
    return out


def parse_funding(data: Mapping[str, Any], ts_ms: int) -> FundingQuote:
    """Build a FundingQuote from an ``activeAssetCtx`` payload (message carries no timestamp)."""
    return FundingQuote(ts_ms, float(data["ctx"]["funding"]))


async def _ping(ws: Any) -> None:
    while True:
        await asyncio.sleep(PING_INTERVAL_S)
        await ws.send(json.dumps({"method": "ping"}))


async def _session(coin: str) -> AsyncIterator[Event]:
    last_bucket = -1
    depth: OrderBook | None = None
    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        for sub in ("l2Book", "bbo", "trades", "activeAssetCtx"):
            await ws.send(json.dumps({"method": "subscribe", "subscription": {"type": sub, "coin": coin}}))
        pinger = asyncio.create_task(_ping(ws))
        try:
            async for raw in ws:
                msg = json.loads(raw)
                channel = msg.get("channel")
                data = msg.get("data")
                if channel == "l2Book" and data["coin"] == coin:
                    depth = parse_l2book(data)
                    yield depth
                elif channel == "bbo" and depth is not None and data["coin"] == coin:
                    depth = merge_bbo(depth, data)
                    yield depth
                elif channel == "trades":
                    for trade in parse_trades(data):
                        if trade.instrument == coin:
                            yield trade
                elif channel == "activeAssetCtx" and data["coin"] == coin:
                    now = int(time.time() * 1000)
                    if now // FUNDING_BUCKET_MS != last_bucket:
                        last_bucket = now // FUNDING_BUCKET_MS
                        yield parse_funding(data, now)
        finally:
            pinger.cancel()


def stream(coin: str = "BTC") -> AsyncIterator[Event]:
    """Reconnecting stream of OrderBook, Trade and hourly FundingQuote events for ``coin``.

    Full ``l2Book`` snapshots (~5 s apart) are refreshed by ``bbo`` updates (several per second).

    Funding is emitted once per UTC hour (first message, then at each hour change).
    """
    return resilient(lambda: _session(coin), "hyperliquid")
