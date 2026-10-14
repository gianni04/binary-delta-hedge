# BTC Binary Delta Hedge

Delta hedges a Polymarket "Bitcoin above K" binary with a BTC perpetual on Hyperliquid. The hedge is then compared with a strip of Kalshi binaries and with Deribit options, using a live recording and backtests over 207 daily expiries.

## Method

- Binary priced as N(d2). Delta from the Black-Scholes formula with zero rate, hedged with the perp.
- Static hedge (one order) against dynamic hedge (rebalance on each threshold). Kill switch 2 hours before expiry.
- Simulated execution: taker orders walk the order book level by level and pay fees. Maker orders fill only when a trade crosses their price.
- Kalshi strip: 9 NO binaries, 250 dollars apart, equal weights. It replicates a put spread.
- Benchmark against Deribit DVOL options: a put spread and a vanilla put.

## Results

- Session of 12/10/2026 (41 minutes live): static hedge P&L -80.17 $, dynamic -206.28 $. Most of the gap is Hyperliquid taker fees: 127.76 $ against 5.70 $.
- One Kalshi trade: the strip beats the single strike by 221 $. The gain comes from the Kalshi leg, not from lower gamma.
- Over 207 expiries, the strip halves the daily P&L standard deviation (361.80 $ to 185.95 $, with DVOL sigma). The mean stays negative at -58.0 $ per day.
- Against Deribit, the put spread beats the strip by 21.7 $ per day (p = 0.002). The gap reverses in September-October (-34.5 $ per day), when the Kalshi spread narrows.

![Strip against Deribit options](reports/deribit_vs_kalshi.png)

## Data

Public APIs: Polymarket CLOB, Hyperliquid, Kalshi, Deribit (DVOL and trades) and Binance BTC/USDT 1-minute candles for resolution. The raw API caches (about 1 GB) are not in the repo. The backtests download them again.

## Run it

```bash
pip install -e ".[dev]"
python -m pytest
```

The tests use captured live messages in `tests/fixtures/`. The kill-switch audit (`python -m risk.audit`) reports three checks as pending on the committed journal, because that session ended before expiry.
