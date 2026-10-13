"""Gamma kill-switch : clôture forcée avant l'échéance.

Pourquoi : pour une binaire cash-or-nothing, Γ ∝ 1/(S² σ² T). Quand T → 0,
Γ explose, donc le delta varie de plus en plus vite avec le prix. Un hedge
dynamique devient alors instable : chaque tick exige un ordre, les frais et
le spread dévorent le gain, et une petite variation de S renverse la position.
On sort donc à T − lead (2 h par défaut), avant que la zone de Γ explosif
ne soit atteinte, et on ne tient jamais la position jusqu'à la résolution.
"""

from __future__ import annotations

from typing import Literal

from strategies.types import OrderIntent

DEFAULT_LEAD_MS = 7_200_000


class KillSwitch:
    """Déclenche la clôture de toutes les positions à `expiry_ms - lead_ms`."""

    def __init__(self, expiry_ms: int, lead_ms: int = DEFAULT_LEAD_MS) -> None:
        """Mémorise l'échéance du marché et l'avance de déclenchement en ms."""
        self._expiry_ms = expiry_ms
        self._lead_ms = lead_ms

    @property
    def deadline_ms(self) -> int:
        """Instant (ms epoch) à partir duquel le kill-switch est actif."""
        return self._expiry_ms - self._lead_ms

    def triggered(self, now_ms: int) -> bool:
        """Vrai ssi `now_ms >= deadline_ms` (borne incluse)."""
        return now_ms >= self.deadline_ms

    def flatten(self, pm_shares: float, hl_position: float) -> list[OrderIntent]:
        """Ordres de clôture, dans l'ordre : annulation HL, puis HL, puis PM.

        - `cancel_all` HL est toujours émis en premier.
        - Position HL non nulle : market de |hl_position| du côté opposé (`kill_hl`).
        - Parts PM > 0 : vente market de `pm_shares` (`kill_pm`).
        """
        intents: list[OrderIntent] = [
            OrderIntent(
                venue="hyperliquid",
                kind="cancel_all",
                side=None,
                size=0.0,
                limit_price=None,
                tag="kill_cancel",
            )
        ]
        if hl_position != 0:
            hl_side: Literal["buy", "sell"] = "sell" if hl_position > 0 else "buy"
            intents.append(
                OrderIntent(
                    venue="hyperliquid",
                    kind="market",
                    side=hl_side,
                    size=abs(hl_position),
                    limit_price=None,
                    tag="kill_hl",
                )
            )
        if pm_shares > 0:
            intents.append(
                OrderIntent(
                    venue="polymarket",
                    kind="market",
                    side="sell",
                    size=pm_shares,
                    limit_price=None,
                    tag="kill_pm",
                )
            )
        return intents
