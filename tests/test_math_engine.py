"""Tests for core.math_engine."""

from __future__ import annotations

import math
import random

import pytest

from core.math_engine import (
    SECONDS_PER_YEAR,
    EwmaVol,
    binary_call_delta,
    binary_call_gamma,
    binary_call_price,
    d2,
    implied_vol,
    year_fraction,
)

K = 100_000.0
T = 2.0 / 365.0


@pytest.mark.parametrize("s", [95_000.0, 99_000.0, 100_000.0, 101_500.0, 106_000.0])
@pytest.mark.parametrize("sigma", [0.4, 0.7])
def test_delta_matches_finite_difference(s: float, sigma: float) -> None:
    h = s * 1e-5
    fd = (binary_call_price(s + h, K, sigma, T) - binary_call_price(s - h, K, sigma, T)) / (2 * h)
    assert binary_call_delta(s, K, sigma, T) == pytest.approx(fd, rel=1e-5)


@pytest.mark.parametrize("s", [95_000.0, 99_000.0, 101_500.0, 106_000.0])
@pytest.mark.parametrize("sigma", [0.4, 0.7])
def test_gamma_matches_finite_difference_of_delta(s: float, sigma: float) -> None:
    h = s * 1e-4
    fd = (binary_call_delta(s + h, K, sigma, T) - binary_call_delta(s - h, K, sigma, T)) / (2 * h)
    assert binary_call_gamma(s, K, sigma, T) == pytest.approx(fd, rel=1e-4, abs=1e-14)


def test_atm_values() -> None:
    sigma = 0.5
    v = sigma * math.sqrt(T)
    assert d2(K, K, sigma, T) == pytest.approx(-v / 2)
    assert binary_call_price(K, K, sigma, T) < 0.5
    assert binary_call_price(K, K, sigma, T) == pytest.approx(0.5 - v / 2 / math.sqrt(2 * math.pi), abs=1e-3)
    assert binary_call_delta(K, K, sigma, T) > 0


def test_gamma_sign() -> None:
    assert binary_call_gamma(95_000.0, K, 0.5, T) > 0
    assert binary_call_gamma(106_000.0, K, 0.5, T) < 0


def test_expiry_limits() -> None:
    assert binary_call_price(101.0, 100.0, 0.5, 0.0) == 1.0
    assert binary_call_price(99.0, 100.0, 0.5, 0.0) == 0.0
    assert binary_call_price(100.0, 100.0, 0.5, -1.0) == 0.0
    assert binary_call_delta(101.0, 100.0, 0.5, 0.0) == 0.0
    assert binary_call_gamma(101.0, 100.0, 0.5, 0.0) == 0.0
    tiny = 1e-9
    assert binary_call_price(101.0, 100.0, 0.5, tiny) == pytest.approx(1.0)
    assert binary_call_price(99.0, 100.0, 0.5, tiny) == pytest.approx(0.0)


def test_value_errors() -> None:
    for fn in (binary_call_price, binary_call_delta, binary_call_gamma):
        with pytest.raises(ValueError):
            fn(0.0, K, 0.5, T)
        with pytest.raises(ValueError):
            fn(K, -1.0, 0.5, T)
        with pytest.raises(ValueError):
            fn(K, K, 0.0, T)
    with pytest.raises(ValueError):
        implied_vol(0.5, 0.0, K, T)


def test_year_fraction() -> None:
    assert year_fraction(0, int(SECONDS_PER_YEAR * 1000)) == pytest.approx(1.0)
    assert year_fraction(10, 5) == 0.0


@pytest.mark.parametrize("s", [95_000.0, 99_900.0, 100_000.0, 100_800.0, 108_000.0])
@pytest.mark.parametrize("sigma", [0.2, 0.5, 0.9, 1.5])
def test_implied_vol_roundtrip(s: float, sigma: float) -> None:
    p = binary_call_price(s, K, sigma, T)
    iv = implied_vol(p, s, K, T)
    if s < K and math.sqrt(2 * math.log(K / s) / T) < sigma:
        # sigma sits on the high-vol branch: the low-vol root is returned instead
        assert iv is not None
        assert iv < sigma
        assert binary_call_price(s, K, iv, T) == pytest.approx(p, abs=1e-9)
    elif 1e-12 < p < 1 - 1e-12:
        assert iv == pytest.approx(sigma, rel=1e-6)


def test_implied_vol_non_monotone_branch() -> None:
    s = 95_000.0
    x = math.log(K / s)
    sigma_peak = math.sqrt(2 * x / T)
    p_max = binary_call_price(s, K, sigma_peak, T)
    high = 2.5 * sigma_peak
    p_high = binary_call_price(s, K, high, T)
    assert p_high < p_max
    iv = implied_vol(p_high, s, K, T)
    assert iv is not None and iv < sigma_peak
    assert binary_call_price(s, K, iv, T) == pytest.approx(p_high, abs=1e-9)
    assert implied_vol(min(p_max * 1.01, 0.999), s, K, T) is None


def test_implied_vol_edge_cases() -> None:
    assert implied_vol(0.0, 101.0, 100.0, T) is None
    assert implied_vol(1.0, 101.0, 100.0, T) is None
    assert implied_vol(0.5, 101.0, 100.0, 0.0) is None
    assert implied_vol(0.999999, 99.0, 100.0, T) is None


def test_ewma_none_until_two_points() -> None:
    e = EwmaVol(1800)
    assert e.value is None
    e.update(0, 100.0)
    assert e.value is None
    e.update(0, 101.0)
    assert e.value is None
    e.update(1000, 100.0)
    assert e.value == 0.0


def test_ewma_recovers_known_vol_random_walk() -> None:
    rng = random.Random(7)
    sigma = 0.6
    ts = 0
    price = 100_000.0
    e = EwmaVol(half_life_s=6 * 3600)
    for _ in range(40_000):
        dt_s = rng.choice([1.0, 2.0, 5.0, 10.0])
        ts += int(dt_s * 1000)
        price *= math.exp(sigma * math.sqrt(dt_s / SECONDS_PER_YEAR) * rng.gauss(0, 1))
        e.update(ts, price)
    assert e.value is not None
    assert e.value == pytest.approx(sigma, rel=0.10)


def test_ewma_tracks_regime_change() -> None:
    rng = random.Random(3)
    ts = 0
    price = 100.0
    e = EwmaVol(half_life_s=600)
    for sigma, n in ((0.3, 3000), (1.2, 3000)):
        for _ in range(n):
            ts += 1000
            price *= math.exp(sigma * math.sqrt(1.0 / SECONDS_PER_YEAR) * rng.gauss(0, 1))
            e.update(ts, price)
    assert e.value is not None
    assert e.value == pytest.approx(1.2, rel=0.2)


@pytest.mark.parametrize("t_days", [0.1, 1.0, 5.0])
def test_implied_vol_none_when_mid_above_peak(t_days: float) -> None:
    """S<K, mid above the digital's maximum N(-sqrt(2|x|)): no root, hence None."""
    s = 99_500.0
    peak = binary_call_price(s, K, math.sqrt(2 * math.log(K / s) / (t_days / 365.0)), t_days / 365.0)
    assert peak < 0.49
    assert implied_vol(0.49, s, K, t_days / 365.0) is None
    assert implied_vol(peak * 0.9, s, K, t_days / 365.0) is not None
