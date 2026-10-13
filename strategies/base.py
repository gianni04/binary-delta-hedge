"""Template commun des stratégies de couverture."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.math_engine import binary_call_delta, year_fraction
from risk.kill_switch import KillSwitch
from strategies.types import Fill, OrderIntent, Snapshot


def round_lot(size: float, sz_decimals: int) -> float:
    """Arrondit `size` au lot Hyperliquid (`sz_decimals` décimales)."""
    return round(size, sz_decimals)


class HedgeStrategy(ABC):
    """Achète Q parts YES puis délègue à `_decide`; le KillSwitch passe toujours en premier."""

    def __init__(self, name: str, quantity: float, kill_switch: KillSwitch) -> None:
        """`quantity` = Q parts YES à acheter à l'entrée."""
        self.name = name
        self.quantity = quantity
        self.kill_switch = kill_switch
        self.pm_shares = 0.0
        self.hl_position = 0.0
        self.done = False
        self.entered = False
        self.flattening = False
        self._lot = 1e-5

    def step(self, snap: Snapshot) -> list[OrderIntent]:
        """Ordres à émettre pour ce snapshot. Les sous-classes ne peuvent pas contourner le KillSwitch."""
        if self.done:
            return []
        self._lot = 10.0 ** -snap.perp.sz_decimals
        if self.flattening or self.kill_switch.triggered(snap.ts_ms):
            # T-2h: tout doit être clôturé ; on réémet sur le reliquat jusqu'à être plat
            self.flattening = True
            hl = 0.0 if abs(self.hl_position) < self._lot else self.hl_position
            intents = self.kill_switch.flatten(self.pm_shares, hl)
            if self.is_flat():
                self.done = True
            return intents
        if not self.entered:
            self.entered = True
            return [
                OrderIntent(
                    venue="polymarket",
                    kind="market",
                    side="buy",
                    size=self.quantity,
                    limit_price=None,
                    tag="entry_pm",
                )
            ]
        return self._decide(snap)

    @abstractmethod
    def _decide(self, snap: Snapshot) -> list[OrderIntent]:
        """Logique propre à la stratégie, appelée seulement après l'entrée et avant le kill-switch."""

    def is_flat(self) -> bool:
        """Plus de parts PM et position HL inférieure à un lot."""
        return self.pm_shares <= 1e-9 and abs(self.hl_position) < self._lot

    def on_fill(self, fill: Fill) -> None:
        """Met à jour les positions : achat +, vente -. En clôture, done dès que plat."""
        signed = fill.size if fill.side == "buy" else -fill.size
        if fill.venue == "polymarket":
            self.pm_shares += signed
        else:
            self.hl_position += signed
        if self.flattening and self.is_flat():
            self.done = True

    def target_hedge(self, snap: Snapshot) -> float | None:
        """h = -pm_shares * delta (BTC), None si sigma ou le mid HL manque."""
        s = snap.hl_book.mid
        if snap.sigma is None or s is None:
            return None
        t = year_fraction(snap.ts_ms, snap.spec.expiry_ms)
        return -self.pm_shares * binary_call_delta(s, snap.spec.strike, snap.sigma, t)
