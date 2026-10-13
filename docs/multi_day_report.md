# Validation multi-jours : strike unique contre binary strip

207 échéances journalières KXBTCD (2026-03-19 → 2026-10-11), 2 structures × 2 sources de σ. PnL en &#36; par échéance, net de frais Kalshi, frais Hyperliquid et funding. Bootstrap : 10000 tirages, graine 20261012. Test apparié sur le même jour et la même σ.

Jours extrêmes (|S1/S0 − 1| > 5 %) : 2026-06-02 (5,4 %), 2026-08-19 (6,9 %), 2026-08-20 (5,2 %), 2026-08-21 (6,7 %), 2026-09-03 (5,2 %), 2026-09-18 (6,0 %), 2026-09-21 (7,3 %). Jours au pas de 250 &#36; (9 pattes) : 177 sur 207.

## Statistiques par combinaison (total_pnl)

| Structure | σ | n | Moyenne | Médiane | Écart-type | Err.-type | Sharpe/j | Sharpe ann. | Min | Max | % gagnants | σ horaire moy. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| single | dvol | 207 | -85,01 | -131,65 | 361,80 | 25,15 | -0,235 | -4,49 | -915,94 | 1 043,56 | 41,1 | 106,43 |
| single | kalshi_iv | 207 | -74,51 | -130,36 | 381,82 | 26,54 | -0,195 | -3,73 | -967,79 | 2 052,74 | 39,1 | 104,10 |
| strip | dvol | 207 | -57,98 | -70,27 | 185,95 | 12,92 | -0,312 | -5,96 | -684,96 | 898,77 | 31,9 | 52,73 |
| strip | kalshi_iv | 207 | -53,63 | -66,15 | 200,93 | 13,97 | -0,267 | -5,10 | -804,63 | 1 229,89 | 29,5 | 49,87 |

## Décomposition de la moyenne de total_pnl

| Structure | σ | Kalshi | Perp | −Frais HL | −Funding | = PnL total | Frais Kalshi moy. |
|---|---|---|---|---|---|---|---|
| single | dvol | -84,23 | 19,57 | -17,25 | -3,11 | -85,01 | 16,69 |
| single | kalshi_iv | -84,23 | 35,95 | -22,30 | -3,93 | -74,51 | 16,69 |
| strip | dvol | -53,78 | 14,12 | -15,52 | -2,80 | -57,98 | 13,67 |
| strip | kalshi_iv | -53,78 | 21,67 | -18,27 | -3,25 | -53,63 | 13,67 |

## Tests appariés, tous les jours

Différence = b − a (strip − single, ou kalshi_iv − dvol).

| Comparaison | Variable | Diff. moyenne | t | p | IC 95 % bootstrap |
|---|---|---|---|---|---|
| strip − single (dvol) | total_pnl | 27,03 | 1,50 | 0,136 | [-8,58 ; 63,18] |
| strip − single (dvol) | σ horaire couvert | -53,70 | -21,18 | <0,001 | [-58,61 ; -48,76] |
| strip − single (kalshi_iv) | total_pnl | 20,88 | 1,14 | 0,255 | [-15,20 ; 57,35] |
| strip − single (kalshi_iv) | σ horaire couvert | -54,23 | -20,36 | <0,001 | [-59,52 ; -49,12] |
| kalshi_iv − dvol (single) | total_pnl | 10,50 | 1,29 | 0,200 | [-4,36 ; 27,44] |
| kalshi_iv − dvol (single) | σ horaire couvert | -2,32 | -0,80 | 0,422 | [-7,50 ; 3,82] |
| kalshi_iv − dvol (strip) | total_pnl | 4,35 | 0,97 | 0,334 | [-4,19 ; 13,54] |
| kalshi_iv − dvol (strip) | σ horaire couvert | -2,86 | -1,80 | 0,074 | [-5,83 ; 0,48] |

