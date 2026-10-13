"""Exécution simulée : balayage du carnet (taker) et remplissage maker HL.

Limite assumée : aucun impact persistant sur le carnet. Chaque ordre balaie le
carnet tel que publié ; le carnet suivant efface notre consommation.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.models import OrderBook, Side, Trade


def sweep_levels(book: OrderBook, side: Side, size: float) -> list[tuple[float, float]]:
    """(prix, taille) consommés niveau par niveau : un achat mange les asks, une vente les bids."""
    levels = book.asks if side == "buy" else book.bids
    out: list[tuple[float, float]] = []
    remaining = size
    for lv in levels:
        if remaining <= 0:
            break
        take = min(remaining, lv.size)
        if take > 0:
            out.append((lv.price, take))
            remaining -= take
    return out


def sweep(book: OrderBook, side: Side, size: float) -> tuple[float, float]:
    """(prix moyen, taille remplie) du balayage ; prix moyen 0.0 si rien n'est rempli."""
    levels = sweep_levels(book, side, size)
    filled = sum(q for _, q in levels)
    if filled <= 0:
        return 0.0, 0.0
    return sum(p * q for p, q in levels) / filled, filled


@dataclass(slots=True)
class RestingOrder:
    """Ordre limite HL reposant dans le simulateur."""

    side: Side
    price: float
    remaining: float
    tag: str


def maker_fill(order: RestingOrder, trade: Trade) -> float:
    """Taille remplie par `trade` : seulement si l'agresseur passe STRICTEMENT au travers du prix.

    Vente limite à L : trade d'achat avec prix > L. Achat limite à L : trade de vente avec prix < L.
    Remplissage = min(reste, taille du trade) ; le reste de l'ordre repose encore.
    """
    if order.side == "sell":
        crossed = trade.side == "buy" and trade.price > order.price
    else:
        crossed = trade.side == "sell" and trade.price < order.price
    if not crossed:
        return 0.0
    return min(order.remaining, trade.size)
