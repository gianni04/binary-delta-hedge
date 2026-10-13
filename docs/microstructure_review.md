# Microstructure et frais : faits sourcés

Sources officielles, sauf mention contraire, relevées le 2026-10-12. Chaque fait porte son URL.

## Faits officiels

### Hyperliquid

**Abonnements WS** (https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions.md)
- `l2Book` : `{"method":"subscribe","subscription":{"type":"l2Book","coin":"BTC"}}`. Données : `{coin, levels:[Array<WsLevel>, Array<WsLevel>], time:number}`, `WsLevel = {px:string, sz:string, n:number}`. La doc ne précise pas quel tableau de `levels` correspond aux bids et lequel aux asks, ni le sens de `"A"`/`"B"`.
- `trades` : `WsTrade[] = {coin, side:string, px:string, sz:string, hash, time:number, tid:number, users:[buyer, seller]}`. Valeurs de `side` non documentées sur cette page. `tid` = hash 50 bits ; clé d'unicité suggérée `(time, coin, tid)`.
- `activeAssetCtx` : `{coin, ctx:{dayNtlVlm, prevDayPx, markPx, midPx?, funding, openInterest, oraclePx}}`. Champs de `ctx` typés `number` dans la documentation ; voir la précision plus bas sur la fixture réelle.

**Ping / keepalive** (https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/timeouts-and-heartbeats.md)
- Message : `{"method":"ping"}`. Réponse : `{"channel":"pong"}`.
- Le serveur ferme la connexion après 60 s sans message. Intervalle recommandé non précisé ; un ping inférieur à 60 s suffit.

**Tick / lot** (https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size.md)
- Prix : au plus 5 chiffres significatifs et au plus `MAX_DECIMALS − szDecimals` décimales (MAX_DECIMALS = 6 pour les perps, 8 pour le spot). Les prix entiers sont toujours autorisés.
- Taille : arrondie à `szDecimals`.
- Minimum notionnel de 10 \$ : non confirmé (ni sur cette page, ni sur la fiche perpetuals).

