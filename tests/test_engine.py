"""Engine tests on a synthetic stream: strategies, journal, replay determinism, plot, EWMA grid."""

from __future__ import annotations

import asyncio
import json
import math
import random
import subprocess
import sys
from collections import defaultdict
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

import run as runmod
from api import recorder
from api.models import BookLevel, Event, FundingQuote, MarketSpec, OrderBook, PerpSpec, Trade, VolQuote
from core.math_engine import SECONDS_PER_YEAR, EwmaVol, binary_call_price, year_fraction
from sim.engine import run as run_engine

ROOT = Path(__file__).resolve().parents[1]
HOUR = 3_600_000
EXPIRY = 10_000 * HOUR + 1_800_000
K = 100_000.0
SPEC = MarketSpec("syn", "q", K, EXPIRY, "tok", 0.01, 5.0, 0.0, 0.0)
PERP = PerpSpec("BTC", 5, 40)
Q = 1000.0


def _hl(ts: int, mid: float) -> OrderBook:
    return OrderBook("hyperliquid", "BTC", ts, (BookLevel(mid - 0.5, 5.0), BookLevel(mid - 1.5, 50.0)),
                     (BookLevel(mid + 0.5, 5.0), BookLevel(mid + 1.5, 50.0)))


def _pm(ts: int, p: float) -> OrderBook:
    return OrderBook("polymarket", "tok", ts, (BookLevel(p - 0.01, 5000.0),), (BookLevel(p + 0.01, 5000.0),))


def synthetic(ticks: int, start: int, step_ms: int = 10_000) -> Iterator[Event]:
    yield FundingQuote(start, 1e-4)
    yield VolQuote("dvol", start, 0.55)
    for k in range(ticks):
        ts = start + k * step_ms
        s = 100_000.0 + 400.0 * math.sin(k / 30)
        p = round(binary_call_price(s, K, 0.5, year_fraction(ts, EXPIRY)), 3)
        yield _hl(ts, s)
        yield _pm(ts, min(max(p, 0.05), 0.95))
        if k % 4 == 3:
            yield Trade("hyperliquid", "BTC", ts, 101_000.0, 0.15, "buy")


async def aiter(events: Iterator[Event]) -> AsyncIterator[Event]:
    for e in events:
        yield e


