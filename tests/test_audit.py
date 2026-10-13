"""Tests de l'audit de journal sur un journal synthétique."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from risk.audit import CONTROLS, audit, main
from risk.fees import hl_fee, pm_fee

EXPIRY_MS = 1_800_000_000_000
DEADLINE_MS = EXPIRY_MS - 7_200_000
CTRL_FEE = CONTROLS[0]
CTRL_KILL_AFTER = CONTROLS[6]
CTRL_KILL_TIME = CONTROLS[7]
CTRL_FLAT = CONTROLS[8]
CTRL_CLOSE = CONTROLS[9]
CTRL_SUM = CONTROLS[3]
CTRL_PNL = CONTROLS[4]
CTRL_MAKER = CONTROLS[2]


def _fill(
    strategy: str,
    ts: int,
    venue: str,
    side: str,
    size: float,
    price: float,
    tag: str,
    maker: bool = False,
    fee: float | None = None,
) -> dict[str, Any]:
    if fee is None:
        if venue == "polymarket":
            fee = pm_fee(size, price, maker)
        else:
            fee = hl_fee(size * price, maker)
    return {
        "type": "fill",
        "strategy": strategy,
        "ts_ms": ts,
        "venue": venue,
        "side": side,
        "size": size,
        "price": price,
        "fee": fee,
        "maker": maker,
        "tag": tag,
    }


def _mark(
    strategy: str,
    ts: int,
    hl_position: float,
    pnl_pm: float,
    pnl_hl: float,
    fees_pm: float,
    fees_hl: float,
    funding: float = 0.0,
    kill_close_ms: int | None = None,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "type": "mark",
        "strategy": strategy,
        "ts_ms": ts,
        "S": 80_000.0,
        "pm_mid": 0.5,
        "hl_position": hl_position,
        "pnl_total": pnl_pm + pnl_hl - fees_pm - fees_hl - funding,
        "pnl_pm": pnl_pm,
        "pnl_hl": pnl_hl,
        "fees_pm": fees_pm,
        "fees_hl": fees_hl,
        "funding": funding,
    }
    if kill_close_ms is not None:
        rec["kill_close_ms"] = kill_close_ms
    return rec


def _valid_records(with_kill: bool = True) -> list[dict[str, Any]]:
    t_entry = DEADLINE_MS - 3_600_000
    records: list[dict[str, Any]] = [
        _fill("static", t_entry, "polymarket", "buy", 100.0, 0.5, "entry_pm"),
        _fill("static", t_entry + 1, "hyperliquid", "sell", 0.5, 80_000.0, "static_hedge", maker=True),
        _mark("static", t_entry + 2, -0.5, -2.0, 0.0, 1.75, 6.0),
    ]
    if with_kill:
        t_kill = DEADLINE_MS + 1_000
        records += [
            _fill("static", t_kill, "hyperliquid", "buy", 0.5, 80_000.0, "kill_hl"),
            _fill("static", t_kill + 1, "polymarket", "sell", 100.0, 0.5, "kill_pm"),
            _mark("static", t_kill + 2, 0.0, -2.0, -1.0, 3.5, 24.0, kill_close_ms=t_kill),
        ]
    return records


def _write(tmp_path: Path, records: list[dict[str, Any]], meta: bool = True) -> Path:
    journal = tmp_path / "journal_test.jsonl"
    journal.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    if meta:
        (tmp_path / "meta_test.json").write_text(
            json.dumps({"spec": {"expiry_ms": EXPIRY_MS}}), encoding="utf-8"
        )
    return journal


def _check(report: Any, name: str) -> Any:
    return next(c for c in report.checks if c.name == name)


def test_valid_complete_journal_passes(tmp_path: Path) -> None:
    report = audit(_write(tmp_path, _valid_records()))
    assert report.ok is True
    for c in report.checks:
        assert c.ok is True, (c.name, c.detail)


def test_falsified_fee_fails(tmp_path: Path) -> None:
    records = _valid_records()
    records[0]["fee"] = 1.0  # vrai frais : 1,75
    report = audit(_write(tmp_path, records))
    assert report.ok is False
    assert _check(report, CTRL_FEE).ok is False


def test_falsified_fee_makes_cli_exit_nonzero(tmp_path: Path) -> None:
    records = _valid_records()
    records[1]["fee"] = 0.0
    assert main([str(_write(tmp_path, records))]) == 1


def test_valid_journal_cli_exit_zero(tmp_path: Path) -> None:
    assert main([str(_write(tmp_path, _valid_records()))]) == 0


def test_taker_zero_fee_fails(tmp_path: Path) -> None:
    records = _valid_records()
    records[0]["fee"] = 0.0
    report = audit(_write(tmp_path, records))
    assert _check(report, CONTROLS[1]).ok is False


def test_hl_maker_outside_static_hedge_fails(tmp_path: Path) -> None:
    records = _valid_records()
    records[1]["tag"] = "dyn_rebal"
    report = audit(_write(tmp_path, records))
    assert _check(report, CTRL_MAKER).ok is False


def test_fills_sum_mismatch_fails(tmp_path: Path) -> None:
    records = _valid_records()
    records[-1]["fees_pm"] = 99.0
    report = audit(_write(tmp_path, records))
    assert _check(report, CTRL_SUM).ok is False


def test_pnl_decomposition_mismatch_fails(tmp_path: Path) -> None:
    records = _valid_records()
    records[2]["pnl_total"] = 123.0
    report = audit(_write(tmp_path, records))
    assert _check(report, CTRL_PNL).ok is False


def test_decreasing_fees_fail(tmp_path: Path) -> None:
    records = _valid_records()
    records[2]["fees_hl"] = 30.0
    records[2]["pnl_total"] = -2.0 - 0.0 - 1.75 - 30.0
    report = audit(_write(tmp_path, records))
    assert _check(report, CONTROLS[5]).ok is False


def test_fill_after_kill_fails(tmp_path: Path) -> None:
    records = _valid_records()
    t_late = DEADLINE_MS + 2_000
    records.insert(-1, _fill("static", t_late, "hyperliquid", "sell", 0.1, 80_000.0, "static_hedge", maker=True))
    report = audit(_write(tmp_path, records))
    assert _check(report, CTRL_KILL_AFTER).ok is False


def test_kill_before_deadline_fails(tmp_path: Path) -> None:
    records = _valid_records()
    early = DEADLINE_MS - 1
    records[3]["ts_ms"] = early
    records[4]["ts_ms"] = early
    records[5]["ts_ms"] = early
    report = audit(_write(tmp_path, records))
    assert _check(report, CTRL_KILL_TIME).ok is False


def test_open_position_at_last_mark_fails(tmp_path: Path) -> None:
    records = _valid_records()
    records[-1]["hl_position"] = -0.5
    report = audit(_write(tmp_path, records))
    assert _check(report, CTRL_FLAT).ok is False


def test_missing_kill_close_ms_fails(tmp_path: Path) -> None:
    records = _valid_records()
    del records[-1]["kill_close_ms"]
    report = audit(_write(tmp_path, records))
    assert _check(report, CTRL_CLOSE).ok is False


def test_partial_journal_is_pending_not_failure(tmp_path: Path) -> None:
    report = audit(_write(tmp_path, _valid_records(with_kill=False)))
    assert report.ok is True
    assert _check(report, CTRL_KILL_TIME).ok is None
    assert _check(report, CTRL_FLAT).ok is None
    assert _check(report, CTRL_CLOSE).ok is None


def test_partial_journal_fails_with_final_flag(tmp_path: Path) -> None:
    report = audit(_write(tmp_path, _valid_records(with_kill=False)), final=True)
    assert report.ok is False
    assert _check(report, CTRL_CLOSE).ok is False


def test_missing_meta_leaves_kill_time_pending(tmp_path: Path) -> None:
    report = audit(_write(tmp_path, _valid_records(), meta=False))
    assert _check(report, CTRL_KILL_TIME).ok is None


def test_stats_decomposition(tmp_path: Path) -> None:
    report = audit(_write(tmp_path, _valid_records()))
    (s,) = report.stats
    assert s.n_fills == 4
    assert s.premium == pytest.approx(50.0)
    assert s.fees_pm == pytest.approx(3.5)
    assert s.fees_hl == pytest.approx(24.0)
    assert s.fee_pct_premium == pytest.approx((3.5 + 24.0) / 50.0 * 100.0)
    assert s.n_rebal == 0
    assert s.hl_notional == pytest.approx(0.5 * 80_000.0 * 2)


def test_truncated_last_line_is_ignored(tmp_path: Path) -> None:
    journal = _write(tmp_path, _valid_records(with_kill=False))
    with journal.open("a", encoding="utf-8") as fh:
        fh.write('{"type":"fill","strate')
    report = audit(journal)
    assert report.ok is True
