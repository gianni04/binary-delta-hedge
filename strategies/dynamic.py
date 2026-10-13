"""Couverture dynamique : rebalancement market dès que l'écart au delta cible dépasse un seuil."""

from __future__ import annotations

from risk.kill_switch import KillSwitch
from strategies.base import HedgeStrategy, round_lot
from strategies.types import OrderIntent, Snapshot


class DynamicHedger(HedgeStrategy):
    """Ramène la position HL vers -Q*delta quand |écart| dépasse le seuil (BTC)."""

    def __init__(
        self,
        name: str,
        quantity: float,
        kill_switch: KillSwitch,
        threshold_btc: float | None = None,
    ) -> None:
        """`threshold_btc` None : max(lot, min_notional / S)."""
        super().__init__(name, quantity, kill_switch)
        self.threshold_btc = threshold_btc

    def _decide(self, snap: Snapshot) -> list[OrderIntent]:
        target = self.target_hedge(snap)
        mid = snap.hl_book.mid
        if target is None or mid is None:
            return []
        diff = target - self.hl_position
        threshold = self.threshold_btc
        if threshold is None:
            threshold = max(10.0 ** -snap.perp.sz_decimals, snap.perp.min_notional / mid)
        if abs(diff) <= threshold:
            return []
        size = round_lot(abs(diff), snap.perp.sz_decimals)
        if size <= 0:
            return []
        return [
            OrderIntent(
                venue="hyperliquid",
                kind="market",
                side="buy" if diff > 0 else "sell",
                size=size,
                limit_price=None,
                tag="dyn_rebal",
            )
        ]