| Comparaison | Var(b)/Var(a) | σ(b)/σ(a) | IC 95 % bootstrap σ(b)/σ(a) | t Pitman-Morgan | p |
|---|---|---|---|---|---|
| strip / single (dvol) | 0,264 | 0,514 | [0,436 ; 0,579] | -14,96 | <0,001 |
| strip / single (kalshi_iv) | 0,277 | 0,526 | [0,441 ; 0,584] | -15,20 | <0,001 |
| kalshi_iv / dvol (single) | 1,114 | 1,055 | [0,957 ; 1,177] | 2,51 | 0,013 |
| kalshi_iv / dvol (strip) | 1,168 | 1,081 | [0,945 ; 1,202] | 3,46 | <0,001 |

## Robustesse : sans les 7 jours extrêmes (n = 200)

| Structure | σ | n | Moyenne | Médiane | Écart-type | Err.-type | Sharpe/j | Sharpe ann. | Min | Max | % gagnants | σ horaire moy. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| single | dvol | 200 | -107,28 | -151,05 | 329,68 | 23,31 | -0,325 | -6,22 | -915,94 | 454,86 | 39,5 | 98,67 |
| single | kalshi_iv | 200 | -105,39 | -137,32 | 312,81 | 22,12 | -0,337 | -6,44 | -914,36 | 452,26 | 37,5 | 92,10 |
| strip | dvol | 200 | -74,72 | -75,57 | 137,03 | 9,69 | -0,545 | -10,42 | -557,82 | 203,32 | 30,0 | 45,27 |
| strip | kalshi_iv | 200 | -74,55 | -67,29 | 126,16 | 8,92 | -0,591 | -11,29 | -640,69 | 200,46 | 27,5 | 40,17 |

| Comparaison | Variable | Diff. moyenne | t | p | IC 95 % bootstrap |
|---|---|---|---|---|---|
| strip − single (dvol) | total_pnl | 32,56 | 1,76 | 0,080 | [-3,86 ; 67,97] |
| strip − single (dvol) | σ horaire couvert | -53,39 | -20,46 | <0,001 | [-58,52 ; -48,34] |
| strip − single (kalshi_iv) | total_pnl | 30,84 | 1,70 | 0,091 | [-4,73 ; 66,09] |
| strip − single (kalshi_iv) | σ horaire couvert | -51,92 | -22,29 | <0,001 | [-56,49 ; -47,36] |
| kalshi_iv − dvol (single) | total_pnl | 1,89 | 0,32 | 0,747 | [-9,43 ; 13,03] |
| kalshi_iv − dvol (single) | σ horaire couvert | -6,57 | -3,85 | <0,001 | [-9,79 ; -3,21] |
| kalshi_iv − dvol (strip) | total_pnl | 0,18 | 0,05 | 0,960 | [-6,72 ; 7,02] |
| kalshi_iv − dvol (strip) | σ horaire couvert | -5,10 | -4,61 | <0,001 | [-7,20 ; -2,89] |

| Comparaison | Var(b)/Var(a) | σ(b)/σ(a) | IC 95 % bootstrap σ(b)/σ(a) | t Pitman-Morgan | p |
|---|---|---|---|---|---|
| strip / single (dvol) | 0,173 | 0,416 | [0,368 ; 0,463] | -18,50 | <0,001 |
| strip / single (kalshi_iv) | 0,163 | 0,403 | [0,347 ; 0,461] | -18,40 | <0,001 |
| kalshi_iv / dvol (single) | 0,900 | 0,949 | [0,925 ; 0,973] | -2,95 | 0,004 |
| kalshi_iv / dvol (strip) | 0,848 | 0,921 | [0,852 ; 0,998] | -3,17 | 0,002 |

## Robustesse : jours à 9 pattes seulement (n = 177)

