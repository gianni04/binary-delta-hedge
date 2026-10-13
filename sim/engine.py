"""Boucle de simulation : même flux, une stratégie et un Ledger chacune."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from api.models import Event, FundingQuote, MarketSpec, OrderBook, PerpSpec, Trade, VolQuote
from core.math_engine import EwmaVol, binary_call_delta, implied_vol, year_fraction
from sim.fills import RestingOrder, maker_fill, sweep_levels
from sim.ledger import Ledger, fill_fee
from strategies.base import HedgeStrategy
from strategies.types import Fill, OrderIntent, Snapshot

HOLD_MS = 300_000  # hystérésis : dernière σ implicite valide gardée 300 s
GRID_MS = 60_000  # EwmaVol alimentée sur une grille fixe de 60 s (bruit de microstructure)
EWMA_HALF_LIFE_S = 1800.0
SOURCES = ("implied", "dvol", "ewma")


@dataclass(slots=True)
class _Last:
    ts_ms: int
    s: float
    pm_mid: float
    sigma: float | None
    sigmas: dict[str, float | None]
    used: str | None
    delta_share: float


async def run(
    events: AsyncIterator[Event],
    strategies: Sequence[HedgeStrategy],
    spec: MarketSpec,
    perp: PerpSpec,
    journal_path: str | Path,
    sigma_source: str = "implied",
) -> dict[str, Ledger]:
    """Rejoue `events` ; s'arrête quand toutes les stratégies sont done ou que le flux finit.

    σ choisie : source demandée, repli implied -> dvol -> ewma. L'implicite est tenue 300 s
    après sa dernière valeur valide (`sigma_used_source` = "implied_held" alors).
    """
    path = Path(journal_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    hl_book: OrderBook | None = None
    pm_book: OrderBook | None = None
    dvol: float | None = None
    ewma = EwmaVol(EWMA_HALF_LIFE_S)
    grid_minute: int | None = None
    prev_mid: float | None = None
    held: tuple[float, int] | None = None
    last: _Last | None = None
    delta_share = 0.0
    resting: dict[str, list[RestingOrder]] = {s.name: [] for s in strategies}
    swept: dict[tuple[str, str], OrderBook] = {}  # dernier carnet balayé par (stratégie, venue)

    with path.open("w", encoding="utf-8") as out:
        ledgers = {s.name: Ledger(s.name, out) for s in strategies}

        def execute(strat: HedgeStrategy, snap: Snapshot, intent: OrderIntent) -> None:
            ledger = ledgers[strat.name]
            if intent.kind == "cancel_all":
                if intent.venue == "hyperliquid":
                    resting[strat.name].clear()
                return
            if intent.side is None:
                raise ValueError(f"intent sans side : {intent}")
            if intent.kind == "limit":
                if intent.venue != "hyperliquid" or intent.limit_price is None:
                    raise ValueError(f"limit non supporté : {intent}")
                resting[strat.name].append(RestingOrder(intent.side, intent.limit_price, intent.size, intent.tag))
                return
            book = snap.hl_book if intent.venue == "hyperliquid" else snap.pm_book
            if swept.get((strat.name, intent.venue)) is book:
                return  # carnet déjà consommé : la stratégie réémettra au prochain carnet
            swept[(strat.name, intent.venue)] = book
            # un fill par niveau consommé : pm_fee est non linéaire en p
            for px, sz in sweep_levels(book, intent.side, intent.size):
                f = Fill(snap.ts_ms, intent.venue, intent.side, sz, px,
                         fill_fee(intent.venue, sz, px, False), False, intent.tag)
                strat.on_fill(f)
                ledger.on_fill(f)

        def do_mark(strat: HedgeStrategy, lg: _Last, force: bool) -> None:
            ledger = ledgers[strat.name]
            extra = None
            if strat.done and strat.flattening:
                # temps de clôture : dernier fill kill (= ce ts) moins l'échéance du kill-switch
                extra = {"kill_close_ms": lg.ts_ms - strat.kill_switch.deadline_ms}
            ledger.mark(lg.ts_ms, lg.s, lg.pm_mid, lg.sigma, lg.sigmas, lg.used,
                        ledger.pm_shares * lg.delta_share, force=force, extra=extra)

        try:
            async for ev in events:
                if isinstance(ev, OrderBook):
                    if ev.venue == "hyperliquid":
                        hl_book = ev
                        mid = ev.mid
                        if mid is not None:
                            minute = ev.ts_ms // GRID_MS
                            if grid_minute is None:
                                ewma.update(minute * GRID_MS, mid)
                            elif minute > grid_minute and prev_mid is not None:
                                ewma.update(minute * GRID_MS, prev_mid)
                            if grid_minute is None or minute > grid_minute:
                                grid_minute = minute
                            prev_mid = mid
                    else:
                        pm_book = ev
                elif isinstance(ev, VolQuote):
                    dvol = ev.value
                elif isinstance(ev, FundingQuote):
                    for lg_ in ledgers.values():
                        lg_.funding_rate = ev.rate_hourly
                elif isinstance(ev, Trade) and ev.venue == "hyperliquid":
                    for strat in strategies:
                        for o in list(resting[strat.name]):
                            q = maker_fill(o, ev)
                            if q <= 0:
                                continue
                            o.remaining -= q
                            if o.remaining <= 1e-12:
                                resting[strat.name].remove(o)
                            f = Fill(ev.ts_ms, "hyperliquid", o.side, q, o.price,
                                     fill_fee("hyperliquid", q, o.price, True), True, o.tag)
                            strat.on_fill(f)
                            ledgers[strat.name].on_fill(f)
                if hl_book is None or pm_book is None:
                    continue
                s, pm_mid = hl_book.mid, pm_book.mid
                if s is None or pm_mid is None:
                    continue
                ts = ev.ts_ms
                t = year_fraction(ts, spec.expiry_ms)
                imp = implied_vol(pm_mid, s, spec.strike, t)
                if imp is not None:
                    held = (imp, ts)
                held_val = held[0] if held is not None and ts - held[1] <= HOLD_MS else None
                eff: dict[str, float | None] = {"implied": held_val, "dvol": dvol, "ewma": ewma.value}
                sigma: float | None = None
                used: str | None = None
                for src in [sigma_source] + [x for x in SOURCES if x != sigma_source]:
                    v = eff[src]
                    if v is not None and v > 0:
                        sigma = v
                        used = "implied_held" if src == "implied" and imp is None else src
                        break
                if sigma is not None and t > 0:
                    delta_share = binary_call_delta(s, spec.strike, sigma, t)
                snap_sigmas: dict[str, float | None] = {"implied": imp, "dvol": dvol, "ewma": ewma.value}
                for strat in strategies:
                    ledgers[strat.name].advance(ts, s)
                    if strat.done:
                        continue
                    snap = Snapshot(ts, hl_book, pm_book, spec, perp, sigma, snap_sigmas)
                    for intent in strat.step(snap):
                        execute(strat, snap, intent)
                    lg = _Last(ts, s, pm_mid, sigma, snap_sigmas, used, delta_share)
                    if strat.done:
                        resting[strat.name].clear()
                        do_mark(strat, lg, True)
                        ledgers[strat.name].final_marked = True
                    else:
                        do_mark(strat, lg, False)
                last = _Last(ts, s, pm_mid, sigma, snap_sigmas, used, delta_share)
                if all(x.done for x in strategies):
                    break
        finally:
            aclose = getattr(events, "aclose", None)
            if aclose is not None:
                await aclose()
            if last is not None:
                for strat in strategies:
                    if not ledgers[strat.name].final_marked:
                        do_mark(strat, last, True)
    return ledgers
