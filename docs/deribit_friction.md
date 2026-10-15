# Hedging friction: Kalshi against Deribit

Preliminary note for the Deribit benchmark (see [deribit_benchmark_report.md](deribit_benchmark_report.md)). Consulted 2026-10-12. Analytical calculations with explicit assumptions, no market data.

## 1. Deribit fee schedule (BTC options)

| Item | Value used | Status | Source |
|---|---|---|---|
| Fee per contract (taker, maker) | min(0.0003 BTC, 0.125 × option price), i.e. 0.03% of the underlying | CONFIRMED by excerpt from the official support page; direct read refused on 2026-10-12 (HTTP 403), readable on 2026-10-15 (HTTP 200 with a browser user agent, after a redirect to the same article with the suffix -Fees), where the standard options fee is 3 bps maker and taker with a 12.5% cap of the premium | support.deribit.com/hc/en-us/articles/25944746248989 (search excerpt), legacy.deribit.com/pages/information/fees (excerpt) |
| Cap | 12.5% of the premium, before volume discount | CONFIRMED (same excerpts) | same, deribit.zendesk.com (excerpt, an old article of about 573 days) |
| Price and fee unit | BTC. Formula: MIN(0.0003 BTC, 0.125 × price) × quantity | CONFIRMED (excerpt) | support.deribit.com/hc/en-us/articles/25944746248989 |
| Contract size | 1 BTC (multiplier) | CONFIRMED, third-party source | paradigm.co/help/products/derivatives/venues/deribit (read 2026-10-12), Deribit block (excerpt) |
| Size increment | 0.1 BTC (DO, BTC options), minimum block of 25 contracts, blocks only | Increment CONFIRMED by third-party source, minimum trade of 0.1 BTC NOT CONFIRMED | paradigm.co, support.deribit.com/hc/en-us/articles/25944688627229 (excerpt) |
| Maker rate | Same as taker on options (common formula) | CONFIRMED by excerpt | support.deribit.com (excerpt) |
| Combo rule | If a combo has at least one buy leg and one sell leg, the cheaper direction (sum of fees) drops to 0. Same-direction combos (straddle, strangle) are excluded. | NOT CONFIRMED on the official page (search excerpt only) | excerpt of the fee article on support.deribit.com |
| Daily options | No trading fee rule found. Exempt from delivery fees (excerpt). | NOT CONFIRMED for trading | Zendesk excerpt |
| Delivery fee | 0.015% of the underlying, capped at 12.5%. Not relevant here: the position is closed at T1, before expiry, so there is no delivery. | NOT CONFIRMED | third-party review, Zendesk excerpt |
| Volume tiers | Standard: 0.03%. VIP1: 0.025%. Standard is used. | VIP1 NOT CONFIRMED (table unreadable in the excerpt) | legacy.deribit.com (excerpt) |

Sources conflict. CoinGecko shows 0.04% or 0.0004 BTC, probably an old schedule, so it is not used. Cryptowisser mentions a revised fee structure in mid-2026 that I could not verify, so it is treated as a risk.

For any point not confirmed, the assumption is min(0.03% of S, 12.5% of the premium), per leg, taker, at entry and at exit. The combo rule is used only as a sensitivity.

Sources and dates (consulted 2026-10-12): support.deribit.com/hc/en-us/articles/25944746248989 (HTTP 403 on direct fetch on 2026-10-12, search excerpts used; HTTP 200 on 2026-10-15 with a browser user agent, redirecting to the -Fees article, which also lists the combo discount, the 0.015% options delivery fee capped at 12.5%, and no delivery fee on daily options), legacy.deribit.com/pages/information/fees (excerpt, DNS error on direct fetch), deribit.zendesk.com (403), docs.deribit.com/api-reference/combo-books/private-get_leg_prices.md (read: `amount` is in coin for options, no fee), paradigm.co/help/products/derivatives/venues/deribit (read), coingecko.com/en/exchanges/deribit (conflict).

## 2. Friction under each model

### 2.1 Formulas

Kalshi, for C contracts at price P ($, between 0 and 1):


```math
F_K = \lceil 0.07\ C\ P(1-P) \rceil \ \text{cents}
```


As a share of the premium, per contract:


```math
\frac{F_K}{C\ P} = 0.07\ (1-P)
```


The absolute fee is largest at P = 0.5, at $0.0175 per contract. The relative fee is largest as P goes to 0 (7%). Rounding up adds at most one cent per order.

Deribit, per leg of quantity q (in BTC), with price P_BTC (in BTC):


```math
F_D = q\cdot\min\bigl(0.0003\ \text{BTC};\ 0.125\ P_{BTC}\bigr)\cdot S
```


Relative fee:


```math
\frac{F_D}{q\ P_{BTC}\ S} = \min\!\Bigl(\frac{0.0003}{P_{BTC}};\ 0.125\Bigr)
```


The fixed-fee regime (0.03%) applies while P_BTC > 0.0024 BTC. For an at-the-money put in Black (r = 0), P_BTC ≈ 0.3989·σ√τ, so:


```math
\frac{F_D}{\text{premium}} \approx \frac{0.00075}{\sigma\sqrt{\tau}}
```


