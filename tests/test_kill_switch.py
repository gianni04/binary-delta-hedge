"""Tests du kill-switch gamma."""

from __future__ import annotations

from risk.kill_switch import KillSwitch
from strategies.types import OrderIntent

EXPIRY_MS = 1_800_000_000_000
LEAD_MS = 7_200_000
DEADLINE_MS = EXPIRY_MS - LEAD_MS


def test_deadline_is_expiry_minus_lead() -> None:
    ks = KillSwitch(EXPIRY_MS)
    assert ks.deadline_ms == DEADLINE_MS


def test_triggered_one_ms_before_deadline_is_false() -> None:
    assert KillSwitch(EXPIRY_MS).triggered(DEADLINE_MS - 1) is False


def test_triggered_at_deadline_is_true() -> None:
    assert KillSwitch(EXPIRY_MS).triggered(DEADLINE_MS) is True


def test_triggered_one_ms_after_deadline_is_true() -> None:
    assert KillSwitch(EXPIRY_MS).triggered(DEADLINE_MS + 1) is True


def test_custom_lead_moves_deadline() -> None:
    ks = KillSwitch(EXPIRY_MS, lead_ms=60_000)
    assert ks.deadline_ms == EXPIRY_MS - 60_000
    assert ks.triggered(EXPIRY_MS - 60_000) is True
    assert ks.triggered(EXPIRY_MS - 60_001) is False


def test_flatten_long_hl_and_long_pm_order_and_sides() -> None:
    intents = KillSwitch(EXPIRY_MS).flatten(pm_shares=100.0, hl_position=0.5)
    assert intents == [
        OrderIntent("hyperliquid", "cancel_all", None, 0.0, None, "kill_cancel"),
        OrderIntent("hyperliquid", "market", "sell", 0.5, None, "kill_hl"),
        OrderIntent("polymarket", "market", "sell", 100.0, None, "kill_pm"),
    ]


def test_flatten_short_hl_buys_back_absolute_size() -> None:
    intents = KillSwitch(EXPIRY_MS).flatten(pm_shares=0.0, hl_position=-0.25)
    assert intents == [
        OrderIntent("hyperliquid", "cancel_all", None, 0.0, None, "kill_cancel"),
        OrderIntent("hyperliquid", "market", "buy", 0.25, None, "kill_hl"),
    ]


def test_flatten_flat_positions_only_cancels() -> None:
    intents = KillSwitch(EXPIRY_MS).flatten(pm_shares=0.0, hl_position=0.0)
    assert intents == [
        OrderIntent("hyperliquid", "cancel_all", None, 0.0, None, "kill_cancel"),
    ]


def test_flatten_no_pm_order_when_shares_not_positive() -> None:
    intents = KillSwitch(EXPIRY_MS).flatten(pm_shares=0.0, hl_position=1.0)
    assert all(i.venue != "polymarket" for i in intents)
    assert [i.tag for i in intents] == ["kill_cancel", "kill_hl"]
