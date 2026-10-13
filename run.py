"""Point d'entrée : `python run.py live ...` ou `python run.py replay data/raw_<run>.jsonl`."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import statistics
import tempfile
import time
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path

from api.models import Event, MarketSpec, OrderBook, PerpSpec
from risk.kill_switch import KillSwitch
from sim.engine import run as run_engine
from strategies.base import HedgeStrategy
from strategies.dynamic import DynamicHedger
from strategies.static import StaticHedger

DATA = Path("data")


def build_strategies(spec: MarketSpec, quantity: float, threshold: float | None = None) -> list[HedgeStrategy]:
    """Les deux stratégies comparées, chacune avec son propre KillSwitch."""
    return [
        StaticHedger("static", quantity, KillSwitch(spec.expiry_ms)),
        DynamicHedger("dynamic", quantity, KillSwitch(spec.expiry_ms), threshold),
    ]


async def simulate(
    events: AsyncIterator[Event],
    spec: MarketSpec,
    perp: PerpSpec,
    quantity: float,
    sigma_source: str,
    journal: Path,
    threshold: float | None = None,
) -> None:
    """Même code en live et en replay : seul le flux d'événements change."""
    await run_engine(events, build_strategies(spec, quantity, threshold), spec, perp, journal, sigma_source)


async def _first_mid(spec: MarketSpec) -> float | None:
    from api import polymarket

    stream = polymarket.stream(spec)
    try:
        async with asyncio.timeout(15):
            async for ev in stream:
                if isinstance(ev, OrderBook) and ev.mid is not None:
                    return ev.mid
    except TimeoutError:
        return None
    finally:
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()
    return None


async def pick_market(slug: str | None, min_hours: float) -> MarketSpec:
    """--slug, sinon le YES le plus proche de 0,5 avec au moins `min_hours` avant l'échéance."""
    from api import polymarket

    specs = await polymarket.find_btc_above_markets()
    if slug:
        for s in specs:
            if s.slug == slug:
                return s
        raise SystemExit(f"slug introuvable : {slug}")
    limit = time.time() * 1000 + min_hours * 3_600_000
    cands = [s for s in specs if s.expiry_ms >= limit][:40]
    mids = await asyncio.gather(*(_first_mid(s) for s in cands))
    scored = [(abs(m - 0.5), s) for m, s in zip(mids, cands, strict=True) if m is not None]
    if not scored:
        raise SystemExit("aucun marché éligible")
    return min(scored, key=lambda x: x[0])[1]


