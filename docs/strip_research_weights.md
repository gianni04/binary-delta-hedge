# Weighting the Kalshi KXBTCD-26OCT1117 strip, premium budget $510

Setup: entry 2026-10-10 21:00 UTC, $`S_0=82986`$ (Hyperliquid), $`T=1`$ day $`=1/365`$ year, $`\sigma=0.3682`$ (DVOL). Premium budget $`B=510`$ dollars, the same capital as the reference single-strike trade.

## 1. Market data (1-minute candles, `end_period_ts = 1791666000`)

Reproducible request: `GET https://api.elections.kalshi.com/trade-api/v2/series/KXBTCD/markets/{ticker}/candlesticks?start_ts=1791665940&end_ts=1791666000&period_interval=1`

NO buy price $`p_i = 1 - \text{yes\_bid}_i`$ (close_dollars).

| Ticker | $`K_i`$ | yes_bid | yes_ask | $`p_i`$ (NO) |
|---|---|---|---|---|
| KXBTCD-26OCT1117-T81999.99 | 81,999.99 | 0.85 | 0.89 | 0.15 |
| KXBTCD-26OCT1117-T82249.99 | 82,249.99 | 0.83 | 0.84 | 0.17 |
| KXBTCD-26OCT1117-T82499.99 | 82,499.99 | 0.73 | 0.74 | 0.27 |
| KXBTCD-26OCT1117-T82749.99 | 82,749.99 | 0.63 | 0.65 | 0.37 |
| KXBTCD-26OCT1117-T82999.99 | 82,999.99 | 0.49 | 0.50 | 0.51 |
| KXBTCD-26OCT1117-T83249.99 | 83,249.99 | 0.38 | 0.39 | 0.62 |
| KXBTCD-26OCT1117-T83499.99 | 83,499.99 | 0.28 | 0.29 | 0.72 |
| KXBTCD-26OCT1117-T83749.99 | 83,749.99 | 0.18 | 0.19 | 0.82 |
| KXBTCD-26OCT1117-T83999.99 | 83,999.99 | 0.11 | 0.12 | 0.89 |

Strike KXBTCD-26OCT1117-T84249.99 is excluded: there is no candle at 21:00 (the last one is at 20:59, yes_bid 0.02, yes_ask 0.13). The reference at-the-money strike (82,999.99, yes_bid 0.49, NO 0.51) matches `result.json`. Strike spacing is $250, checked on the 80 markets in `event.json`.

## 2. Weighting schemes

Number of contracts per strike $`n_i = w_i\ n`$, with $`n`$ set by the budget constraint:


```math
\sum_i w_i\ p_i\ n = B \quad\Rightarrow\quad n_i=\mathrm{round}\!\left(\frac{B\ w_i}{\sum_j w_j p_j}\right)
```


(a) Uniform in $`\Delta K`$. $`w_i=\Delta K_i/\Delta K`$. The grid is regular, so $`w_i=1`$. In Carr-Madan replication, $`\sum_i \Delta K\ \mathrm{NO}(K_i)`$ approximates $`\int \mathbf 1\lbrace S_T\lt K\rbrace \ dK`$, which is a put spread.

(b) Gaussian. $`w_i=\varphi\!\big((K_i-S_0)/(S_0\sigma\sqrt T)\big)`$, with $`S_0\sigma\sqrt T=1599.35`$. With N = 9, the weights stay between 0.33 and 0.40. The scheme is nearly uniform and only removes 10 to 17% from the wings.

NO Greeks (per contract, $`d_2`$ from `core/math_engine.py`, $`r=0`$):


```math
\Delta_{NO}(K)=-\frac{\varphi(d_2)}{S\sigma\sqrt T},\qquad \Gamma_{NO}(K)=+\frac{\varphi(d_2)\ (d_2+\sigma\sqrt T)}{S^2\sigma^2 T}
```


