# Pondération du strip Kalshi KXBTCD-26OCT1117, budget de prime 510 $

Cadre : entrée 2026-10-10 21:00 UTC, $`S_0=82\ 986`$ (HL), $`T=1`$ j $`=1/365`$ an, $`\sigma=0{,}3682`$ (DVOL). Budget de prime $`B=510`$ \$, soit le même capital que le trade à strike unique de référence.

## 1. Données de marché (bougies 1 min, `end_period_ts = 1791666000`)

Requête reproductible : `GET https://api.elections.kalshi.com/trade-api/v2/series/KXBTCD/markets/{ticker}/candlesticks?start_ts=1791665940&end_ts=1791666000&period_interval=1`

Prix NO d'achat $`p_i = 1 - \text{yes\_bid}_i`$ (close_dollars).

| Ticker | $`K_i`$ | yes_bid | yes_ask | $`p_i`$ (NO) |
|---|---|---|---|---|
| KXBTCD-26OCT1117-T81999.99 | 81 999,99 | 0,85 | 0,89 | 0,15 |
| KXBTCD-26OCT1117-T82249.99 | 82 249,99 | 0,83 | 0,84 | 0,17 |
| KXBTCD-26OCT1117-T82499.99 | 82 499,99 | 0,73 | 0,74 | 0,27 |
| KXBTCD-26OCT1117-T82749.99 | 82 749,99 | 0,63 | 0,65 | 0,37 |
| KXBTCD-26OCT1117-T82999.99 | 82 999,99 | 0,49 | 0,50 | 0,51 |
| KXBTCD-26OCT1117-T83249.99 | 83 249,99 | 0,38 | 0,39 | 0,62 |
| KXBTCD-26OCT1117-T83499.99 | 83 499,99 | 0,28 | 0,29 | 0,72 |
| KXBTCD-26OCT1117-T83749.99 | 83 749,99 | 0,18 | 0,19 | 0,82 |
| KXBTCD-26OCT1117-T83999.99 | 83 999,99 | 0,11 | 0,12 | 0,89 |

Le strike KXBTCD-26OCT1117-T84249.99 est exclu : aucune bougie à 21:00 (dernière à 20:59, yes_bid 0,02 / yes_ask 0,13). Le strike ATM de référence (82 999,99, yes_bid 0,49, NO 0,51) est cohérent avec `result.json`. Espacement des strikes = 250 \$, vérifié sur les 80 marchés de `event.json`.

## 2. Schémas de poids

Nombre de contrats par strike $`n_i = w_i\ n`$, avec $`n`$ fixé par la contrainte de budget :

```math
\sum_i w_i\ p_i\ n = B \quad\Rightarrow\quad n_i=\mathrm{round}\!\left(\frac{B\ w_i}{\sum_j w_j p_j}\right)
```


- **(a) Uniforme / $`\Delta K`$.** $`w_i=\Delta K_i/\Delta K`$ ; grille régulière donc $`w_i=1`$. Réplication Carr-Madan : $`\sum_i \Delta K\ \mathrm{NO}(K_i)`$ approxime $`\int \mathbf 1\lbrace S_T\lt K\rbrace \ dK`$, soit un put spread.
- **(b) Gaussien.** $`w_i=\varphi\!\big((K_i-S_0)/(S_0\sigma\sqrt T)\big)`$, avec $`S_0\sigma\sqrt T=1\ 599{,}35`$. Sur N = 9, les poids restent entre 0,33 et 0,40 : quasi uniforme, il ne fait que retirer 10 à 17 % aux ailes.

Grecques NO (par contrat, $`d_2`$ de `core/math_engine.py`, $`r=0`$) :

```math
\Delta_{NO}(K)=-\frac{\varphi(d_2)}{S\sigma\sqrt T},\qquad \Gamma_{NO}(K)=+\frac{\varphi(d_2)\ (d_2+\sigma\sqrt T)}{S^2\sigma^2 T}
```

Vérification : $`\Delta_{NO}(82\ 999{,}99)=-0{,}00024940`$, identique à `delta_no_per_contract` de `result.json`.

