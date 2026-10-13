# Friction de couverture : Kalshi contre Deribit

Note préparatoire au benchmark Deribit (voir [deribit_benchmark_report.md](deribit_benchmark_report.md)). Consultée le 2026-10-12. Calculs analytiques, hypothèses explicites, sans données de marché.

## 1. Barème Deribit (options BTC)

| Point | Valeur retenue | Statut | Source |
|---|---|---|---|
| Frais par contrat (taker, maker) | min(0,0003 BTC ; 0,125 · prix de l'option), soit 0,03 % du sous-jacent | CONFIRMÉ par extrait du support officiel (page refusée en lecture directe, HTTP 403) | support.deribit.com/hc/en-us/articles/25944746248989 (extrait de recherche) ; legacy.deribit.com/pages/information/fees (extrait) |
| Plafond | 12,5 % de la prime, avant réduction par volume | CONFIRMÉ (mêmes extraits) | idem ; deribit.zendesk.com (extrait, article ancien d'environ 573 jours) |
| Unité des prix et des frais | BTC. Formule : MIN(0,0003 BTC ; 0,125 × prix) × quantité | CONFIRMÉ (extrait) | support.deribit.com/hc/en-us/articles/25944746248989 |
| Taille de contrat | 1 BTC (multiplicateur) | CONFIRMÉ, source tierce | paradigm.co/help/products/derivatives/venues/deribit (lu le 2026-10-12) ; bloc Deribit (extrait) |
| Incrément de taille | 0,1 BTC (DO, options BTC) ; minimum de bloc 25 contrats, pour les blocs seulement | Incrément CONFIRMÉ source tierce ; minimum de trade 0,1 BTC NON CONFIRMÉ | paradigm.co ; support.deribit.com/hc/en-us/articles/25944688627229 (extrait) |
| Taux maker | Identique au taker sur les options (formule commune) | CONFIRMÉ par extrait | support.deribit.com (extrait) |
| Règle combo | Si le combo a au moins une patte achat et une patte vente, la direction la moins chère (somme des frais) tombe à 0. Les combos de même sens (straddle, strangle) sont exclus. | NON CONFIRMÉ sur la page officielle (extrait de recherche seulement) | extrait de l'article de frais support.deribit.com |
| Options journalières | Aucune règle de frais de trading trouvée. Exemptées de frais de livraison (extrait). | NON CONFIRMÉ pour le trading | extrait Zendesk |
| Frais de livraison | 0,015 % du sous-jacent, plafonné à 12,5 %. Sans objet ici : la clôture se fait à T1, avant l'expiration, donc aucune livraison. | NON CONFIRMÉ | review tierce ; extrait Zendesk |
| Tiers de volume | Standard : 0,03 %. VIP1 : 0,025 %. Le standard est retenu. | VIP1 NON CONFIRMÉ (tableau illisible dans l'extrait) | legacy.deribit.com (extrait) |

Conflits. CoinGecko indique 0,04 % ou 0,0004 BTC : ancien barème probable, non retenu. Cryptowisser évoque une structure de frais révisée mi-2026, non vérifiée : traitée comme risque.

Hypothèse retenue pour tout point non confirmé : min(0,03 % S ; 12,5 % de la prime), par patte, en taker, à l'entrée et à la sortie. La règle combo n'est utilisée que comme sensibilité.

Sources et dates (consultation 2026-10-12) : support.deribit.com/hc/en-us/articles/25944746248989 (HTTP 403 en direct, extraits de recherche) ; legacy.deribit.com/pages/information/fees (extrait ; DNS KO en direct) ; deribit.zendesk.com (403) ; docs.deribit.com/api-reference/combo-books/private-get_leg_prices.md (lu : `amount` en coin pour les options, pas de frais) ; paradigm.co/help/products/derivatives/venues/deribit (lu) ; coingecko.com/en/exchanges/deribit (conflit).

## 2. Théorie comparée de la friction

### 2.1 Formules

Kalshi, par ordre de C contrats au prix P ($, entre 0 et 1) :

$$F_K = \lceil 0{,}07\,C\,P(1-P) \rceil \ \text{cents}$$

Par contrat, en % de la prime :

$$\frac{F_K}{C\,P} = 0{,}07\,(1-P)$$

Le frais absolu est maximal en P = 0,5 : 0,0175 $ par contrat. Le frais relatif est maximal en P → 0 (7 %), et le plafonnement d'arrondi ajoute au plus 1 cent par ordre.

Deribit, par patte de quantité q (BTC), prix P_BTC (BTC) :

$$F_D = q\cdot\min\bigl(0{,}0003\ \text{BTC};\ 0{,}125\,P_{BTC}\bigr)\cdot S$$

Frais relatif :

$$\frac{F_D}{q\,P_{BTC}\,S} = \min\!\Bigl(\frac{0{,}0003}{P_{BTC}};\ 0{,}125\Bigr)$$

Le régime à frais fixes (0,03 %) s'applique tant que P_BTC > 0,0024 BTC. Pour un put ATM en Black (r = 0), P_BTC ≈ 0,3989·σ√τ, donc :

$$\frac{F_D}{\text{prime}} \approx \frac{0{,}00075}{\sigma\sqrt{\tau}}$$

Le frais relatif croît en 1/(σ√τ) : une option journalière coûte environ 2,6 fois plus, en %, qu'une option hebdomadaire au même σ (√7).

Aller-retour : Deribit est payé à l'entrée (T0) et à la sortie (T1), car la position est revendue à T1. Kalshi est payé une seule fois, car le contrat va au règlement.

$$\text{Friction}_{RT,D} = F_{D,T0} + F_{D,T1},\qquad \text{Friction}_{K} = F_{K,T0}$$

### 2.2 Chiffres (calculs analytiques, hypothèses explicites)

Hypothèses : r = 0, smile plat, S = 70 000 $ (illustratif, seul le % compte), T0 = 35 h, T1 = 11 h, σ ∈ {40 %, 55 %}. Précision ±0,2 pt (calcul gaussien analytique).

Put ATM journalier, en % de la prime d'entrée :

| Quantité | σ = 40 % | σ = 55 % |
|---|---|---|
| Prime T0 (% S) | 1,008 | 1,387 |
| Frais Deribit T0 (0,0003 BTC) | 2,97 % | 2,16 % |
| Prime T1 (% S) | 0,565 | 0,778 |
| Frais Deribit T1 | 5,31 % | 3,86 % |
| Deribit aller-retour (% prime T0) | **5,95 %** | **4,33 %** |
| Kalshi, équivalent ATM (strip de binaires sous K, pas 250 $), une fois | **4,9 %** | **4,9 %** |

Le 4,9 % Kalshi vient de Σ P_j·0,07·(1−P_j) / Σ P_j sur des binaires au pas de 250 $. Le ratio ne bouge presque pas avec σ. Les exemples de cette page prennent le pas de 250 $ des 177 jours à 9 pattes ; sur les 30 jours à 5 pattes, le pas est de 500 $ et la taille équivalente devient q = n/500.

Put spread ±1 000 $ (long K+1 125, court K−1 125, pas Deribit ; équivalent au strip Kalshi de 9 pattes) :

| Quantité | σ = 40 % | σ = 55 % |
|---|---|---|
| Prime nette T0 (% S) | 1,621 | 1,629 |
| Frais Deribit T0 (2 × 0,0003 BTC) | 3,70 % | 3,68 % |
| Prime nette T1 (% S) | 1,612 | 1,613 |
| Frais T1 (jambe longue 0,0003 ; jambe courte plafonnée à 0,000110 BTC en σ40 et 0,000276 BTC en σ55) | 2,54 % | 3,57 % |
| Deribit aller-retour (% prime T0) | **6,2 %** | **7,2 %** |
| Kalshi strip 9 pattes, une fois | **3,23 %** | **3,35 %** |
| Deribit aller-retour, si combo confirmé (0,0003 à l'entrée + 0,0003 à la sortie) | 3,7 % | 3,7 % |

Vérification dimensionnelle, n = 1 par patte : q = n/250 = 0,004 BTC. Kalshi : prime 4,50 $, frais 0,145 $ (0,18 $ si chaque patte est un ordre séparé, arrondi au cent supérieur). Deribit : prime 4,54 $ (σ40), frais entrée 0,168 $, frais sortie 0,115 $.

### 2.3 Où chaque modèle pénalise le plus

- Kalshi : le relatif vaut 0,07(1−P). Il pèse le plus sur les ailes (P → 0 : 7 % et plus avec l'arrondi). L'ATM paie le plus en absolu (1,75 ¢) mais le moins en relatif.
- Deribit : le relatif vaut min(0,0003/P_BTC ; 12,5 %). Il pèse sur les ailes deux fois plus fort (plafond 12,5 % par patte). Le frais en $ est identique à tous les strikes (0,0003·S·q), donc les options bon marché sont pénalisées en %.
- Le point faible de Deribit est l'aller-retour. Une option ATM à 40 % coûte 3 % à l'entrée et 5 % à la sortie. La patte courte du spread, presque sans valeur à T1, tombe au plafond.
- Conclusion chiffrée : en ATM, Deribit à 40 % est plus cher que Kalshi sur l'aller-retour (5,9 % contre 4,9 %). À 55 %, il est moins cher (4,3 % contre 4,9 %). Sur le spread ±1 000 $, Deribit coûte environ 2 fois plus que Kalshi (6,2-7,2 % contre 3,2-3,4 %), sauf si la règle combo se confirme (3,7 %, à égalité).

### 2.4 Gamma en escalier et gamma continu

- Kalshi : le strip est une somme de binaires. Le delta saute de n/250 à chaque strike (9 marches). Le gamma est concentré sur 9 points, et l'erreur de couverture est bornée par le pas de 250 $.
- Deribit : une option vanille ou un spread à 2 strikes a un delta continu par morceaux. Le gamma est lisse et maximal près des strikes, sans marche.

## 3. Raccordement des échéances

La fenêtre T0 = J−1 21:00 UTC → T1 = J 21:00 UTC est celle de Kalshi et du hedge Hyperliquid. Elle impose la même horloge à toutes les pattes. Le put journalier J+1 08:00 UTC est ouvert à T0 (35 h) et valorisé à T1 (11 h) : il n'expire jamais dans la fenêtre, donc aucun frais de livraison ni de règlement n'entre en jeu. L'option la plus proche qui couvre la fenêtre sans expirer dedans est ainsi la seule qui reste comparable au strip Kalshi. Le mark-to-market à T1 est la valeur de sortie, payée au taker.

## 4. Points non confirmés à lever avant conclusion

1. Règle combo (direction la moins chère à 0) : confirmer sur la page officielle, ou auprès du support Deribit.
2. Tiers VIP et changement de barème mi-2026 (Cryptowisser) : vérifier la date d'effet.
3. Minimum de trade (0,1 BTC) : confirmer le minimum et l'incrément.
4. Frais de livraison et exemption journalière : sans objet ici, à noter uniquement.
