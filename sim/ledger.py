"""Comptabilité par stratégie et écriture du journal JSONL."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TextIO

from risk.fees import hl_fee, pm_fee
from strategies.types import Fill

HOUR_MS = 3_600_000
MARK_EVERY_MS = 1000


def fill_fee(venue: str, size: float, price: float, maker: bool) -> float:
    """Frais d'un fill unitaire (un niveau de carnet) via risk.fees."""
    if venue == "polymarket":
        return pm_fee(size, price, maker)
    return hl_fee(size * price, maker)


class Ledger:
    """Cash, positions, frais, funding et marks d'une stratégie."""

    def __init__(self, strategy: str, out: TextIO) -> None:
        self.strategy = strategy
        self._out = out
        self.cash_pm = 0.0
        self.cash_hl = 0.0
        self.pm_shares = 0.0
        self.hl_position = 0.0
        self.fees_pm = 0.0
        self.fees_hl = 0.0
        self.funding = 0.0
        self.funding_rate = 0.0
        self.final_marked = False
        self.last_mark_ts: int | None = None
        self._hour: int | None = None

    def _write(self, rec: dict[str, object]) -> None:
        self._out.write(json.dumps(rec, separators=(",", ":")) + "\n")

    def on_fill(self, fill: Fill) -> None:
        """Enregistre le fill (cash hors frais, frais cumulés) et l'écrit au journal."""
        signed = fill.size if fill.side == "buy" else -fill.size
        cash = -signed * fill.price
        if fill.venue == "polymarket":
            self.pm_shares += signed
            self.cash_pm += cash
            self.fees_pm += fill.fee
        else:
            self.hl_position += signed
            self.cash_hl += cash
            self.fees_hl += fill.fee
        self._write(
            {
                "type": "fill", "strategy": self.strategy, "ts_ms": fill.ts_ms, "venue": fill.venue,
                "side": fill.side, "size": fill.size, "price": fill.price, "fee": fill.fee,
                "maker": fill.maker, "tag": fill.tag,
            }
        )

    def advance(self, ts_ms: int, s: float) -> None:
        """À chaque heure pleine UTC franchie : funding += position * S * dernier taux horaire."""
        hour = ts_ms // HOUR_MS
        if self._hour is not None and hour > self._hour:
            self.funding += (hour - self._hour) * self.hl_position * s * self.funding_rate
        if self._hour is None or hour > self._hour:
            self._hour = hour

    def pnl_pm(self, pm_mid: float) -> float:
        """MtM brut de la jambe Polymarket, hors frais."""
        return self.cash_pm + self.pm_shares * pm_mid

    def pnl_hl(self, s: float) -> float:
        """MtM brut de la jambe Hyperliquid, hors frais."""
        return self.cash_hl + self.hl_position * s

    def mark(
        self,
        ts_ms: int,
        s: float,
        pm_mid: float,
        sigma: float | None,
        sigmas: Mapping[str, float | None],
        sigma_used_source: str | None,
        delta_pm_btc: float,
        force: bool = False,
        extra: Mapping[str, object] | None = None,
    ) -> bool:
        """Écrit une ligne mark (au plus 1/s sauf `force`). Retourne True si écrite."""
        if not force and self.last_mark_ts is not None and ts_ms - self.last_mark_ts < MARK_EVERY_MS:
            return False
        self.last_mark_ts = ts_ms
        pnl_pm, pnl_hl = self.pnl_pm(pm_mid), self.pnl_hl(s)
        rec: dict[str, object] = (
            {
                "type": "mark", "strategy": self.strategy, "ts_ms": ts_ms, "S": s, "pm_mid": pm_mid,
                "sigma": sigma, "sigma_implied": sigmas.get("implied"), "sigma_dvol": sigmas.get("dvol"),
                "sigma_ewma": sigmas.get("ewma"), "sigma_used_source": sigma_used_source,
                "delta_pm_btc": delta_pm_btc, "hl_position": self.hl_position,
                "net_delta_btc": delta_pm_btc + self.hl_position,
                "pnl_total": pnl_pm + pnl_hl - self.fees_pm - self.fees_hl - self.funding,
                "pnl_pm": pnl_pm, "pnl_hl": pnl_hl, "fees_pm": self.fees_pm,
                "fees_hl": self.fees_hl, "funding": self.funding,
            }
        )
        if extra:
            rec.update(extra)
        self._write(rec)
        return True