Check: $`\Delta_{NO}(82999.99)=-0.00024940`$, identical to `delta_no_per_contract` in `result.json`.

Fee per leg: $`f_i=\lceil 0.07\ n_i\ p_i(1-p_i)\rceil_{\text{cent}}`$, rounded per leg. The single-strike reference trade pays $`f=17.50`$ dollars.

## 3. Results (total premium, fees, hedge, gamma)

| Scheme | N | Strikes | $`n_i`$ | Total premium | Total fees | $`\Delta_{\text{total}}`$ (BTC) | $`h_\text{perp}`$ (BTC) | $`\Gamma(S_0)`$ (BTC/$) | $`\max\vert\Gamma\vert`$ T=1 day | $`\max\vert\Gamma\vert`$ T=1 h |
|---|---|---|---|---|---|---|---|---|---|---|
| Reference (single strike) | 1 | 82,999.99 | 1000 | 510.00 | 17.50 | −0.249399 | 0.24940 | 1.39e-07 | 8.07e-05 (S=82,000) | 2.28e-03 (S=82,675) |
| (a) | 7 | 82,249.99…83,749.99 | 147 | 511.56 | 14.50 | −0.244620 | 0.24462 | 5.16e-07 | 7.28e-05 (ratio 0.90) | 7.45e-04 (ratio **0.33**) |
| (b) | 7 | same | 138–154 | 509.63 | 14.59 | −0.244349 | 0.24435 | 6.14e-07 | 7.29e-05 (ratio 0.90) | 7.42e-04 (ratio 0.33) |
| **(a)** | **9** | **81,999.99…83,999.99** | **113** | **510.76** | **12.94** | **−0.234405** | **0.23440** | **6.97e-07** | **6.59e-05 (ratio 0.82)** | **5.30e-04 (ratio 0.23)** |
| (b) | 9 | same | 100–122 | 509.35 | 13.20 | −0.235566 | 0.23557 | 8.59e-07 | 6.68e-05 (ratio 0.83) | 5.36e-04 (ratio 0.24) |

Maximum gamma searched over $`S\in[82000;84000]`$, in steps of 5 dollars. For the strip: $`\Gamma_\text{total}=\sum_i n_i\Gamma_{NO}(K_i)`$.

Detail of the chosen scheme (a), N = 9:

| $`K_i`$ | $`p_i`$ | $`n_i`$ | Premium ($) | Fee ($) | $`\Delta_i`$ (BTC) | $`n_i\Gamma_{NO,i}`$ |
|---|---|---|---|---|---|---|
| 81,999.99 | 0.15 | 113 | 16.95 | 1.01 | −0.023394 | 9.21e-06 |
| 82,249.99 | 0.17 | 113 | 19.21 | 1.12 | −0.025443 | 7.51e-06 |
| 82,499.99 | 0.27 | 113 | 30.51 | 1.56 | −0.026986 | 5.31e-06 |
| 82,749.99 | 0.37 | 113 | 41.81 | 1.85 | −0.027919 | 2.75e-06 |
| 82,999.99 | 0.51 | 113 | 57.63 | 1.98 | −0.028182 | 1.57e-08 |
| 83,249.99 | 0.62 | 113 | 70.06 | 1.87 | −0.027761 | −2.69e-06 |
| 83,499.99 | 0.72 | 113 | 81.36 | 1.60 | −0.026693 | −5.19e-06 |
| 83,749.99 | 0.82 | 113 | 92.66 | 1.17 | −0.025058 | −7.30e-06 |
| 83,999.99 | 0.89 | 113 | 100.57 | 0.78 | −0.022970 | −8.91e-06 |
| **Total** | | **113** | **510.76** | **12.94** | **−0.234405** | **6.97e-07** |

## 4. Recommendation

Use scheme (a): uniform in $`\Delta K`$, N = 9, with strikes symmetric around $`K_{ATM}=82,999.99`$ (the strike closest to $`S_0`$, 14 dollars away). That is $`K_k=K_{ATM}+k\cdot250`$ for $`k\in\{-4,\dots,4\}`$.