Frais par patte : $`f_i=\lceil 0{,}07\ n_i\ p_i(1-p_i)\rceil_{\text{cent}}`$ (arrondi par patte). Trade de référence à strike unique : $`f=17{,}50`$ \$.

## 3. Résultats (prime totale, frais, couverture, gamma)

| Schéma | N | Strikes | $`n_i`$ | Prime totale | Frais totaux | $`\Delta_{\text{total}}`$ (BTC) | $`h_\text{perp}`$ (BTC) | $`\Gamma(S_0)`$ (BTC/\$) | $`\max\vert\Gamma\vert`$ T=1 j | $`\max\vert\Gamma\vert`$ T=1 h |
|---|---|---|---|---|---|---|---|---|---|---|
| Référence (strike unique) | 1 | 82 999,99 | 1000 | 510,00 | 17,50 | −0,249399 | 0,24940 | 1,39e-07 | 8,07e-05 (S=82 000) | 2,28e-03 (S=82 675) |
| (a) | 7 | 82 249,99…83 749,99 | 147 | 511,56 | 14,50 | −0,244620 | 0,24462 | 5,16e-07 | 7,28e-05 (ratio 0,90) | 7,45e-04 (ratio **0,33**) |
| (b) | 7 | idem | 138–154 | 509,63 | 14,59 | −0,244349 | 0,24435 | 6,14e-07 | 7,29e-05 (ratio 0,90) | 7,42e-04 (ratio 0,33) |
| **(a)** | **9** | **81 999,99…83 999,99** | **113** | **510,76** | **12,94** | **−0,234405** | **0,23440** | **6,97e-07** | **6,59e-05 (ratio 0,82)** | **5,30e-04 (ratio 0,23)** |
| (b) | 9 | idem | 100–122 | 509,35 | 13,20 | −0,235566 | 0,23557 | 8,59e-07 | 6,68e-05 (ratio 0,83) | 5,36e-04 (ratio 0,24) |

Gamma max recherché sur $`S\in[82\ 000;84\ 000]`$, pas 5 \$. Pour le strip : $`\Gamma_\text{total}=\sum_i n_i\Gamma_{NO}(K_i)`$.

Détail du schéma retenu (a), N = 9 :

| $`K_i`$ | $`p_i`$ | $`n_i`$ | Prime (\$) | Frais (\$) | $`\Delta_i`$ (BTC) | $`n_i\Gamma_{NO,i}`$ |
|---|---|---|---|---|---|---|
| 81 999,99 | 0,15 | 113 | 16,95 | 1,01 | −0,023394 | 9,21e-06 |
| 82 249,99 | 0,17 | 113 | 19,21 | 1,12 | −0,025443 | 7,51e-06 |
| 82 499,99 | 0,27 | 113 | 30,51 | 1,56 | −0,026986 | 5,31e-06 |
| 82 749,99 | 0,37 | 113 | 41,81 | 1,85 | −0,027919 | 2,75e-06 |
| 82 999,99 | 0,51 | 113 | 57,63 | 1,98 | −0,028182 | 1,57e-08 |
| 83 249,99 | 0,62 | 113 | 70,06 | 1,87 | −0,027761 | −2,69e-06 |
| 83 499,99 | 0,72 | 113 | 81,36 | 1,60 | −0,026693 | −5,19e-06 |
| 83 749,99 | 0,82 | 113 | 92,66 | 1,17 | −0,025058 | −7,30e-06 |
| 83 999,99 | 0,89 | 113 | 100,57 | 0,78 | −0,022970 | −8,91e-06 |
| **Total** | | **113** | **510,76** | **12,94** | **−0,234405** | **6,97e-07** |

## 4. Recommandation

**Schéma (a), uniforme en $`\Delta K`$, N = 9, strikes symétriques autour de $`K_{ATM}=82\ 999{,}99`$ (strike le plus proche de $`S_0`$, à 14 \$) : $`K_k=K_{ATM}+k\cdot250`$, $`k\in\{-4,\dots,4\}`$.**

Formule finale : $`n_i = \mathrm{round}\!\big(B/\sum_j p_j\big) = \mathrm{round}(510/4{,}52)=113`$ contrats par strike.

