"""Black-Scholes cash-or-nothing (digital call) pricing, r = 0, payoff 1.

Conventions: S spot, K strike, sigma annualised vol (decimal), T in years.
    d2 = [ln(S/K) - sigma^2 T / 2] / (sigma sqrt(T)),  d1 = d2 + sigma sqrt(T)
    price = N(d2)
    delta = phi(d2) / (S sigma sqrt(T))
    gamma = -phi(d2) d1 / (S^2 sigma^2 T)
"""

from __future__ import annotations

import math

from scipy.optimize import brentq

SECONDS_PER_YEAR: float = 365 * 24 * 3600
_SQRT2 = math.sqrt(2.0)
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)
_IV_LO = 1e-3
_IV_HI = 5.0


def _cdf(x: float) -> float:
    """Standard normal CDF: 0.5 * erfc(-x / sqrt(2))."""
    return 0.5 * math.erfc(-x / _SQRT2)


def _pdf(x: float) -> float:
    """Standard normal density: exp(-x^2 / 2) / sqrt(2 pi)."""
    return _INV_SQRT_2PI * math.exp(-0.5 * x * x)


def _check(s: float, k: float, sigma: float | None = None) -> None:
    if s <= 0 or k <= 0:
        raise ValueError(f"S and K must be > 0 (S={s}, K={k})")
    if sigma is not None and sigma <= 0:
        raise ValueError(f"sigma must be > 0 (sigma={sigma})")


def year_fraction(now_ms: int, expiry_ms: int) -> float:
    """T = max(expiry_ms - now_ms, 0) / 1000 / SECONDS_PER_YEAR."""
    return max(expiry_ms - now_ms, 0) / 1000.0 / SECONDS_PER_YEAR


def d2(s: float, k: float, sigma: float, t: float) -> float:
    """d2 = [ln(S/K) - sigma^2 T / 2] / (sigma sqrt(T)). Requires T > 0."""
    _check(s, k, sigma)
    if t <= 0:
        raise ValueError(f"d2 undefined for T <= 0 (T={t})")
    v = sigma * math.sqrt(t)
    return (math.log(s / k) - 0.5 * v * v) / v


def binary_call_price(s: float, k: float, sigma: float, t: float) -> float:
    """Price of the 1$ cash-or-nothing call: N(d2). T <= 0 gives 1 if S > K else 0."""
    _check(s, k, sigma)
    if t <= 0:
        return 1.0 if s > k else 0.0
    return _cdf(d2(s, k, sigma, t))


def binary_call_delta(s: float, k: float, sigma: float, t: float) -> float:
    """dV/dS = phi(d2) / (S sigma sqrt(T)), in 1/BTC-equivalent per share. 0 for T <= 0."""
    _check(s, k, sigma)
    if t <= 0:
        return 0.0
    return _pdf(d2(s, k, sigma, t)) / (s * sigma * math.sqrt(t))


def binary_call_gamma(s: float, k: float, sigma: float, t: float) -> float:
    """d2V/dS2 = -phi(d2) d1 / (S^2 sigma^2 T), with d1 = d2 + sigma sqrt(T). 0 for T <= 0."""
    _check(s, k, sigma)
    if t <= 0:
        return 0.0
    v = sigma * math.sqrt(t)
    dd2 = d2(s, k, sigma, t)
    return -_pdf(dd2) * (dd2 + v) / (s * s * v * v)


def implied_vol(price: float, s: float, k: float, t: float) -> float | None:
    """Vol sigma such that N(d2(sigma)) = price, or None.

    With x = ln(S/K) and v = sigma sqrt(T), d2 = x/v - v/2.
    - S >= K (x >= 0): d2 is strictly decreasing in sigma, so the price falls
      monotonically from ~1 to 0 and the root is unique on [1e-3, 5].
    - S < K (x < 0): d2 rises until v* = sqrt(2|x|) (price peaks at N(-sqrt(2|x|)) < 0.5)
      then falls, so a price below that peak has two roots. The high-vol root is
      the artefact of the digital's fall-off, not a tradable vol; we return the
      LOW-vol root, i.e. the branch where price increases with sigma (bracket
      upper bound clipped to v*/sqrt(T)). A price above the peak has no root: None.
    Returns None for price outside (0, 1), T <= 0, or no sign change in the bracket.
    """
    _check(s, k)
    if not 0.0 < price < 1.0 or t <= 0:
        return None
    lo = _IV_LO
    hi = _IV_HI
    x = math.log(s / k)
    if x < 0:
        hi = min(hi, math.sqrt(2.0 * -x / t))
        if hi <= lo:
            return None

    def f(sig: float) -> float:
        return _cdf(d2(s, k, sig, t)) - price

    f_lo, f_hi = f(lo), f(hi)
    if f_lo == 0.0:
        return lo
    if f_hi == 0.0:
        return hi
    if f_lo * f_hi > 0:
        return None
    return float(brentq(f, lo, hi, xtol=1e-12, rtol=1e-12))


class EwmaVol:
    """Time-weighted EWMA realised vol of log returns, annualised.

    For each step (dt seconds, log return r) existing sums decay by
    w = exp(-ln2 dt / half_life_s), then num += r^2 and den += dt:
        var_per_second = num / den   (a decayed average of r^2/dt weighted by dt)
        value = sqrt(var_per_second * SECONDS_PER_YEAR)
    Irregular steps are handled by the dt-aware decay; non-increasing timestamps
    and non-positive prices are ignored.
    """

    def __init__(self, half_life_s: float) -> None:
        if half_life_s <= 0:
            raise ValueError("half_life_s must be > 0")
        self.half_life_s = half_life_s
        self._last_ts: int | None = None
        self._last_price: float | None = None
        self._num = 0.0
        self._den = 0.0

    def update(self, ts_ms: int, price: float) -> None:
        """Feed one (timestamp, price) observation."""
        if price <= 0:
            return
        if self._last_ts is None or self._last_price is None:
            self._last_ts, self._last_price = ts_ms, price
            return
        dt = (ts_ms - self._last_ts) / 1000.0
        if dt <= 0:
            return
        r = math.log(price / self._last_price)
        w = math.exp(-math.log(2.0) * dt / self.half_life_s)
        self._num = self._num * w + r * r
        self._den = self._den * w + dt
        self._last_ts, self._last_price = ts_ms, price

    @property
    def value(self) -> float | None:
        """Annualised vol, or None before two distinct observations."""
        if self._den <= 0:
            return None
        return math.sqrt(self._num / self._den * SECONDS_PER_YEAR)
