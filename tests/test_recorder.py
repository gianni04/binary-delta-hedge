"""merge / record / replay / resilient."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from api import recorder
from api.models import BookLevel, Event, FundingQuote, OrderBook, Trade, VolQuote


async def agen(items: list[Event], delay: float = 0.0) -> AsyncIterator[Event]:
    for item in items:
        await asyncio.sleep(delay)
        yield item


async def collect(stream: AsyncIterator[Event]) -> list[Event]:
    return [e async for e in stream]


SAMPLE: list[Event] = [
    OrderBook("hyperliquid", "BTC", 1, (BookLevel(1.0, 2.0),), (BookLevel(2.0, 3.0),)),
    Trade("polymarket", "tok", 2, 0.5, 4.0, "buy"),
    VolQuote("dvol", 3, 0.4),
    FundingQuote(4, 1e-5),
]


def test_record_then_replay(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "run.jsonl"
    seen = asyncio.run(collect(recorder.record(agen(SAMPLE), path)))
    assert seen == SAMPLE
    assert path.read_text(encoding="utf-8").count("\n") == len(SAMPLE)
    assert asyncio.run(collect(recorder.replay(path))) == SAMPLE


def test_record_appends(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    asyncio.run(collect(recorder.record(agen(SAMPLE[:2]), path)))
    asyncio.run(collect(recorder.record(agen(SAMPLE[2:]), path)))
    assert asyncio.run(collect(recorder.replay(path))) == SAMPLE


def test_merge_interleaves_all() -> None:
    a = agen(SAMPLE[:2], 0.01)
    b = agen(SAMPLE[2:], 0.015)
    merged = asyncio.run(collect(recorder.merge(a, b)))
    assert sorted(e.ts_ms for e in merged) == [1, 2, 3, 4]


def test_merge_propagates_errors() -> None:
    async def boom() -> AsyncIterator[Event]:
        yield SAMPLE[0]
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        asyncio.run(collect(recorder.merge(boom(), agen(SAMPLE, 0.05))))


def test_resilient_reconnects(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    calls = 0

    async def flaky() -> AsyncIterator[int]:
        nonlocal calls
        calls += 1
        if calls < 8:
            raise ConnectionError("down")
        yield calls

    async def first() -> int:
        return await anext(recorder.resilient(flaky, "t"))

    assert asyncio.run(first()) == 8
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