Justification :
1. **Réplication.** Les poids en $`\Delta K`$ sont l'approximation exacte du put spread (Carr-Madan). Le schéma gaussien n'apporte aucune correction utile ici : sur 9 strikes, il ne change les $`n_i`$ que de 10 à 17 %. Il ne produit donc pas de gain mesurable.
2. **Lissage de la falaise.** Gamma max à T=1 h : 5,3e-04 contre 2,28e-03 pour le trade de référence, soit 4,3 fois moins. À T=1 j, ratio 0,82. Le gain vient de la dispersion sur 9 strikes, pas du choix des poids.
3. **Frais.** 12,94 \$ contre 17,50 \$ : les frais sont proportionnels à $`p(1-p)`$ par patte, et la prime se répartit sur des strikes à faible $`p`$.
4. **Budget.** 510,76 \$ de prime, soit +0,76 \$ (arrondi entier). Une troncature à 112 contrats donnerait 506,24 \$ ; l'arrondi reste conforme à la règle.

Alternative écartée : N = 7 (a). Le gamma à T = 1 h est moins bien lissé (ratio 0,33 contre 0,23 pour N = 9), le domaine $`[82\ 000;84\ 000]`$ est couvert plus étroitement et les frais sont plus élevés (14,50 \$).

## 5. Couverture


```math
h_\text{perp} = -\Delta_\text{total} = -\sum_i n_i\ \Delta_{NO}(K_i) = 0{,}23440\ \text{BTC (long perp, arrondi } 10^{-5}\text{)}
```


Couverture statique à l'entrée, sans rebalancement. Référence à strike unique : $`h=0{,}24940`$ BTC (`result.json` : 0,2494).

## 6. Payoff à l'échéance (avant frais, hedge statique)

PnL Kalshi = $`\sum_i n_i(\mathbf 1\lbrace S_T\lt K_i\rbrace -p_i)`$. PnL perp = $`h\ (S_T-S_0)`$.

| $`S_T`$ | Strike unique non couvert | Strike unique couvert | Strip non couvert | Strip couvert (a, N=9) |
|---|---|---|---|---|
| 82 000 | 490,00 | 244,09 | 393,24 | 162,12 |
| 82 500 | 490,00 | 368,79 | 167,24 | 53,32 |
| 83 000 | −510,00 | −506,51 | −58,76 | −55,48 |
| 83 250 | −510,00 | −444,16 | −171,76 | −109,88 |
| 83 543,76 (réalisé BRTI) | −510,00 | −370,89 | −284,76 | −154,02 |
| 84 000 | −510,00 | −257,11 | −510,76 | −273,08 |

Lecture : au réalisé 83 543,76, le strip couvert perd moins que le strike unique couvert (−154 contre −371). À 84 000, le strike unique couvert reste meilleur (−257 contre −273), car il porte un hedge un peu plus grand. Le strip donne une réponse plus douce autour de K (pas de falaise à 82 999,99).

Hors de ce tableau : frais Kalshi (≈ 13 \$ pour le strip, contre 17,50 \$ pour le strike unique), frais HL, funding (≈ −1,5 \$ sur 24 h pour le hedge du strike unique).

## 7. Hypothèses et limites

- $`\sigma`$ fixé à la DVOL 0,3682 pour tous les strikes (pas de smile) ; $`\Delta`$ et $`\Gamma`$ évalués à $`S_0`$ et $`T`$ d'entrée.
- Gamma T=1 h : même $`\sigma`$, $`T`$ réduit ; ne tient pas compte du smile.
- Pas de mise à jour du hedge : la couverture statique ne protège que la première variation de $`S`$.
- Pas de frais HL dans les tableaux de couverture.

## 8. Reproduction

Les données viennent de `data/kalshi_one_trade/event.json` (strikes) et de la requête de bougies de la section 1. Les poids, $`n_i`$, frais, $`\Delta`$, $`\Gamma`$, $`\max\vert\Gamma\vert`$ sur $`[82\ 000;84\ 000]`$ et payoffs se recalculent à partir des formules des sections 2 à 6.