| Structure | σ | n | Moyenne | Médiane | Écart-type | Err.-type | Sharpe/j | Sharpe ann. | Min | Max | % gagnants | σ horaire moy. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| single | dvol | 177 | -89,32 | -131,65 | 355,92 | 26,75 | -0,251 | -4,79 | -915,94 | 1 043,56 | 41,2 | 104,21 |
| single | kalshi_iv | 177 | -78,72 | -133,36 | 375,81 | 28,25 | -0,209 | -4,00 | -967,79 | 2 052,74 | 39,0 | 101,41 |
| strip | dvol | 177 | -68,50 | -75,58 | 182,53 | 13,72 | -0,375 | -7,17 | -684,96 | 898,77 | 29,9 | 51,92 |
| strip | kalshi_iv | 177 | -64,48 | -67,65 | 197,64 | 14,86 | -0,326 | -6,23 | -804,63 | 1 229,89 | 27,7 | 48,64 |

| Comparaison | Variable | Diff. moyenne | t | p | IC 95 % bootstrap |
|---|---|---|---|---|---|
| strip − single (dvol) | total_pnl | 20,83 | 1,08 | 0,282 | [-17,41 ; 58,27] |
| strip − single (dvol) | σ horaire couvert | -52,30 | -18,60 | <0,001 | [-57,87 ; -46,91] |
| strip − single (kalshi_iv) | total_pnl | 14,24 | 0,73 | 0,467 | [-24,33 ; 51,59] |
| strip − single (kalshi_iv) | σ horaire couvert | -52,77 | -17,90 | <0,001 | [-58,62 ; -47,18] |
| kalshi_iv − dvol (single) | total_pnl | 10,61 | 1,15 | 0,251 | [-6,01 ; 29,71] |
| kalshi_iv − dvol (single) | σ horaire couvert | -2,80 | -0,86 | 0,392 | [-8,44 ; 4,22] |
| kalshi_iv − dvol (strip) | total_pnl | 4,02 | 0,80 | 0,425 | [-5,19 ; 14,05] |
| kalshi_iv − dvol (strip) | σ horaire couvert | -3,27 | -1,84 | 0,067 | [-6,54 ; 0,37] |

| Comparaison | Var(b)/Var(a) | σ(b)/σ(a) | IC 95 % bootstrap σ(b)/σ(a) | t Pitman-Morgan | p |
|---|---|---|---|---|---|
| strip / single (dvol) | 0,263 | 0,513 | [0,431 ; 0,585] | -13,76 | <0,001 |
| strip / single (kalshi_iv) | 0,277 | 0,526 | [0,433 ; 0,588] | -13,97 | <0,001 |
| kalshi_iv / dvol (single) | 1,115 | 1,056 | [0,948 ; 1,196] | 2,21 | 0,029 |
| kalshi_iv / dvol (strip) | 1,172 | 1,083 | [0,934 ; 1,220] | 3,12 | 0,002 |

## Sous-période mars-mai (n = 74)

| Structure | σ | n | Moyenne | Médiane | Écart-type | Err.-type | Sharpe/j | Sharpe ann. | Min | Max | % gagnants | σ horaire moy. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| single | dvol | 74 | -95,13 | -91,48 | 334,53 | 38,89 | -0,284 | -5,43 | -915,94 | 454,86 | 43,2 | 94,19 |
| single | kalshi_iv | 74 | -101,67 | -128,90 | 322,13 | 37,45 | -0,316 | -6,03 | -914,36 | 439,41 | 35,1 | 90,09 |
| strip | dvol | 74 | -97,42 | -92,08 | 158,55 | 18,43 | -0,614 | -11,74 | -464,96 | 203,32 | 29,7 | 49,24 |
| strip | kalshi_iv | 74 | -102,26 | -87,83 | 146,77 | 17,06 | -0,697 | -13,31 | -640,69 | 145,74 | 29,7 | 44,20 |

