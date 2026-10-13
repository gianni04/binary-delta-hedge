# Strip Kalshi contre options Deribit (207 échéances, 2026-03-19 → 2026-10-11)

Même fenêtre partout : T0 = J−1 21:00 UTC → T1 = J 21:00 UTC. Deribit : journalière J+1 08:00 UTC valorisée à T1 (smile des trades [T−3 h, T] en log-moneyness, ± demi-spread mesuré), quantité q = n/p BTC exacte, p étant le pas des strikes Kalshi (250 $ sur 177 jours, 500 $ sur 30 ; Deribit impose en réalité un pas de 0,1 BTC). Hedge statique Hyperliquid, fundings réels. Strip Kalshi : σ DVOL, budget = prime du strike unique. Barème des frais : [deribit_friction.md](deribit_friction.md).

## PnL total couvert par échéance ($)

| Structure | Moyenne | Médiane | Écart-type | % jours gagnants | Cumul |
|---|---|---|---|---|---|
| Strip binaire Kalshi | -58,0 | -70,3 | 186,0 | 31,9 | -12 002 |
| Put spread Deribit | -36,3 | -50,2 | 133,0 | 25,1 | -7 519 |
| Put vanille Deribit | -42,9 | -78,0 | 175,9 | 27,1 | -8 887 |

## Tests appariés contre le strip Kalshi

| Comparaison | Écart moyen ($/jour) | p (t apparié) | IC 95 % bootstrap | Écart-type / strip | p Pitman-Morgan |
|---|---|---|---|---|---|
| Put spread Deribit − strip | 21,7 | 0,002 | [7,9 ; 35,6] | 0,71 | < 0,001 |
| Put vanille Deribit − strip | 15,0 | 0,286 | [-11,7 ; 42,3] | 0,95 | 0,393 |

## Friction sur les 7 mois

Frais et spread de l'option seulement : les frais du hedge Hyperliquid (même perp des deux côtés) sont exclus. Kalshi paie ses frais une fois (le contrat va au règlement) et son spread à l'entrée ; Deribit paie frais et demi-spread à l'entrée et à la sortie (clôture à T1).

| Plateforme | Frais ($) | Spread ($) | Friction totale ($) | Friction / prime | Friction par jour ($) |
|---|---|---|---|---|---|
| Kalshi, strip | 2 829 | 8 472 | 11 301 | 10,1 % | 54,6 |
| Deribit, put spread (frais pleins) | 6 167 | 2 267 | 8 434 | 8,4 % | 40,7 |
| Deribit, put spread (remise combo, non confirmée) | 3 735 | 2 267 | 6 002 | 6,0 % | 29,0 |
| Deribit, put vanille | 3 295 | 1 129 | 4 425 | 8,0 % | 21,4 |

## Avant friction d'option (frais et spread rajoutés)

| Structure | Moyenne ($) | Écart-type ($) |
|---|---|---|
| Strip binaire Kalshi | -3,4 | 172,8 |
| Put spread Deribit | 4,4 | 132,7 |
| Put vanille Deribit | -21,6 | 174,6 |

## Par sous-période (Deribit − strip, $/jour)

| Période | n | Put spread − strip | p | Put vanille − strip | p | Spread Kalshi par jour ($) |
|---|---|---|---|---|---|---|
| Mars-mai | 74 | 49,6 | < 0,001 | 30,7 | 0,174 | 71,4 |
| Juin-août | 92 | 24,2 | 0,009 | 34,5 | 0,114 | 29,7 |
| Septembre-octobre | 41 | -34,5 | 0,008 | -57,0 | 0,072 | 11,1 |

## Décomposition et robustesse (put spread − strip)

- Écart total : 21,7 $/jour, dont friction d'option 13,8 $ (p 0,003) et reste avant friction 7,8 $ (p 0,154).
- Régression de l'écart quotidien sur le spread Kalshi du jour : écart = -14,5 + 0,88 × spread (corrélation 0,61).
- Septembre-octobre sans les jours |S1/S0 − 1| > 5 % (n = 38) : -32,0 $/jour, p 0,012.
- Écart de payoff maximal dû à la grille Deribit (pas de 500 $) : |écart| médian 111 $, médiane signée 0 $ ; corrélation avec l'écart de PnL 0,01.
- Capital : le put spread est acheté (débit net médian 487 $, perte maximale de l'option) ; nominal médian du hedge perp 16,4 k$.

Bootstrap : 10 000 tirages, graine 20261012. Pitman-Morgan : corrélation entre (b − a) et (b + a), t de Student à n − 2 ddl.