The relative fee grows as 1/(σ√τ). A daily option therefore costs about 2.6 times more, in percent, than a weekly option at the same σ (√7).

Round trip: Deribit is paid at entry (T0) and at exit (T1), because the position is sold at T1. Kalshi is paid once, because the contract goes to settlement.


```math
\text{Friction}_{RT,D} = F_{D,T0} + F_{D,T1},\qquad \text{Friction}_{K} = F_{K,T0}
```


### 2.2 Figures (analytical calculations, explicit assumptions)

Assumptions: r = 0, flat smile, S = $70,000 (illustrative, only the percentages matter), T0 = 35 h, T1 = 11 h, σ ∈ {40%, 55%}. Precision ±0.2 pt (analytical Gaussian calculation).

At-the-money daily put, as a percentage of the entry premium:

| Quantity | σ = 40% | σ = 55% |
|---|---|---|
| Premium T0 (% of S) | 1.008 | 1.387 |
| Deribit fee T0 (0.0003 BTC) | 2.97% | 2.16% |
| Premium T1 (% of S) | 0.565 | 0.778 |
| Deribit fee T1 | 5.31% | 3.86% |
| Deribit round trip (% of T0 premium) | **5.95%** | **4.33%** |
| Kalshi, ATM equivalent (strip of binaries below K, $250 step), once | **4.9%** | **4.9%** |

The 4.9% Kalshi figure comes from Σ P_j·0.07·(1−P_j) / Σ P_j over binaries on a $250 step. The ratio barely moves with σ. The examples on this page use the $250 step of the 177 nine-leg days. On the 30 five-leg days the step is $500, and the equivalent size becomes q = n/500.

Put spread ±$1,000 (long K+1125, short K−1125, Deribit step, equivalent to the 9-leg Kalshi strip):

| Quantity | σ = 40% | σ = 55% |
|---|---|---|
| Net premium T0 (% of S) | 1.621 | 1.629 |
| Deribit fee T0 (2 × 0.0003 BTC) | 3.70% | 3.68% |
| Net premium T1 (% of S) | 1.612 | 1.613 |
| Fee T1 (long leg 0.0003, short leg capped at 0.000110 BTC at σ40 and 0.000276 BTC at σ55) | 2.54% | 3.57% |
| Deribit round trip (% of T0 premium) | **6.2%** | **7.2%** |
| Kalshi 9-leg strip, once | **3.23%** | **3.35%** |
| Deribit round trip if the combo rule is confirmed (0.0003 at entry + 0.0003 at exit) | 3.7% | 3.7% |

Dimension check, n = 1 per leg: q = n/250 = 0.004 BTC. Kalshi: premium $4.50, fee $0.145 ($0.18 if each leg is a separate order, rounded up to the next cent). Deribit: premium $4.54 (σ40), entry fee $0.168, exit fee $0.115.

### 2.3 Where each model penalises most

- Kalshi: the relative fee is 0.07(1−P). It hits the wings hardest (P → 0: 7%, more with rounding). The ATM strike pays the most in absolute terms (1.75 cents) but the least in relative terms.
- Deribit: the relative fee is min(0.0003/P_BTC, 12.5%). It hits the wings about twice as hard, because of the 12.5% cap per leg. The dollar fee is the same at every strike (0.0003·S·q), so cheap options are penalised in percentage terms.
- Deribit's weak point is the round trip. An ATM option at 40% costs 3% at entry and 5% at exit. The short leg of the spread, nearly worthless at T1, reaches the cap.
- Numbers in brief: at the ATM strike with σ = 40%, Deribit is more expensive than Kalshi on the round trip (5.9% against 4.9%). At 55% it is cheaper (4.3% against 4.9%). On the ±$1,000 spread, Deribit costs about twice as much as Kalshi (6.2-7.2% against 3.2-3.4%), unless the combo rule is confirmed. In that case it is level (3.7%).

### 2.4 Stepwise gamma and continuous gamma

- Kalshi: the strip is a sum of binaries. Delta jumps by n/250 at each strike (9 steps). Gamma sits at 9 points, and the hedging error is bounded by the $250 step.
- Deribit: a vanilla option or a two-strike spread has a continuous, piecewise delta. Gamma is smooth and peaks near the strikes, with no step.

## 3. Matching expiries

The window T0 = day J−1 21:00 UTC to T1 = day J 21:00 UTC is the one used by Kalshi and by the Hyperliquid hedge. It puts every leg on the same clock. The daily put expiring at J+1 08:00 UTC is open at T0 (35 h) and valued at T1 (11 h). It never expires inside the window, so no delivery or settlement fee applies. The nearest option that covers the window without expiring inside it is therefore the only one that stays comparable to the Kalshi strip. The mark-to-market at T1 is the exit value, paid as taker.

## 4. Open points to settle before concluding

1. Combo rule (cheapest direction at zero): confirm on the official page or with Deribit support.
2. VIP tiers and the mid-2026 schedule change (Cryptowisser): check the effective date.
3. Minimum trade (0.1 BTC): confirm the minimum and the increment.
4. Delivery fee and daily-expiry exemption: not relevant here, noted only.
