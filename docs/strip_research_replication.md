# Replicating a put spread with a strip of binaries

Theory note on the static replication of a put spread with Kalshi NO contracts. Conventions: $`r=0`$, Black-Scholes, $`T`$ in years (365 days), $`S`$ spot, $`\sigma`$ annualised, $`N`$ and $`\varphi`$ are the standard normal CDF and density. Consistent with `core/math_engine.py`: $`\text{YES}(K)=N(d_2)`$, so $`\text{NO}(K)=N(-d_2)`$.

## 1. Static replication

Identity, for all $`S\ge 0`$:


```math
(K-S)^+=\int_0^K \mathbf{1}\lbrace S\lt k\rbrace \ dk \qquad(1)
```


If $`S\lt K`$, the integrand equals 1 on $`(S,K)`$ and the integral is $`K-S`$. If $`S\ge K`$, the integrand is zero on $`(0,K)`$.

The NO at strike $`k`$ pays $`\mathbf{1}\lbrace S_T\lt k\rbrace`$. Its Black-Scholes price is:


```math
\text{NO}(k)=N(-d_2(k)),\qquad d_2(k)=\frac{\ln(S/k)-\sigma^2T/2}{\sigma\sqrt T} \qquad(2)
```


For a put spread on $`[K_{\min},K_{\max}]`$, (1) gives:


```math
(K_{\max}-S)^+-(K_{\min}-S)^+=\int_{K_{\min}}^{K_{\max}}\mathbf{1}\lbrace S\lt k\rbrace \ dk \qquad(3)
```


Strip: grid $`K_i=K_{\min}+i\ \Delta K`$, $`i=0,\dots,M`$, with $`M=(K_{\max}-K_{\min})/\Delta K`$. We hold $`n_i=Q\ \Delta K`$ NO contracts at strike $`K_i`$:


```math
\Pi_{\text{strip}}(S)=\sum_{i=0}^{M} Q\ \Delta K\ \mathbf{1}\lbrace S\lt K_i\rbrace \ \approx\ Q\big[(K_{\max}-S)^+-(K_{\min}-S)^+\big] \qquad(4)
```


Fair price, with $`r=0`$: $`\sum_i Q\ \Delta K\ N(-d_2(K_i))\approx Q\ [P(K_{\max})-P(K_{\min})]`$, where $`P`$ is the Black-Scholes put.

Discretisation error. For a fixed $`S`$, $`k\mapsto\mathbf{1}\lbrace S\lt k\rbrace`$ is monotone and bounded by 1. The Riemann sum with step $`\Delta K`$ therefore differs from the integral by at most one cell. Per scenario:


```math
\Big|\Pi_{\text{strip}}(S)-Q\big[(K_{\max}-S)^+-(K_{\min}-S)^+\big]\Big|\le Q\ \Delta K \qquad(5)
```


The error is zero if $`S`$ falls exactly on the grid, up to the boundary convention. It is bounded by $`\Delta K`$ per unit of $`Q`$, not by $`\Delta K`$ times the number of strikes.

Truncation: the strip replicates a put spread, not a put. With $`W=K_{\max}-K_{\min}`$:

- If $`S\le K_{\min}`$: $`\Pi=Q\ W`$ (constant, no extra protection).
- If $`K_{\min}\lt S\lt K_{\max}`$: $`\Pi=Q\ (K_{\max}-S)`$.
- If $`S\ge K_{\max}`$: $`\Pi=0`$.

The payoff is bounded in $`[0,QW]`$. A vanilla put would need $`K_{\min}\to 0`$, which means a grid covering the whole lower part of the distribution. Kalshi does not list that. With $`K_{\min}\gt 0`$, the gap to a vanilla put is $`Q\ (K_{\min}-S)^+\le Q\ K_{\min}`$, and it sits in the lower tail.

## 2. Binary, call spread, gamma

With $`r=0`$, put-call parity $`C-P=S-K`$ gives $`P(K+\varepsilon)-P(K)=C(K+\varepsilon)-C(K)+\varepsilon`$. Hence:


```math
\text{YES}(K)=\mathbf{1}\lbrace S\gt K\rbrace =\lim_{\varepsilon\to 0}\frac{C(K)-C(K+\varepsilon)}{\varepsilon},\qquad \text{NO}=1-\text{YES} \qquad(6)
```


A YES is therefore a long call spread of width $`\varepsilon`$, scaled by $`1/\varepsilon`$ (Hull; Taleb). A NO is a put spread of the same type, as in (3).

Useful identity, with $`r=0`$: $`S\ \varphi(d_1)=K\ \varphi(d_2)`$. It follows from $`d_1+d_2=2\ln(S/K)/(\sigma\sqrt T)`$.

Gamma of YES, as coded in `math_engine.py`:


```math
\Gamma_{\text{YES}}=-\frac{\varphi(d_2)\ d_1}{S^2\sigma^2T}=-\frac{d_1\varphi(d_1)}{K S\sigma^2T}
```


The sign flips for the NO: $`\Gamma_{\text{NO}}=+\varphi(d_2)d_1/(S^2\sigma^2T)`$. The gamma of a single binary is of order $`1/(S^2\sigma^2T)`$. Near the strike as $`T\to 0`$, it diverges as $`1/T`$.