Final formula: $`n_i = \mathrm{round}\!\big(B/\sum_j p_j\big) = \mathrm{round}(510/4.52)=113`$ contracts per strike.

Reasons:

1. Replication. The $`\Delta K`$ weights are the exact put-spread approximation (Carr-Madan). The Gaussian scheme adds no useful correction here. Over 9 strikes it only changes the $`n_i`$ by 10 to 17%, so it gives no measurable gain.
2. Smoothing the cliff. Maximum gamma at T=1 h is 5.3e-04, against 2.28e-03 for the reference trade, which is 4.3 times lower. At T=1 day the ratio is 0.82. The gain comes from spreading the position over 9 strikes, not from the choice of weights.
3. Fees. $12.94 against $17.50. Fees are proportional to $`p(1-p)`$ per leg, and the premium is spread over strikes with a low $`p`$.
4. Budget. $510.76 of premium, that is +$0.76 from integer rounding. Truncating to 112 contracts would give $506.24. Rounding stays within the rule.

Rejected alternative: N = 7 (a). Gamma at T = 1 h is smoothed less well (ratio 0.33 against 0.23 for N = 9), the domain $`[82000;84000]`$ is covered more narrowly, and fees are higher ($14.50).

## 5. Hedge

```math
h_\text{perp} = -\Delta_\text{total} = -\sum_i n_i\ \Delta_{NO}(K_i) = 0.23440\ \text{BTC (long perp, rounded to } 10^{-5}\text{)}
```


This is a static hedge at entry, with no rebalancing. The single-strike reference is $`h=0.24940`$ BTC (`result.json`: 0.2494).

## 6. Payoff at expiry (before fees, static hedge)

Kalshi PnL $`=\sum_i n_i(\mathbf 1\lbrace S_T\lt K_i\rbrace -p_i)`$. Perp PnL $`=h\ (S_T-S_0)`$.

| $`S_T`$ | Single strike, unhedged | Single strike, hedged | Strip, unhedged | Strip, hedged (a, N=9) |
|---|---|---|---|---|
| 82,000 | 490.00 | 244.09 | 393.24 | 162.12 |
| 82,500 | 490.00 | 368.79 | 167.24 | 53.32 |
| 83,000 | −510.00 | −506.51 | −58.76 | −55.48 |
| 83,250 | −510.00 | −444.16 | −171.76 | −109.88 |
| 83,543.76 (realised BRTI) | −510.00 | −370.89 | −284.76 | −154.02 |
| 84,000 | −510.00 | −257.11 | −510.76 | −273.08 |

At the realised 83,543.76, the hedged strip loses less than the hedged single strike (−154 against −371). At 84,000 the hedged single strike is still better (−257 against −273), because it carries a slightly larger hedge. The strip gives a softer answer around K, with no cliff at 82,999.99.

Outside this table: Kalshi fees (about 13 dollars for the strip, against 17.50 for the single strike), Hyperliquid fees, and funding (about −1.5 dollars over 24 h for the single-strike hedge).

## 7. Assumptions and limits

- $`\sigma`$ is fixed at the DVOL value 0.3682 for all strikes (no smile). $`\Delta`$ and $`\Gamma`$ are evaluated at $`S_0`$ and at the entry $`T`$.
- Gamma at T=1 h uses the same $`\sigma`$ and a shorter $`T`$. It ignores the smile.
- The hedge is never updated. The static hedge only protects against the first move in $`S`$.
- The hedge tables exclude Hyperliquid fees.

## 8. Reproduction

The data come from `data/kalshi_one_trade/event.json` (strikes) and from the candle request in section 1. Weights, $`n_i`$, fees, $`\Delta`$, $`\Gamma`$, $`\max\vert\Gamma\vert`$ on $`[82000;84000]`$ and payoffs can be recomputed from the formulas in sections 2 to 6.