async def live(args: argparse.Namespace) -> None:
    """Flux live enregistré dans data/raw_<run>.jsonl, journal dans data/journal_<run>.jsonl."""
    from api import deribit, hyperliquid, polymarket, recorder

    spec = await pick_market(args.slug, args.min_hours)
    perp = await hyperliquid.perp_spec()
    run_id = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    DATA.mkdir(exist_ok=True)
    meta = {"spec": asdict(spec), "perp": asdict(perp), "quantity": args.quantity, "sigma_source": args.sigma}
    (DATA / f"meta_{run_id}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    merged = recorder.merge(hyperliquid.stream(), polymarket.stream(spec), deribit.stream_dvol())
    events = recorder.record(merged, DATA / f"raw_{run_id}.jsonl")
    journal = DATA / f"journal_{run_id}.jsonl"
    print(f"{spec.slug} K={spec.strike} run={run_id}")
    try:
        async with asyncio.timeout(args.hours * 3600):
            await simulate(events, spec, perp, args.quantity, args.sigma, journal)
    except TimeoutError:
        pass
    print(f"journal : {journal}")


async def replay(args: argparse.Namespace) -> None:
    """Rejoue un enregistrement brut ; le journal doit être identique à celui du live."""
    from api import recorder

    raw = Path(args.raw)
    run_id = raw.stem.removeprefix("raw_")
    meta = json.loads((raw.parent / f"meta_{run_id}.json").read_text(encoding="utf-8"))
    spec = MarketSpec(**meta["spec"])
    perp = PerpSpec(**meta["perp"])
    suffix = f"_{args.tag}" if args.tag else ""
    journal = raw.parent / f"journal_{run_id}_replay{suffix}.jsonl"
    sigma = args.sigma or meta["sigma_source"]
    await simulate(recorder.replay(raw), spec, perp, meta["quantity"], sigma, journal, args.threshold)
    print(f"journal : {journal}")


CSV_COLUMNS = ["threshold", "sigma_source", "n_rebal", "hl_notional", "fees_hl", "fees_pm", "funding",
               "pnl_total", "std_net_delta_btc", "max_abs_net_delta_btc", "hedge_lag_ms"]


def summarize(journal: Path, threshold: str, sigma: str, strategy: str = "dynamic") -> dict[str, object]:
    """Une ligne de balayage depuis les enregistrements d'une stratégie du journal.

    Les stats de delta net portent sur les marks entre le premier fill HL et le premier fill kill
    (exclu) ; `hedge_lag_ms` = premier fill HL - fill entry_pm.
    """
    recs = [json.loads(x) for x in journal.read_text(encoding="utf-8").splitlines()]
    mine = [r for r in recs if r["strategy"] == strategy]
    fills = [r for r in mine if r["type"] == "fill"]
    marks = [r for r in mine if r["type"] == "mark"]
    hl = [f for f in fills if f["venue"] == "hyperliquid"]
    entry = [f for f in fills if f["tag"] == "entry_pm"]
    kills = [f for f in fills if str(f["tag"]).startswith("kill")]
    t_hl = int(hl[0]["ts_ms"]) if hl else None
    t_kill = int(kills[0]["ts_ms"]) if kills else None
    window = [
        float(m["net_delta_btc"]) for m in marks
        if t_hl is not None and int(m["ts_ms"]) >= t_hl and (t_kill is None or int(m["ts_ms"]) < t_kill)
    ]
    last = marks[-1]
    return {
        "threshold": threshold, "sigma_source": sigma,
        "n_rebal": sum(1 for f in fills if f["tag"] == "dyn_rebal"),
        "hl_notional": sum(float(f["size"]) * float(f["price"]) for f in hl),
        "fees_hl": last["fees_hl"], "fees_pm": last["fees_pm"], "funding": last["funding"],
        "pnl_total": last["pnl_total"],
        "std_net_delta_btc": statistics.pstdev(window) if len(window) > 1 else "",
        "max_abs_net_delta_btc": max(abs(n) for n in window) if window else "",
        "hedge_lag_ms": t_hl - int(entry[0]["ts_ms"]) if t_hl is not None and entry else "",
    }


async def sweep(args: argparse.Namespace) -> None:
    """Rejoue la dynamique pour chaque seuil (σ implicite) puis chaque source de σ au seuil par défaut."""
    from api import recorder

    raw = Path(args.raw)
    run_id = raw.stem.removeprefix("raw_")
    meta = json.loads((raw.parent / f"meta_{run_id}.json").read_text(encoding="utf-8"))
    spec = MarketSpec(**meta["spec"])
    perp = PerpSpec(**meta["perp"])
    cases: list[tuple[float | None, str]] = [(float(x), "implied") for x in args.thresholds.split(",")]
    cases += [(None, src) for src in ("implied", "dvol", "ewma")]
    rows: list[dict[str, object]] = []
    static_row: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as tmp:
        for thr, src in cases:
            journal = Path(tmp) / "j.jsonl"
            await simulate(recorder.replay(raw), spec, perp, meta["quantity"], src, journal, thr)
            rows.append(summarize(journal, "default" if thr is None else repr(thr), src))
            if not static_row:
                static_row.append(summarize(journal, "static", src, "static"))
    rows.append(static_row[0])
    out = raw.parent / f"sweep_{run_id}.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"sweep : {out}")


def main() -> None:
    """CLI."""
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)
    lv = sub.add_parser("live")
    lv.add_argument("--hours", type=float, required=True)
    lv.add_argument("--slug")
    lv.add_argument("--quantity", type=float, default=1000.0)
    lv.add_argument("--min-hours", type=float, default=3.0)
    lv.add_argument("--sigma", choices=["implied", "dvol", "ewma"], default="implied")
    rp = sub.add_parser("replay")
    rp.add_argument("raw")
    rp.add_argument("--threshold", type=float)
    rp.add_argument("--sigma", choices=["implied", "dvol", "ewma"])
    rp.add_argument("--tag", default="")
    sw = sub.add_parser("sweep")
    sw.add_argument("raw")
    sw.add_argument("--thresholds", required=True)
    args = ap.parse_args()
    asyncio.run({"live": live, "replay": replay, "sweep": sweep}[args.mode](args))


if __name__ == "__main__":
    main()