Strip gamma, from (3) and section 3:


```math
\Gamma_{\text{strip}}=\frac{Q}{S\sigma\sqrt T}\big[\varphi(d_1(K_{\max}))-\varphi(d_1(K_{\min}))\big]
```


This is exactly the gamma of a vanilla put spread, times $`Q`$. It is bounded: $`|\Gamma_{\text{strip}}|\le 0.4\ Q/(S\sigma\sqrt T)`$. It diverges only as $`1/\sqrt T`$, like a vanilla option, and it is spread over the grid instead of concentrated on one strike.

## 3. Delta

Per contract: $`\Delta_{\text{NO}}(K)=-\varphi(d_2(K))/(S\sigma\sqrt T)`$.

Strip:


```math
\Delta_{\text{total}}=\sum_i n_i\ \Delta_{\text{NO}}(K_i)=-Q\ \Delta K\sum_i\frac{\varphi(d_2(K_i))}{S\sigma\sqrt T}
```


Continuous limit as $`\Delta K\to 0`$:


```math
\Delta_{\text{total}}\to -Q\int_{K_{\min}}^{K_{\max}}\frac{\varphi(d_2(k))}{S\sigma\sqrt T}\ dk
```


With $`\partial d_1/\partial k=-1/(k\sigma\sqrt T)`$ and $`\varphi(d_2)=(S/k)\varphi(d_1)`$:


```math
\int_{K_{\min}}^{K_{\max}}\frac{\varphi(d_2(k))}{S\sigma\sqrt T}\ dk=\int_{d_1(K_{\max})}^{d_1(K_{\min})}\varphi(v)\ dv=N(d_1(K_{\min}))-N(d_1(K_{\max}))
```


Hence:


```math
\boxed{\ \Delta_{\text{total}}\to Q\big[N(d_1(K_{\max}))-N(d_1(K_{\min}))\big]\ }
```


Check: the Black-Scholes delta of a put is $`-N(-d_1)=N(d_1)-1`$. The delta of the long put spread $`P(K_{\max})-P(K_{\min})`$ is therefore $`N(d_1(K_{\max}))-N(d_1(K_{\min}))`$. This matches the limit above.

Sign and bounds: $`d_1`$ decreases in $`K`$, so $`N(d_1(K_{\max}))\lt N(d_1(K_{\min}))`$. Hence $`\Delta_{\text{total}}\in(-Q,0)`$, negative like a long NO. For $`K_{\min}\to 0`$ and $`K_{\max}\to\infty`$, $`\Delta\to -Q`$.

Consequence for hedging: the perp to hold is $`h=-\Delta_{\text{total}}`$ in BTC, that is $`h=Q\big[N(d_1(K_{\min}))-N(d_1(K_{\max}))\big]`$. The backtest already sets the hedge to $`h=-\Delta_{\text{NO}}`$ times the number of contracts for the single strike. The same convention applies to the strip.

## 4. Limits

- At fair prices, $`E_{\mathbb Q}[\Pi_{\text{strip}}]=Q[P(K_{\max})-P(K_{\min})]`$. The single strike has the same expectation. The strip changes the distribution of the hedged PnL, not its expectation. Fees take part of it.
- Kalshi fee: $`\lceil 0.07\cdot C\cdot P(1-P)\rceil`$, rounded up to the cent, per order. A strip of $`M`$ orders pays at least $`M`$ roundings, so its cost is higher than that of a single order.
- Bid-ask spread: a strip crosses $`M`$ spreads instead of one.
- One day gives no statistical conclusion. The standard error of the daily mean is $`\sigma_{\text{PnL}}/\sqrt n`$. With $`n=1`$, a result of $-382 says nothing about the expectation.
- Non-uniform weights beyond a constant step are covered in `strip_research_weights.md`. This document only covers replication on a constant step.

## Sources

1. Carr, P. & Madan, D. (1998). "Towards a Theory of Volatility Trading". Reprinted in E. Jouini, J. Cvitanic & M. Musiela (eds.), *Option Pricing, Interest Rates and Risk Management*, Cambridge University Press, 2001, pp. 458-476. DOI 10.1017/CBO9780511569708.013.
2. Breeden, D. T. & Litzenberger, R. H. (1978). "Prices of State-Contingent Claims Implicit in Option Prices". *Journal of Business*, 51(4), 621-651. DOI 10.1086/296025.
3. Black, F. & Scholes, M. (1973). "The Pricing of Options and Corporate Liabilities". *Journal of Political Economy*, 81(3), 637-654. DOI 10.1086/260062.
4. Hull, J. C., *Options, Futures, and Other Derivatives*, Pearson, chapter "Exotic Options", section on binaries.
5. Taleb, N. N. (1997). *Dynamic Hedging: Managing Vanilla and Exotic Options*, John Wiley & Sons. See the entries "binary options" and "call spread" in the index.
6. Carr, Ellis & Gupta (1998), *Journal of Finance*, 53(3), 1165-1190. DOI 10.1111/0022-1082.00048. A separate article with a similar title. Do not confuse it with item 1.
