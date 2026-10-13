"""Tests for strategies (static / dynamic / kill-switch template)."""

from __future__ import annotations

from api.models import BookLevel, MarketSpec, OrderBook, PerpSpec
from core.math_engine import binary_call_delta, year_fraction
from risk.kill_switch import KillSwitch
from strategies.base import HedgeStrategy
from strategies.dynamic import DynamicHedger
from strategies.static import StaticHedger
from strategies.types import Fill, OrderIntent, Snapshot

HOUR = 3_600_000
EXPIRY = 1_000 * HOUR
K = 100_000.0
PERP = PerpSpec(coin="BTC", sz_decimals=5, max_leverage=40)
SPEC = MarketSpec("s", "q", K, EXPIRY, "tok", 0.01, 5.0, 0.0, 0.0)
Q = 1000.0


def _book(venue: str, mid: float, half: float, ts: int) -> OrderBook:
    assert venue in ("hyperliquid", "polymarket")
    return OrderBook(
        venue=venue,  # type: ignore[arg-type]
        instrument="x",
        ts_ms=ts,
        bids=(BookLevel(mid - half, 10.0),),
        asks=(BookLevel(mid + half, 10.0),),
    )


def snap(ts: int, s: float = K, sigma: float | None = 0.5) -> Snapshot:
    return Snapshot(
        ts_ms=ts,
        hl_book=_book("hyperliquid", s, 0.5, ts),
        pm_book=_book("polymarket", 0.5, 0.01, ts),
        spec=SPEC,
        perp=PERP,
        sigma=sigma,
        sigmas={"implied": sigma},
    )


def fill(venue: str, side: str, size: float) -> Fill:
    return Fill(0, venue, side, size, 1.0, 0.0, False, "t")  # type: ignore[arg-type]


def ks() -> KillSwitch:
    return KillSwitch(EXPIRY)


def entered(strat: HedgeStrategy, ts: int) -> None:
    out = strat.step(snap(ts))
    assert len(out) == 1
    strat.on_fill(fill("polymarket", "buy", Q))


def expected_h(ts: int, s: float = K, sigma: float = 0.5) -> float:
    return -Q * binary_call_delta(s, K, sigma, year_fraction(ts, EXPIRY))


T0 = EXPIRY - 10 * HOUR


def test_entry_once() -> None:
    st = StaticHedger("static", Q, ks())
    out = st.step(snap(T0))
    assert out == [OrderIntent("polymarket", "market", "buy", Q, None, "entry_pm")]
    assert st.entered
    assert st.step(snap(T0 + 1000)) == []  # not filled yet, pm_shares == 0


def test_on_fill_signs() -> None:
    st = DynamicHedger("d", Q, ks())
    st.on_fill(fill("polymarket", "buy", 5))
    st.on_fill(fill("hyperliquid", "sell", 2))
    st.on_fill(fill("hyperliquid", "buy", 0.5))
    assert st.pm_shares == 5 and st.hl_position == -1.5


def test_static_single_sized_sell() -> None:
    st = StaticHedger("static", Q, ks())
    entered(st, T0)
    out = st.step(snap(T0 + 1000))
    assert len(out) == 1
    o = out[0]
    assert (o.venue, o.kind, o.side, o.tag) == ("hyperliquid", "limit", "sell", "static_hedge")
    assert o.size == round(abs(expected_h(T0 + 1000)), 5)
    assert o.limit_price == K + 0.5  # best ask, passive side
    assert st.step(snap(T0 + 2000)) == []
    assert st.step(snap(T0 + 3000, s=K + 500)) == []


def test_static_waits_for_sigma() -> None:
    st = StaticHedger("static", Q, ks())
    entered(st, T0)
    assert st.step(snap(T0 + 1000, sigma=None)) == []
    assert len(st.step(snap(T0 + 2000))) == 1


def test_static_below_min_notional() -> None:
    st = StaticHedger("static", 0.3, ks())
    st.step(snap(T0))
    st.on_fill(fill("polymarket", "buy", 0.3))
    assert st.step(snap(T0 + 1000)) == []
    assert st.step(snap(T0 + 2000)) == []


