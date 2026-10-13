"""Deribit client: BTC DVOL implied-volatility index stream."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any

import websockets

from api.models import VolQuote
from api.recorder import resilient

log = logging.getLogger(__name__)

WS_URL = "wss://www.deribit.com/ws/api/v2"
CHANNEL = "deribit_volatility_index.btc_usd"
HEARTBEAT_S = 30


def parse_dvol(params: Mapping[str, Any]) -> VolQuote:
    """Convert a subscription ``params`` object; Deribit quotes DVOL in percent."""
    data = params["data"]
    return VolQuote("dvol", int(data["timestamp"]), float(data["volatility"]) / 100.0)


async def _session() -> AsyncIterator[VolQuote]:
    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "public/set_heartbeat",
                                  "params": {"interval": HEARTBEAT_S}}))
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "public/subscribe",
                                  "params": {"channels": [CHANNEL]}}))
        async for raw in ws:
            msg = json.loads(raw)
            method = msg.get("method")
            if method == "heartbeat" and msg["params"].get("type") == "test_request":
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "public/test"}))
            elif method == "subscription" and msg["params"].get("channel") == CHANNEL:
                yield parse_dvol(msg["params"])


def stream_dvol() -> AsyncIterator[VolQuote]:
    """Reconnecting stream of DVOL readings as decimal annualised volatility."""
    return resilient(_session, "deribit")
