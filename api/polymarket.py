"""Polymarket client: Gamma market discovery and the CLOB ``market`` WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from typing import Any

import httpx
import websockets

from api.models import BookLevel, Event, MarketSpec, OrderBook, Side, Trade
from api.recorder import resilient

log = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com"
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PING_INTERVAL_S = 10.0
STATS: dict[str, int] = {"price_changes": 0, "book_mismatches": 0}
DAILY_SLUG = re.compile(r"^bitcoin-above-on-[a-z]+-\d{1,2}-\d{4}$")
STRIKE = re.compile(r"above \$([\d,]+(?:\.\d+)?)")


def parse_market(market: Mapping[str, Any]) -> MarketSpec | None:
    """Build a MarketSpec from a Gamma market object, or None if it is not a tradable BTC-above market.

    Fee bps come from ``feeSchedule``: ``rate`` x 10 000 is the taker coefficient of
    ``fee = shares x rate x p x (1 - p)``; makers pay nothing when ``takerOnly``.
    """
    match = STRIKE.search(str(market.get("question", "")))
    if not match or not market.get("acceptingOrders") or market.get("closed"):
        return None
    outcomes = json.loads(market["outcomes"])
    tokens = json.loads(market["clobTokenIds"])
    if "Yes" not in outcomes:
        return None
    schedule = market.get("feeSchedule") or {}
    rate_bps = round(float(schedule.get("rate", 0.0)) * 10_000.0, 6) if market.get("feesEnabled") else 0.0
    expiry = datetime.fromisoformat(str(market["endDate"]).replace("Z", "+00:00"))
    return MarketSpec(
        slug=str(market["slug"]),
        question=str(market["question"]),
        strike=float(match.group(1).replace(",", "")),
        expiry_ms=int(expiry.timestamp() * 1000),
        yes_token_id=str(tokens[outcomes.index("Yes")]),
        tick_size=float(market["orderPriceMinTickSize"]),
        min_order_size=float(market["orderMinSize"]),
        taker_fee_bps=rate_bps,
        maker_fee_bps=0.0 if schedule.get("takerOnly") else rate_bps,
    )


async def find_btc_above_markets() -> list[MarketSpec]:
    """List active daily 'Bitcoin above K on <date>' markets, sorted by expiry then strike."""
    async with httpx.AsyncClient(base_url=GAMMA_URL, timeout=20.0) as client:
        resp = await client.get(
            "/public-search",
            params={"q": "Bitcoin above", "events_status": "active", "limit_per_type": 50},
        )
        resp.raise_for_status()
        events = [e for e in resp.json()["events"] if DAILY_SLUG.match(e["slug"]) and not e.get("closed")]
        specs: list[MarketSpec] = []
        for event in events:
            full = await client.get("/events", params={"slug": event["slug"]})
            full.raise_for_status()
            for market in full.json()[0]["markets"]:
                spec = parse_market(market)
                if spec is not None:
                    specs.append(spec)
    now_ms = int(time.time() * 1000)
    return sorted((s for s in specs if s.expiry_ms > now_ms), key=lambda s: (s.expiry_ms, s.strike))


def _levels(rows: list[Mapping[str, str]]) -> dict[float, float]:
    return {float(r["price"]): float(r["size"]) for r in rows}


class LocalBook:
    """Order book rebuilt from ``book`` snapshots and ``price_change`` deltas for one token."""

    def __init__(self, token_id: str) -> None:
        self.token_id = token_id
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.desynced = False

    def snapshot(self, msg: Mapping[str, Any]) -> None:
        """Replace both sides with the snapshot contents."""
        self.bids, self.asks = _levels(msg["bids"]), _levels(msg["asks"])
        self.desynced = False

    def check_best(self, change: Mapping[str, str]) -> bool:
        """Compare the venue's reported best bid/ask with the local book; flag and count a mismatch."""
        bid = max(self.bids) if self.bids else None
        ask = min(self.asks) if self.asks else None
        ok = all(
            (local is None and not float(rep or 0)) or (local is not None and abs(local - float(rep or 0)) < 1e-9)
            for local, rep in ((bid, change.get("best_bid")), (ask, change.get("best_ask")))
            if rep is not None
        )
        STATS["price_changes"] += 1
        if not ok:
            STATS["book_mismatches"] += 1
            self.desynced = True
            log.warning("polymarket: local best %s/%s != reported %s/%s, resyncing",
                        bid, ask, change.get("best_bid"), change.get("best_ask"))
        return ok

    def apply_change(self, change: Mapping[str, str]) -> None:
        """Set (size > 0) or delete (size = 0) one price level."""
        side = self.bids if change["side"] == "BUY" else self.asks
        size = float(change["size"])
        if size > 0:
            side[float(change["price"])] = size
        else:
            side.pop(float(change["price"]), None)

    def book(self, ts_ms: int) -> OrderBook:
        """Freeze the current state into an OrderBook."""
        return OrderBook(
            "polymarket", self.token_id, ts_ms,
            tuple(BookLevel(p, s) for p, s in sorted(self.bids.items(), reverse=True)),
            tuple(BookLevel(p, s) for p, s in sorted(self.asks.items())),
        )


def handle_message(local: LocalBook, msg: Mapping[str, Any]) -> Event | None:
    """Apply one decoded CLOB message to ``local``; return the resulting event, if any."""
    kind = msg.get("event_type")
    if kind == "book" and msg["asset_id"] == local.token_id:
        local.snapshot(msg)
        return local.book(int(msg["timestamp"]))
    if kind == "price_change":
        mine = [c for c in msg["price_changes"] if c["asset_id"] == local.token_id]
        for change in mine:
            local.apply_change(change)
        if mine:
            local.check_best(mine[-1])
        return local.book(int(msg["timestamp"])) if mine else None
    if kind == "last_trade_price" and msg["asset_id"] == local.token_id:
        side: Side = "buy" if msg["side"] == "BUY" else "sell"
        return Trade("polymarket", local.token_id, int(msg["timestamp"]),
                     float(msg["price"]), float(msg["size"]), side)
    return None


async def _ping(ws: Any) -> None:
    while True:
        await asyncio.sleep(PING_INTERVAL_S)
        await ws.send("PING")


async def _session(spec: MarketSpec) -> AsyncIterator[Event]:
    local = LocalBook(spec.yes_token_id)
    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        await ws.send(json.dumps({"assets_ids": [spec.yes_token_id], "type": "market"}))
        pinger = asyncio.create_task(_ping(ws))
        try:
            async for raw in ws:
                if raw == "PONG":
                    continue
                decoded = json.loads(raw)
                for msg in decoded if isinstance(decoded, list) else [decoded]:
                    event = handle_message(local, msg)
                    if event is not None:
                        yield event
                    if local.desynced:
                        raise ConnectionError("order book desynchronised, resubscribing")
        finally:
            pinger.cancel()


def stream(spec: MarketSpec) -> AsyncIterator[Event]:
    """Reconnecting stream of YES-token OrderBook (per update) and Trade events."""
    return resilient(lambda: _session(spec), "polymarket")
