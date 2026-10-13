"""Frais officiels Hyperliquid et Polymarket (paper trading).

Sources (relevées le 2026-10-12, cf. docs/microstructure_review.md) :
- Hyperliquid, palier 0 : https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees.md
  taker 0,045 % (4,5 bp), maker 0,015 % (1,5 bp).
- Polymarket, marchés crypto : https://docs.polymarket.com/trading/fees.md
  fee = C × feeRate × p × (1 − p), C = parts, p = prix ; feeRate taker = 0,07,
  feeRate maker = 0 ; arrondi à 5 décimales. Rebate maker ignoré.

Les champs `taker_fee_bps` / `maker_fee_bps` de MarketSpec ne servent pas de taux
pour Polymarket.
"""

from __future__ import annotations

HL_MAKER_BPS = 1.5
HL_TAKER_BPS = 4.5
PM_CRYPTO_TAKER_FEE_RATE = 0.07


def hl_fee(notional: float, maker: bool) -> float:
    """Frais Hyperliquid en dollars : |notionnel| × bps / 1e4."""
    bps = HL_MAKER_BPS if maker else HL_TAKER_BPS
    return abs(notional) * bps / 1e4


def pm_fee(shares: float, price: float, maker: bool) -> float:
    """Frais Polymarket crypto en pUSD.

    Taker : round(|shares| × 0,07 × price × (1 − price), 5). Maker : 0.
    Lève ValueError si price n'est pas dans [0, 1].
    """
    if not 0.0 <= price <= 1.0:
        raise ValueError(f"price hors [0, 1] : {price}")
    if maker:
        return 0.0
    return round(abs(shares) * PM_CRYPTO_TAKER_FEE_RATE * price * (1.0 - price), 5)
