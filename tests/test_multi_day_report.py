"""Synthetic checks for reports.multi_day: known stats, detected shift, deterministic bootstrap."""

from __future__ import annotations

import numpy as np

from reports.multi_day import (
    Table,
    bootstrap_mean_ci,
    extreme_days,
    paired_test,
    select,
    summarize,
    variance_test,
)


def test_summarize_known_values() -> None:
    s = summarize(np.array([-1.0, 1.0, 2.0, 4.0]))
    assert s.n == 4
    assert s.mean == 1.5
    assert s.median == 1.5
    assert abs(s.std - np.std([-1, 1, 2, 4], ddof=1)) < 1e-12
    assert abs(s.se - s.std / 2) < 1e-12
    assert s.win_pct == 75.0
    assert s.min == -1.0 and s.max == 4.0
    assert abs(s.sharpe_ann - s.sharpe_day * np.sqrt(365)) < 1e-9


def test_paired_test_detects_imposed_shift() -> None:
    rng = np.random.default_rng(1)
    a = rng.normal(0, 100, 40)
    b = a + 50 + rng.normal(0, 5, 40)
    r = paired_test(a, b)
    assert r.p < 1e-6
    assert 45 < r.ci_lo < r.mean_diff < r.ci_hi < 55


def test_paired_test_no_shift_not_significant() -> None:
    rng = np.random.default_rng(2)
    a = rng.normal(0, 100, 40)
    b = a + rng.normal(0, 30, 40)
    r = paired_test(a, b)
    assert r.p > 0.05
    assert r.ci_lo < 0 < r.ci_hi


def test_bootstrap_is_deterministic() -> None:
    d = np.arange(20, dtype=np.float64)
    assert bootstrap_mean_ci(d, 500, 7) == bootstrap_mean_ci(d, 500, 7)
    lo, hi = bootstrap_mean_ci(d, 500, 7)
    assert lo < d.mean() < hi


def test_variance_test_detects_reduction() -> None:
    rng = np.random.default_rng(3)
    a = rng.normal(0, 100, 60)
    b = 0.4 * a + rng.normal(0, 5, 60)
    v = variance_test(a, b, 1000, 5)
    assert v.pm_p < 1e-6
    assert 0.3 < v.sd_ratio < 0.5
    assert v.sd_ci_lo < v.sd_ratio < v.sd_ci_hi


def test_variance_test_equal_variances() -> None:
    rng = np.random.default_rng(4)
    a = rng.normal(0, 100, 60)
    b = rng.normal(0, 100, 60)
    assert variance_test(a, b, 500, 5).pm_p > 0.01


def test_extreme_days_and_select() -> None:
    dates = ["d1", "d2"] * 2
    tbl = Table(
        dates,
        ["single"] * 2 + ["strip"] * 2,
        ["dvol"] * 4,
        {
            "s0": np.array([100.0, 100.0, 100.0, 100.0]),
            "s1": np.array([104.0, 106.0, 104.0, 106.0]),
            "total_pnl": np.array([1.0, 2.0, 3.0, 4.0]),
        },
    )
    assert extreme_days(tbl) == {"d2"}
    assert list(select(tbl, "strip", "dvol", "total_pnl", {"d2"})) == [4.0]
