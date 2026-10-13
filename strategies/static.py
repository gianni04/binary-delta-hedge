"""Couverture statique : un seul ordre limite maker au delta initial."""

from __future__ import annotations

import logging

from strategies.base import HedgeStrategy, round_lot
from strategies.types import OrderIntent, Snapshot

log = logging.getLogger(__name__)


class StaticHedger(HedgeStrategy):
    """Place un unique ordre limite HL côté passif dimensionné à h0, puis ne fait plus rien."""

    _placed = False

    def _decide(self, snap: Snapshot) -> list[OrderIntent]:
        if self._placed or self.pm_shares <= 0:
            return []
        h0 = self.target_hedge(snap)
        bid, ask = snap.hl_book.best_bid, snap.hl_book.best_ask
        mid = snap.hl_book.mid
        if h0 is None or mid is None or bid is None or ask is None:
            return []
        self._placed = True
        size = round_lot(abs(h0), snap.perp.sz_decimals)
        if size <= 0 or size * mid < snap.perp.min_notional:
            log.info("%s: hedge %.6f BTC sous le notionnel minimum, aucun ordre", self.name, h0)
            return []
        sell = h0 < 0
        return [
            OrderIntent(
                venue="hyperliquid",
                kind="limit",
                side="sell" if sell else "buy",
                size=size,
                limit_price=ask if sell else bid,
                tag="static_hedge",
            )
        ]