def journal_records(path: Path) -> list[dict[str, object]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def synth_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    tmp = tmp_path_factory.mktemp("synth")
    start = EXPIRY - 3 * HOUR
    raw, journal = tmp / "raw_a.jsonl", tmp / "journal_a.jsonl"

    async def go() -> None:
        events = recorder.record(aiter(synthetic(400, start)), raw)
        await runmod.simulate(events, SPEC, PERP, Q, "implied", journal)

    asyncio.run(go())
    return raw, journal


def test_strategies_flat_after_kill_switch(synth_run: tuple[Path, Path]) -> None:
    _, journal = synth_run
    recs = journal_records(journal)
    by: dict[str, list[dict[str, object]]] = defaultdict(list)
    for r in recs:
        by[str(r["strategy"])].append(r)
    for name in ("static", "dynamic"):
        marks = [r for r in by[name] if r["type"] == "mark"]
        fills = [r for r in by[name] if r["type"] == "fill"]
        last = marks[-1]
        assert last["hl_position"] == pytest.approx(0.0, abs=1e-9)
        assert last["net_delta_btc"] == pytest.approx(0.0, abs=1e-9)
        assert any(str(f["tag"]) == "kill_pm" for f in fills)
        assert last["ts_ms"] == EXPIRY - 2 * HOUR
        for m in marks:
            assert m["pnl_total"] == pytest.approx(
                float(m["pnl_pm"]) + float(m["pnl_hl"]) - float(m["fees_pm"]) - float(m["fees_hl"]) - float(m["funding"])  # type: ignore[arg-type]
            )
            assert "sigma_used_source" in m
        for venue, key in (("polymarket", "fees_pm"), ("hyperliquid", "fees_hl")):
            total = sum(float(f["fee"]) for f in fills if f["venue"] == venue)  # type: ignore[arg-type, misc]
            assert last[key] == pytest.approx(total)
        ts = [int(m["ts_ms"]) for m in marks]  # type: ignore[call-overload]
        assert all(b - a >= 1000 for a, b in zip(ts[:-2], ts[1:-1], strict=True))
    assert [r for r in by["static"] if r["type"] == "fill"][0]["tag"] == "entry_pm"


def test_static_single_order_dynamic_rebalances(synth_run: tuple[Path, Path]) -> None:
    _, journal = synth_run
    fills = [r for r in journal_records(journal) if r["type"] == "fill" and r["venue"] == "hyperliquid"]
    st = [f for f in fills if f["strategy"] == "static" and not str(f["tag"]).startswith("kill")]
    dy = [f for f in fills if f["strategy"] == "dynamic" and not str(f["tag"]).startswith("kill")]
    assert st and all(f["tag"] == "static_hedge" and f["maker"] for f in st)
    assert len({f["price"] for f in st}) == 1  # one resting limit order, partially filled
    assert sum(float(f["size"]) for f in st) > 0  # type: ignore[arg-type, misc]
    assert len([f for f in dy if f["tag"] == "dyn_rebal"]) > 3
    assert all(not f["maker"] for f in dy)


def test_funding_hour_crossing(synth_run: tuple[Path, Path]) -> None:
    _, journal = synth_run
    marks = [r for r in journal_records(journal) if r["type"] == "mark" and r["strategy"] == "dynamic"]
    assert marks[0]["funding"] == 0.0
    assert marks[-1]["funding"] != 0.0  # crossed an UTC hour with a position and rate 1e-4


def test_replay_matches_live(synth_run: tuple[Path, Path], tmp_path: Path) -> None:
    raw, journal = synth_run
    replayed = tmp_path / "journal_replay.jsonl"
    asyncio.run(runmod.simulate(recorder.replay(raw), SPEC, PERP, Q, "implied", replayed))
    assert replayed.read_bytes() == journal.read_bytes()


def test_plot_reads_journal(synth_run: tuple[Path, Path], tmp_path: Path) -> None:
    _, journal = synth_run
    out = tmp_path / "fig.png"
    res = subprocess.run(
        [sys.executable, "-m", "reports.plot", str(journal), "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    assert res.returncode == 0, res.stderr
    assert out.exists()


def test_implied_held_then_dvol(tmp_path: Path) -> None:
    """S<K with a mid above the digital's peak: implied is None -> held 300 s, then dvol."""
    start = EXPIRY - 5 * HOUR
    journal = tmp_path / "j.jsonl"

    def evs() -> Iterator[Event]:
        yield VolQuote("dvol", start, 0.55)
        for k in range(0, 60):
            ts = start + k * 10_000
            # S<K close to K, mid 0.49 above the peak N(-sqrt(2|x|)) -> no implied root
            yield _hl(ts, 99_500.0)
            yield _pm(ts, 0.49 if k >= 10 else 0.44)

    asyncio.run(runmod.simulate(aiter(evs()), SPEC, PERP, Q, "implied", journal))
    marks = [r for r in journal_records(journal) if r["type"] == "mark" and r["strategy"] == "static"]
    used = {str(m["ts_ms"]): m["sigma_used_source"] for m in marks}
    assert marks[0]["sigma_used_source"] in ("implied", "dvol")
    srcs = [m["sigma_used_source"] for m in marks]
    assert "implied_held" in srcs
    assert all(m["sigma_implied"] is None for m in marks if m["sigma_used_source"] == "implied_held")
    assert used  # journal non-empty


def _noisy_stream(noise_bp: float, seed: int, ticks: int) -> tuple[list[tuple[int, float, float]], float]:
    rng = random.Random(seed)
    sigma = 0.5
    s = 100_000.0
    start = EXPIRY - 10 * HOUR
    out: list[tuple[int, float, float]] = []
    for k in range(ticks):
        s *= math.exp(sigma * math.sqrt(1.0 / SECONDS_PER_YEAR) * rng.gauss(0, 1))
        out.append((start + k * 1000, s, s * (1 + noise_bp * 1e-4 * rng.gauss(0, 1))))
    return out, sigma


def test_ewma_grid_contains_microstructure_noise(tmp_path: Path) -> None:
    pts, sigma = _noisy_stream(1.0, seed=11, ticks=7200)

    tick = EwmaVol(1800)
    for ts, _, mid in pts:
        tick.update(ts, mid)

    def evs() -> Iterator[Event]:
        yield VolQuote("dvol", pts[0][0], 0.55)
        for ts, s_true, mid in pts:
            p = binary_call_price(s_true, K, 0.5, year_fraction(ts, EXPIRY))
            yield _hl(ts, mid)
            yield _pm(ts, min(max(round(p, 3), 0.05), 0.95))

    journal = tmp_path / "j.jsonl"
    asyncio.run(run_engine(aiter(evs()), runmod.build_strategies(SPEC, Q), SPEC, PERP, journal))
    last = [r for r in journal_records(journal) if r["type"] == "mark"][-1]
    grid = float(last["sigma_ewma"])  # type: ignore[arg-type]
    assert tick.value is not None
    assert tick.value > 1.6 * sigma  # tick-by-tick feeding: noise dominates
    assert grid == pytest.approx(sigma, rel=0.45)  # 60 s grid: bias contained
    assert grid < tick.value * 0.8


def test_thin_pm_book_closes_next_tick(tmp_path: Path) -> None:
    """PM bid takes half of Q at the first kill tick; the residual is closed on the next one."""
    deadline = EXPIRY - 2 * HOUR
    start = deadline - 30_000

    def evs() -> Iterator[Event]:
        for k in range(8):
            ts = start + k * 10_000
            thin = deadline <= ts < deadline + 10_000
            size = Q / 2 if thin else 5000.0
            if k == 0:
                yield _hl(ts, 100_000.0)  # one event per tick afterwards: no double sweep of one book
            yield OrderBook("polymarket", "tok", ts, (BookLevel(0.49, size),), (BookLevel(0.51, 5000.0),))

    journal = tmp_path / "j.jsonl"
    asyncio.run(runmod.simulate(aiter(evs()), SPEC, PERP, Q, "dvol", journal))
    recs = journal_records(journal)
    for name in ("static", "dynamic"):
        kills = [r for r in recs if r["strategy"] == name and r["type"] == "fill" and r["tag"] == "kill_pm"]
        assert [r["size"] for r in kills] == [Q / 2, Q / 2]
        assert kills[1]["ts_ms"] == deadline + 10_000
        final = [r for r in recs if r["strategy"] == name and r["type"] == "mark"][-1]
        assert final["kill_close_ms"] == 10_000
        assert final["ts_ms"] == deadline + 10_000


def test_same_pm_book_not_swept_twice(tmp_path: Path) -> None:
    """Two HL events with no new PM book: the PM kill sale executes once."""
    deadline = EXPIRY - 2 * HOUR

    def evs() -> Iterator[Event]:
        t0 = deadline - 10_000
        yield _pm(t0, 0.5)
        yield _hl(t0, 100_000.0)
        yield OrderBook("polymarket", "tok", deadline, (BookLevel(0.49, Q / 2),), (BookLevel(0.51, 5000.0),))
        yield _hl(deadline, 100_000.0)
        yield _hl(deadline + 1000, 100_000.0)

    journal = tmp_path / "j.jsonl"
    asyncio.run(runmod.simulate(aiter(evs()), SPEC, PERP, Q, "dvol", journal))
    for name in ("static", "dynamic"):
        kills = [r for r in journal_records(journal)
                 if r["strategy"] == name and r["type"] == "fill" and r["tag"] == "kill_pm"]
        assert [r["size"] for r in kills] == [Q / 2]


def test_replay_override_and_sweep_csv(synth_run: tuple[Path, Path], tmp_path: Path) -> None:
    import argparse
    import csv
    import shutil

    raw0, _ = synth_run
    raw = tmp_path / "raw_x.jsonl"
    shutil.copy(raw0, raw)
    meta = {"spec": SPEC.__dict__ if hasattr(SPEC, "__dict__") else {}, "perp": {}, "quantity": Q, "sigma_source": "implied"}
    from dataclasses import asdict

    meta["spec"], meta["perp"] = asdict(SPEC), asdict(PERP)
    (tmp_path / "meta_x.json").write_text(json.dumps(meta), encoding="utf-8")

    asyncio.run(runmod.replay(argparse.Namespace(raw=str(raw), threshold=0.5, sigma="dvol", tag="t")))
    out = tmp_path / "journal_x_replay_t.jsonl"
    assert out.exists()
    asyncio.run(runmod.replay(argparse.Namespace(raw=str(raw), threshold=None, sigma=None, tag="")))
    assert (tmp_path / "journal_x_replay.jsonl").read_bytes() == _journal_bytes_default(raw0)

    asyncio.run(runmod.sweep(argparse.Namespace(raw=str(raw), thresholds="0.0002,0.05")))
    rows = list(csv.DictReader((tmp_path / "sweep_x.csv").open(encoding="utf-8")))
    assert [r["threshold"] for r in rows] == ["0.0002", "0.05", "default", "default", "default", "static"]
    assert [r["sigma_source"] for r in rows] == ["implied", "implied", "implied", "dvol", "ewma", "implied"]
    assert int(rows[0]["hedge_lag_ms"]) >= 0
    assert float(rows[0]["max_abs_net_delta_btc"]) < 0.2  # excludes the entry -> first-HL-fill window
    assert list(rows[0]) == runmod.CSV_COLUMNS
    assert int(rows[0]["n_rebal"]) > int(rows[1]["n_rebal"])


def _journal_bytes_default(raw: Path) -> bytes:
    tmp = raw.parent / "ref_journal.jsonl"
    asyncio.run(runmod.simulate(recorder.replay(raw), SPEC, PERP, Q, "implied", tmp))
    return tmp.read_bytes()
