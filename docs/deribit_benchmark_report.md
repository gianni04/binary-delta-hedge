# Kalshi strip against Deribit options (207 expiries, 2026-03-19 → 2026-10-11)

Same window for every structure: T0 = day J−1 at 21:00 UTC, T1 = day J at 21:00 UTC. Deribit: daily expiry at J+1 08:00 UTC, valued at T1 (trade smile over [T−3 h, T] in log-moneyness, plus or minus the measured half-spread). Quantity q = n/p BTC exactly, where p is the Kalshi strike step (250 $ on 177 days and 500 $ on 30). Deribit in practice requires a 0.1 BTC step. Static Hyperliquid hedge, actual fundings. Kalshi strip: DVOL sigma, budget = premium of the single strike. Fee schedule: [deribit_friction.md](deribit_friction.md).

## Total PnL covered per expiry ($)

| Structure | Mean | Median | Std dev | % winning days | Cumulative |
|---|---|---|---|---|---|
| Kalshi binary strip | -58.0 | -70.3 | 186.0 | 31.9 | -12,002 |
| Deribit put spread | -36.3 | -50.2 | 133.0 | 25.1 | -7,519 |
| Deribit vanilla put | -42.9 | -78.0 | 175.9 | 27.1 | -8,887 |

## Paired tests against the Kalshi strip

| Comparison | Mean gap ($/day) | p (paired t) | 95% bootstrap CI | Std dev / strip | Pitman-Morgan p |
|---|---|---|---|---|---|
| Deribit put spread − strip | 21.7 | 0.002 | [7.9, 35.6] | 0.71 | < 0.001 |
| Deribit vanilla put − strip | 15.0 | 0.286 | [-11.7, 42.3] | 0.95 | 0.393 |

## Friction over the 7 months

Option fees and spread only: the Hyperliquid hedge fees (same perp on both sides) are excluded. Kalshi pays its fee once (the contract goes to settlement) and its spread at entry; Deribit pays fee and half-spread at entry and at exit (closed at T1).

| Platform | Fees ($) | Spread ($) | Total friction ($) | Friction / premium | Friction per day ($) |
|---|---|---|---|---|---|
| Kalshi, strip | 2,829 | 8,472 | 11,301 | 10.1 % | 54.6 |
| Deribit, put spread (full fees) | 6,167 | 2,267 | 8,434 | 8.4 % | 40.7 |
| Deribit, put spread (combo rebate, unconfirmed) | 3,735 | 2,267 | 6,002 | 6.0 % | 29.0 |
| Deribit, vanilla put | 3,295 | 1,129 | 4,425 | 8.0 % | 21.4 |

## Before option friction (fees and spread added back)

| Structure | Mean ($) | Std dev ($) |
|---|---|---|
| Kalshi binary strip | -3.4 | 172.8 |
| Deribit put spread | 4.4 | 132.7 |
| Deribit vanilla put | -21.6 | 174.6 |

## By sub-period (Deribit − strip, $/day)

| Period | n | Put spread − strip | p | Vanilla put − strip | p | Kalshi spread per day ($) |
|---|---|---|---|---|---|---|
| March-May | 74 | 49.6 | < 0.001 | 30.7 | 0.174 | 71.4 |
| June-August | 92 | 24.2 | 0.009 | 34.5 | 0.114 | 29.7 |
| September-October | 41 | -34.5 | 0.008 | -57.0 | 0.072 | 11.1 |

## Breakdown (put spread − strip)

- Total gap: 21.7 $/day, of which option friction 13.8 $ (p 0.003) and the remainder before friction 7.8 $ (p 0.154).
- Regression of the daily gap on the same-day Kalshi spread: gap = -14.5 + 0.88 × spread (correlation 0.61).
- September-October without the days with |S1/S0 − 1| > 5% (n = 38): -32.0 $/day, p 0.012.
- Maximum payoff gap from the Deribit strike grid (500 $ step): median |gap| 111 $, median signed gap 0 $, and correlation with the PnL gap 0.01.
- Capital: the put spread is bought (median net debit 487 $, maximum loss is the option premium); median perp hedge notional 16.4 k$.

Bootstrap: 10,000 draws, seed 20261012. Pitman-Morgan: correlation between (b − a) and (b + a), Student t with n − 2 degrees of freedom.