| Comparaison | Variable | Diff. moyenne | t | p | IC 95 % bootstrap |
|---|---|---|---|---|---|
| strip − single (dvol) | total_pnl | -2,29 | -0,08 | 0,936 | [-58,09 ; 52,73] |
| strip − single (dvol) | σ horaire couvert | -44,95 | -11,46 | <0,001 | [-52,71 ; -37,59] |
| strip − single (kalshi_iv) | total_pnl | -0,60 | -0,02 | 0,983 | [-56,81 ; 53,94] |
| strip − single (kalshi_iv) | σ horaire couvert | -45,89 | -13,13 | <0,001 | [-52,79 ; -39,22] |
| kalshi_iv − dvol (single) | total_pnl | -6,53 | -0,61 | 0,544 | [-27,97 ; 13,53] |
| kalshi_iv − dvol (single) | σ horaire couvert | -4,09 | -1,31 | 0,195 | [-9,59 ; 2,47] |
| kalshi_iv − dvol (strip) | total_pnl | -4,85 | -0,71 | 0,478 | [-18,54 ; 8,04] |
| kalshi_iv − dvol (strip) | σ horaire couvert | -5,04 | -2,29 | 0,025 | [-8,96 ; -0,35] |

| Comparaison | Var(b)/Var(a) | σ(b)/σ(a) | IC 95 % bootstrap σ(b)/σ(a) | t Pitman-Morgan | p |
|---|---|---|---|---|---|
| strip / single (dvol) | 0,225 | 0,474 | [0,406 ; 0,549] | -10,29 | <0,001 |
| strip / single (kalshi_iv) | 0,208 | 0,456 | [0,372 ; 0,547] | -10,48 | <0,001 |
| kalshi_iv / dvol (single) | 0,927 | 0,963 | [0,918 ; 1,015] | -1,16 | 0,249 |
| kalshi_iv / dvol (strip) | 0,857 | 0,926 | [0,813 ; 1,060] | -1,78 | 0,080 |

## Sous-période juin-août (n = 92)

| Structure | σ | n | Moyenne | Médiane | Écart-type | Err.-type | Sharpe/j | Sharpe ann. | Min | Max | % gagnants | σ horaire moy. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| single | dvol | 92 | -93,01 | -159,98 | 353,30 | 36,83 | -0,263 | -5,03 | -796,66 | 1 003,67 | 37,0 | 109,67 |
| single | kalshi_iv | 92 | -72,79 | -135,97 | 395,39 | 41,22 | -0,184 | -3,52 | -967,79 | 2 052,74 | 39,1 | 108,60 |
| strip | dvol | 92 | -60,14 | -87,35 | 180,63 | 18,83 | -0,333 | -6,36 | -684,96 | 777,87 | 33,7 | 53,11 |
| strip | kalshi_iv | 92 | -51,17 | -66,91 | 207,22 | 21,60 | -0,247 | -4,72 | -804,63 | 1 229,89 | 29,3 | 51,98 |

| Comparaison | Variable | Diff. moyenne | t | p | IC 95 % bootstrap |
|---|---|---|---|---|---|
| strip − single (dvol) | total_pnl | 32,87 | 1,24 | 0,216 | [-19,51 ; 83,71] |
| strip − single (dvol) | σ horaire couvert | -56,56 | -14,20 | <0,001 | [-64,28 ; -48,91] |
| strip − single (kalshi_iv) | total_pnl | 21,62 | 0,79 | 0,431 | [-33,15 ; 73,48] |
| strip − single (kalshi_iv) | σ horaire couvert | -56,63 | -12,20 | <0,001 | [-66,18 ; -48,15] |
| kalshi_iv − dvol (single) | total_pnl | 20,22 | 1,38 | 0,171 | [-5,13 ; 52,04] |
| kalshi_iv − dvol (single) | σ horaire couvert | -1,07 | -0,20 | 0,844 | [-10,03 ; 10,89] |
| kalshi_iv − dvol (strip) | total_pnl | 8,97 | 1,25 | 0,216 | [-4,09 ; 23,85] |
| kalshi_iv − dvol (strip) | σ horaire couvert | -1,14 | -0,44 | 0,662 | [-5,58 ; 4,30] |