def test_dynamic_initial_rebalance_then_hold() -> None:
    dy = DynamicHedger("dynamic", Q, ks())
    entered(dy, T0)
    out = dy.step(snap(T0 + 1000))
    assert len(out) == 1
    o = out[0]
    assert (o.venue, o.kind, o.side, o.tag, o.limit_price) == ("hyperliquid", "market", "sell", "dyn_rebal", None)
    assert o.size == round(abs(expected_h(T0 + 1000)), 5)
    dy.on_fill(fill("hyperliquid", "sell", o.size))
    assert dy.step(snap(T0 + 1000)) == []


def test_dynamic_threshold() -> None:
    dy = DynamicHedger("dynamic", Q, ks(), threshold_btc=0.05)
    entered(dy, T0)
    dy.on_fill(fill("hyperliquid", "sell", -expected_h(T0 + 1000)))
    # small move: |diff| under 0.05 -> no order
    s_small = snap(T0 + 1000, s=K + 10)
    assert abs(dy.target_hedge(s_small) - dy.hl_position) < 0.05  # type: ignore[operator]
    assert dy.step(s_small) == []
    # big move: |diff| over 0.05 -> buy to reduce the short
    big = snap(T0 + 1000, s=K - 3000)
    diff = dy.target_hedge(big) - dy.hl_position  # type: ignore[operator]
    assert abs(diff) > 0.05
    out = dy.step(big)
    assert len(out) == 1 and out[0].side == ("buy" if diff > 0 else "sell")
    assert out[0].size == round(abs(diff), 5)


def test_dynamic_default_threshold_and_no_sigma() -> None:
    dy = DynamicHedger("dynamic", Q, ks())
    entered(dy, T0)
    assert dy.step(snap(T0 + 1000, sigma=None)) == []
    dy.on_fill(fill("hyperliquid", "sell", -expected_h(T0 + 1000)))
    target = dy.target_hedge(snap(T0 + 1000))
    assert target is not None
    dy.hl_position = target + 0.00005  # under 10/S = 1e-4
    assert dy.step(snap(T0 + 1000)) == []
    dy.hl_position = target + 0.0002
    assert len(dy.step(snap(T0 + 1000))) == 1


def test_kill_switch_preempts_both() -> None:
    for strat in (StaticHedger("s", Q, ks()), DynamicHedger("d", Q, ks())):
        entered(strat, T0)
        strat.on_fill(fill("hyperliquid", "sell", 0.2))
        just_before = EXPIRY - 2 * HOUR - 1
        assert all(o.tag != "kill_pm" for o in strat.step(snap(just_before)))
        assert not strat.done
        out = strat.step(snap(EXPIRY - 2 * HOUR))
        assert not strat.done  # done only once really flat
        assert [o.tag for o in out] == ["kill_cancel", "kill_hl", "kill_pm"]
        assert out[1].side == "buy" and out[1].size == 0.2
        assert out[2].size == Q
        strat.on_fill(fill("hyperliquid", "buy", 0.2))
        assert not strat.done
        strat.on_fill(fill("polymarket", "sell", Q))
        assert strat.done
        assert strat.step(snap(EXPIRY - 2 * HOUR + 1000)) == []


def test_kill_switch_reissues_on_residual() -> None:
    st = DynamicHedger("d", Q, ks())
    entered(st, T0)
    st.step(snap(EXPIRY - 2 * HOUR))
    st.on_fill(fill("polymarket", "sell", Q / 2))
    out = st.step(snap(EXPIRY - 2 * HOUR + 1000))
    assert not st.done
    assert [(o.tag, o.size) for o in out] == [("kill_cancel", 0.0), ("kill_pm", Q / 2)]
    st.on_fill(fill("polymarket", "sell", Q / 2))
    assert st.done


def test_kill_switch_before_entry() -> None:
    st = DynamicHedger("d", Q, ks())
    out = st.step(snap(EXPIRY - HOUR))
    assert [o.tag for o in out] == ["kill_cancel"]
    assert st.done and not st.entered