**szDecimals réel** (POST https://api.hyperliquid.xyz/info `{"type":"meta"}`, exécuté 2026-10-12) : BTC `szDecimals=5`, `maxLeverage=40`. Lot BTC = 0,00001 BTC. Référence : https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals.md

**Frais de base perps** (https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees.md)
- Palier 0 : taker 0,045 % (4,5 bp), maker 0,015 % (1,5 bp). Conforme aux constantes `HL_MAKER_BPS = 1.5` et `HL_TAKER_BPS = 4.5` du module de frais.

**Funding** (https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding.md)
- Fréquence horaire.
- Formule : F = P moyen + clamp(taux d'intérêt − P, −0,0005, +0,0005), P échantillonné toutes les 5 s et moyenné sur l'heure. La formule est écrite pour un taux 8 h : chaque paiement horaire vaut 1/8 du taux calculé.
- Sens : prime positive, les longs paient les shorts.

### Polymarket

**Canal market WS** (endpoint `wss://ws-subscriptions-clob.polymarket.com/ws/market` ; https://docs.polymarket.com/market-data/realtime-data.md)
- Heartbeat applicatif : trame texte `PING` toutes les 10 s ; le serveur répond `PONG`.
- `book` : `event_type, market, asset_id, timestamp, hash, bids:[{price,size}], asks:[{price,size}]` (chaînes décimales).
- `price_change` : `event_type, market, timestamp, price_changes:[{asset_id, price, size, side:"BUY"|"SELL", hash, best_bid, best_ask}]`. Sémantique de `size` non documentée (taille absolue du niveau ou delta ?). Inférence probable : taille résultante du niveau, à vérifier sur flux réel.
- `last_trade_price` : `event_type, market, asset_id, price, size, fee_rate_bps, side, timestamp, transaction_hash`.
- `tick_size_change` : `event_type, market, asset_id, old_tick_size, new_tick_size, timestamp`.
- Sources : https://docs.polymarket.com/developers/CLOB/websocket/market-channel (schémas, format snake_case) et https://docs.polymarket.com/market-data/realtime-data.md (heartbeat PING 10 s).

**Tick size et taille minimale**
- Champs Gamma observés en direct (GET https://gamma-api.polymarket.com/markets?limit=1&active=true&closed=false, 2026-10-12) : `orderPriceMinTickSize = 0.001`, `orderMinSize = 5`. Ce sont des valeurs par marché, lues à chaque marché (pas de constante 0,01 ou 0,001 en dur).
- Aucune page officielle consultée ne documente ces champs (https://docs.polymarket.com/concepts/prices-orderbook.md ne donne pas de minimum de taille).

**Frais : marchés crypto** (https://docs.polymarket.com/trading/fees.md ; https://docs.polymarket.com/developers/market-makers/maker-rebates-program.md)
- Formule officielle : `fee = C × feeRate × p × (1 − p)`, C = nombre de parts, p = prix de la part.
- `feeRate` taker crypto = **0,07** ; `feeRate` maker = **0** (les makers ne sont jamais facturés).
- Arrondi à 5 décimales ; montants < 0,00001 pUSD ramenés à 0.
- Rebate maker : 20 % des frais taker, distribué quotidiennement en pUSD (seuil 1 \$), réparti au prorata de la « fee equivalent » par marché. Le taux est à la discrétion de Polymarket.
- Symétrie : 30 ¢ et 70 ¢ ont les mêmes frais en \$.
- Exemple officiel : 100 parts à p = 0,50 → 1,75 \$.

**Formule des frais.** Les frais ne se calculent pas à partir de `taker_fee_bps` ni `maker_fee_bps` (bps linéaires). La formule retenue est `fee = shares × 0,07 × p × (1−p)` en taker, `0` en maker. Le champ Gamma `takerBaseFee = 1000` (et `makerBaseFee = 1000`), observé sur un marché, n'est pas expliqué par les pages consultées : il n'est pas utilisé comme taux.

**Résolution des marchés « Bitcoin above ___ on <date> ? »**
- La règle est lue dans le champ `description` du marché (Gamma) : le cours de clôture de la bougie 1 min Binance BTC/USDT à 12:00 heure de New York (ET), sur la date du titre, doit être supérieur au seuil du titre pour que le marché résolve Yes. Source de l'API : `gamma_event.json`, champ description.
- Les marchés up/down utilisent un TWAP Chainlink (https://docs.polymarket.com/concepts/resolution.md). C'est une autre famille de marchés.
- Une source tierce non officielle (https://polyguana.com/market/2219233 et autres) décrit aussi une bougie 1 min à 12:00 ET, ou une bougie 1 h se terminant à l'heure du titre.
- Règle à lire dans la description de chaque marché, et non à figer dans le code.

**Valeurs Gamma utiles** : `orderPriceMinTickSize`, `orderMinSize`, `feesEnabled`, `makerBaseFee`, `takerBaseFee`, `endDate` (ISO, UTC).

### Deribit

**Canal volatilité** (https://docs.deribit.com/subscriptions/market-data/deribit_volatility_indexindex_name.md ; https://docs.deribit.com/articles/notifications.md)
- Abonnement : `{"jsonrpc":"2.0","method":"public/subscribe","id":42,"params":{"channels":["deribit_volatility_index.btc_usd"]}}`. Endpoint prod `wss://deribit.com/ws/api/v2` (testnet `test.deribit.com/ws/api/v2`), d'après un résultat de recherche (non vérifié sur la page elle-même).
- Données : objet `data` avec `index_name` (ex. `btc_usd`), timestamp en ms, valeur de volatilité.
- Exemple documenté : `volatility = 129.36`. L'unité est le pourcent annualisé, pas le décimal : division par 100 avant `VolQuote.value`.
- Limite de débit : environ 3,3 req/s sur les subscribe.

## Conformité du code avec la documentation

| # | Point | Référence officielle | État du code |
|---|---|---|---|
| 1 | Frais Polymarket | fee = C·0,07·p·(1−p), maker 0 | Appliqué : `pm_fee` dans `risk/fees.py` utilise ce taux, 0 en maker, arrondi à 5 décimales. `taker_fee_bps` (renseigné par le loader, `rate × 10 000`) n'entre pas dans le calcul. |
| 2 | Volatilité DVOL | Pourcent annualisé (129,36) | Appliqué : `parse_dvol` dans `api/deribit.py` divise par 100 ; `VolQuote.value` est décimal. |
| 3 | Tick Polymarket | Gamma `orderPriceMinTickSize` (0,001 observé) | Lu par marché depuis Gamma (`parse_market`). Aucune valeur 0,01 en dur. |
| 4 | Taille minimale Polymarket | Gamma `orderMinSize` (5 observé) | Lue depuis Gamma (`min_order_size`). Pas encore appliquée à un ordre (voir 6c). |
| 5 | `PerpSpec.min_notional = 10` | Non confirmé officiellement | Conservé comme paramètre ; hypothèse signalée. |
| 6 | Ping WS | HL : `{"method":"ping"}` < 60 s ; PM : texte `PING` ; Deribit : `set_heartbeat` | Trois formats distincts implémentés : HL toutes les 30 s (`PING_INTERVAL_S`), PM `PING` toutes les 10 s, Deribit `public/set_heartbeat` à 30 s. |
| 7 | Frais HL 1,5 / 4,5 bp | Identique au palier 0 | Conforme. |
| 8 | Résolution « Bitcoin above » | Règle lue dans la description du marché | Date de fin lue depuis `endDate` (Gamma), pas en dur. Règle de résolution à lire par marché. |
| 9 | Sens `side` HL `"A"`/`"B"` | Non documenté | `"B"` = acheteur agresseur : établi sur fixture (les trades `B` s'impriment au meilleur ask du carnet de la même seconde). Mapping dans `parse_trades` : `"buy" if t["side"] == "B"`. |
| 10 | Sémantique de `price_change.size` | Non documentée | Traitée comme taille absolue (`apply_change`) ; compatible avec la fixture, non prouvé sur flux live. |

## Limites
- Non trouvé officiellement : sens de `levels` dans le canal l2Book HL, valeurs de `side` des trades HL, minimum notionnel HL, sémantique de `price_change.size`, règle exacte de résolution des marchés « Bitcoin above » (lue dans la description du marché).
- Le champ Gamma `takerBaseFee = 1000` reste non expliqué.

## Contrôle du code contre ces faits (2026-10-12)

Fixtures lues : `tests/fixtures/hyperliquid_ws.json`, `polymarket_ws.json`, `gamma_event.json`, `deribit_ws.json`, `hyperliquid_meta.json`. Code lu : `api/hyperliquid.py`, `api/polymarket.py`, `api/deribit.py`, `api/models.py`, `strategies/base.py`, `strategies/static.py`, `strategies/dynamic.py`, `risk/fees.py`.

| # | Point | Verdict | Preuve / remarque |
|---|---|---|---|
| 1 | HL trades `side "B"` = acheteur agresseur | OK (doc muette, preuve par fixture) | Les trades `B` s'impriment à 83560, meilleur ask du snapshot l2Book de la même seconde ; les `A` à 83559, meilleur bid. Séquence `B` qui monte 83531→83560, `A` qui descend 83530. |
| 2 | HL l2Book : `levels[0]` = bids décroissants, `levels[1]` = asks croissants | OK | Fixture : `levels[0]` de 83559 à 83540 (décroissant), `levels[1]` de 83560 à 83580 (croissant). `parse_l2book`. |
| 3 | PM `price_change.size` = taille absolue, `"0"` = suppression | Probable, non confirmé | Doc officielle muette (https://docs.polymarket.com/developers/CLOB/websocket/market-channel). Fixture compatible avec l'absolu (0.07 BUY 180 contre snapshot 186,04 ; 0.35 BUY 318,42 contre 568,42 ; 0.02 BUY 0 supprime 15,5), non prouvé. Filtre `asset_id` YES correct (le NO apparaît dans le même message). Si `size` était un delta, le carnet local contiendrait des niveaux négatifs ou des résidus incohérents. Chaque message est donc comparé à `best_bid` et `best_ask` : en cas d'écart, le carnet est resynchronisé par une reconnexion (`book_mismatches` compte les écarts). La session du 12/10 en a déclenché 26 en 87 minutes (log de run). |
| 4 | PM `book` : tri | OK | La fixture n'est pas triée (bids croissants, asks décroissants) ; `LocalBook.book()` trie. |
| 4b | PM `tick_size_change` | Écart ouvert | `handle_message` ignore ce type (retourne `None`). Piste : sur `tick_size_change`, mettre à jour le tick du marché, ou journaliser et forcer une reconnexion. Le tick reste celui du Gamma initial jusqu'au redémarrage. |
| 5 | Division DVOL par 100 | OK | Fixture `volatility: 37.99` (pourcent) ; `parse_dvol` renvoie 0,3799 décimal. |
| 6a | Arrondi au lot HL (`szDecimals`) | OK, remarque | `round_lot` (`strategies/base.py`) utilise `round(size, sz_decimals)`. Un arrondi peut dépasser |Δ| d'un demi-lot ; `floor` garantirait de ne jamais sur-couvrir. Non bloquant. |
| 6b | Prix HL (5 chiffres significatifs, 6 − szDecimals décimales) | Écart ouvert | Aucune fonction de tick HL. Les limites maker viennent du carnet (déjà valides), donc OK aujourd'hui. Obligatoire si un prix calculé est envoyé. |
| 6c | Tick et taille minimale PM chargés depuis Gamma | Chargés, pas encore appliqués | `parse_market` lit `orderPriceMinTickSize` et `orderMinSize` (fixture : 0,01 et 5 ; un autre marché live : 0,001 et 5). Hors du modèle de données et du loader, aucun usage. À prévoir pour un ordre limite PM : taille ≥ 5 parts (`min_order_size`) et prix arrondi au tick. |
| 7a | Ping HL | OK | `{"method":"ping"}` toutes les 30 s, sous le timeout serveur de 60 s. Doc : https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/timeouts-and-heartbeats.md |
| 7b | Ping PM | OK | Texte `PING` toutes les 10 s. `PONG` ignoré à réception. Conforme à https://docs.polymarket.com/market-data/realtime-data.md |
| 7c | Heartbeat Deribit | OK | `public/set_heartbeat`, interval 30 (minimum 10), réponse `public/test` au `test_request`. Conforme à https://docs.deribit.com/articles/connection-management-best-practices |
| 8 | Fin de marché PM | OK, lue depuis `endDate` | `parse_market` lit `endDate` (Gamma), sans 16:00 UTC en dur. Fixture `endDate 2026-10-13T16:00:00Z` = 12:00 EDT. En hiver (EST, UTC-5), midi ET correspond à 17:00 UTC : ne jamais coder 16:00 UTC. Ambiguïté : la bougie « clôturant à 12:00 » est celle de 11:59 à 12:00 ; son instant de clôture est `expiry_ms`. |

### Précisions de vérification
- Les champs `ctx` d'`activeAssetCtx` sont des chaînes dans la fixture réelle (`"funding":"0.0000125"`, `"markPx":"83558.0"`). `parse_funding` convertit avec `float()`.
- Résolution « Bitcoin above » : la règle Binance 1 min à 12:00 ET est lue dans le champ description du marché (`gamma_event.json`). Le TWAP Chainlink concerne les marchés up/down, pas celui-ci.
- Unité du funding HL : la fixture (`funding 0.0000125`, `premium -0.00039`) est cohérente avec un taux horaire (0,0000125 = 0,00125 % par heure, soit le taux d'intérêt HL de 0,01 % / 8 h, base usuelle). La doc officielle ne le dit pas ; forte présomption de taux horaire.

### Autres remarques (non bloquantes)
- `risk/fees.py` : le taux 0,07 est une constante (`PM_CRYPTO_TAKER_FEE_RATE`) et `p·(1−p)` est codé en dur. L'exposant 1 du barème `feeSchedule` est supposé ; à lire depuis `feeSchedule` si le barème change.
- Deux sources de vérité pour les frais : `MarketSpec.taker_fee_bps` (700, soit rate × 10 000, renseigné par le loader Polymarket) et la constante de `risk/fees.py`. Le moteur n'en utilise qu'une : `risk/fees.py`.
- `takerBaseFee = 1000` et `makerBaseFee = 1000` (Gamma) ne sont pas utilisés.
- Le funding est horodaté à l'heure de réception (`time.time()` dans `api/hyperliquid.py`) et non à l'heure du message : léger décalage possible, sans impact sur la moyenne horaire.
- Subscribe Polymarket `{"assets_ids":[...],"type":"market"}` : conforme à la doc officielle (même page market-channel).

### Écarts connus
- Parseurs : rien de bloquant. Restent ouverts (4b) `tick_size_change` ignoré, (6b) pas de tick HL pour les prix calculés, (6c) tick et taille minimale Polymarket chargés mais pas appliqués. Aucun n'intervient dans les simulations : les prix maker viennent du carnet et la couverture n'envoie pas d'ordre limite sur Polymarket.
- La sémantique absolue de `price_change.size` (point 3) reste une inférence, surveillée par le contrôle du meilleur bid et ask.