| Comparaison | Var(b)/Var(a) | σ(b)/σ(a) | IC 95 % bootstrap σ(b)/σ(a) | t Pitman-Morgan | p |
|---|---|---|---|---|---|
| strip / single (dvol) | 0,261 | 0,511 | [0,381 ; 0,604] | -10,04 | <0,001 |
| strip / single (kalshi_iv) | 0,275 | 0,524 | [0,384 ; 0,592] | -10,85 | <0,001 |
| kalshi_iv / dvol (single) | 1,252 | 1,119 | [0,928 ; 1,337] | 3,03 | 0,003 |
| kalshi_iv / dvol (strip) | 1,316 | 1,147 | [0,913 ; 1,330] | 4,02 | <0,001 |

## Sous-période septembre-octobre (n = 41)

| Structure | σ | n | Moyenne | Médiane | Écart-type | Err.-type | Sharpe/j | Sharpe ann. | Min | Max | % gagnants | σ horaire moy. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| single | dvol | 41 | -48,78 | -50,33 | 429,26 | 67,04 | -0,114 | -2,17 | -552,77 | 1 043,56 | 46,3 | 121,23 |
| single | kalshi_iv | 41 | -29,34 | -80,44 | 449,80 | 70,25 | -0,065 | -1,25 | -568,89 | 1 199,36 | 46,3 | 119,29 |
| strip | dvol | 41 | 18,04 | -43,66 | 221,73 | 34,63 | 0,081 | 1,55 | -274,73 | 898,77 | 31,7 | 58,15 |
| strip | kalshi_iv | 41 | 28,64 | -43,67 | 244,12 | 38,12 | 0,117 | 2,24 | -263,18 | 878,03 | 29,3 | 55,37 |

| Comparaison | Variable | Diff. moyenne | t | p | IC 95 % bootstrap |
|---|---|---|---|---|---|
| strip − single (dvol) | total_pnl | 66,82 | 1,42 | 0,164 | [-27,67 ; 157,12] |
| strip − single (dvol) | σ horaire couvert | -63,08 | -11,62 | <0,001 | [-73,51 ; -52,63] |
| strip − single (kalshi_iv) | total_pnl | 57,98 | 1,23 | 0,227 | [-37,45 ; 147,56] |
| strip − single (kalshi_iv) | σ horaire couvert | -63,92 | -12,00 | <0,001 | [-74,30 ; -53,78] |
| kalshi_iv − dvol (single) | total_pnl | 19,44 | 1,25 | 0,219 | [-7,62 ; 52,00] |
| kalshi_iv − dvol (single) | σ horaire couvert | -1,94 | -0,33 | 0,744 | [-11,82 ; 10,61] |
| kalshi_iv − dvol (strip) | total_pnl | 10,60 | 1,05 | 0,300 | [-7,04 ; 32,12] |
| kalshi_iv − dvol (strip) | σ horaire couvert | -2,78 | -0,71 | 0,479 | [-9,31 ; 5,42] |

| Comparaison | Var(b)/Var(a) | σ(b)/σ(a) | IC 95 % bootstrap σ(b)/σ(a) | t Pitman-Morgan | p |
|---|---|---|---|---|---|
| strip / single (dvol) | 0,267 | 0,517 | [0,319 ; 0,634] | -6,68 | <0,001 |
| strip / single (kalshi_iv) | 0,295 | 0,543 | [0,298 ; 0,642] | -6,43 | <0,001 |
| kalshi_iv / dvol (single) | 1,098 | 1,048 | [0,940 ; 1,155] | 1,32 | 0,194 |
| kalshi_iv / dvol (strip) | 1,212 | 1,101 | [0,864 ; 1,296] | 2,33 | 0,025 |
