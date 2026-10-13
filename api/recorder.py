"""Stream plumbing: reconnection, merging, JSONL recording and replay."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import TypeVar

from api.models import Event, event_from_dict, event_to_dict

log = logging.getLogger(__name__)

T = TypeVar("T")
MAX_BACKOFF_S = 30.0


async def resilient(session: Callable[[], AsyncIterator[T]], name: str) -> AsyncIterator[T]:
    """Run ``session`` forever, reconnecting with exponential backoff capped at 30 s.

    Backoff restarts at 1 s once a session has produced an item.
    """
    delay = 1.0
    while True:
        try:
            async for item in session():
                delay = 1.0
                yield item
            log.warning("%s: stream ended, reconnecting in %.1fs", name, delay)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("%s: %s: %s, reconnecting in %.1fs", name, type(exc).__name__, exc, delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2.0, MAX_BACKOFF_S)


async def merge(*streams: AsyncIterator[T]) -> AsyncIterator[T]:
    """Interleave several async iterators in arrival order until all are exhausted."""
    queue: asyncio.Queue[tuple[int, T | BaseException | None]] = asyncio.Queue()

    async def pump(idx: int, stream: AsyncIterator[T]) -> None:
        try:
            async for item in stream:
                await queue.put((idx, item))
            await queue.put((idx, None))
        except BaseException as exc:  # noqa: BLE001 - forwarded to the consumer
            await queue.put((idx, exc))

    tasks = [asyncio.create_task(pump(i, s)) for i, s in enumerate(streams)]
    live = len(tasks)
    try:
        while live:
            _, item = await queue.get()
            if item is None:
                live -= 1
            elif isinstance(item, BaseException):
                raise item
            else:
                yield item
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def record(events: AsyncIterator[Event], path: str | Path) -> AsyncIterator[Event]:
    """Append each event to a JSONL file, then pass it through."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        async for event in events:
            fh.write(json.dumps(event_to_dict(event), separators=(",", ":")) + "\n")
            fh.flush()
            yield event


async def replay(path: str | Path) -> AsyncIterator[Event]:
    """Yield the events stored in a JSONL file, in order."""
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield event_from_dict(json.loads(line))
