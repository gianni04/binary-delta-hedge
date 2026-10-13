"""Tests des frais Hyperliquid et Polymarket."""

from __future__ import annotations

import pytest

from risk.fees import HL_MAKER_BPS, HL_TAKER_BPS, hl_fee, pm_fee


def test_hl_constants_match_official_tier0() -> None:
    assert HL_MAKER_BPS == 1.5
    assert HL_TAKER_BPS == 4.5


def test_hl_taker_fee_on_known_notional() -> None:
    # 10 000 $ × 4,5 bp = 4,50 $
    assert hl_fee(10_000.0, maker=False) == pytest.approx(4.5)


def test_hl_maker_fee_on_known_notional() -> None:
    # 10 000 $ × 1,5 bp = 1,50 $
    assert hl_fee(10_000.0, maker=True) == pytest.approx(1.5)


def test_hl_fee_uses_absolute_notional() -> None:
    assert hl_fee(-10_000.0, maker=False) == pytest.approx(4.5)


def test_pm_official_example_100_shares_at_50_cents() -> None:
    # https://docs.polymarket.com/trading/fees.md : 100 × 0,07 × 0,5 × 0,5 = 1,75
    assert pm_fee(100.0, 0.50, maker=False) == 1.75


def test_pm_fee_symmetric_around_half() -> None:
    assert pm_fee(100.0, 0.30, maker=False) == pm_fee(100.0, 0.70, maker=False)


def test_pm_fee_zero_at_extremes() -> None:
    assert pm_fee(100.0, 0.0, maker=False) == 0.0
    assert pm_fee(100.0, 1.0, maker=False) == 0.0


def test_pm_maker_is_zero() -> None:
    assert pm_fee(100.0, 0.50, maker=True) == 0.0


def test_pm_fee_rounded_to_five_decimals() -> None:
    value = pm_fee(1.0, 0.123, maker=False)
    assert value == round(value, 5)


def test_pm_price_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        pm_fee(10.0, 1.01, maker=False)
    with pytest.raises(ValueError):
        pm_fee(10.0, -0.01, maker=False)
