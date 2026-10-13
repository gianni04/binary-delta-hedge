# Vérification des grecques et de l'implied vol

Module revu : `core/math_engine.py`, avec ses tests `tests/test_math_engine.py`.

## Synthèse

- Aucune erreur de formule : d2, prix, Δ, Γ, `year_fraction`, l'annualisation et la variance EWMA sont corrects.
- `implied_vol` renvoie `None` pour S < K quand le mid YES dépasse le pic de la branche (section 4). Le moteur gère ce cas : il garde la dernière σ implicite valide 300 s, puis passe à la DVOL.
- L'EWMA calculée sur les mids du carnet gonfle la volatilité : +18 % à 1 bp de bruit, +226 % à 5 bp (section 5). Le moteur l'alimente donc sur une grille de 60 s.

## Contrôles

- `python -m pytest tests/test_math_engine.py -q` : 51 passed.
- `python -m mypy --strict core` : aucun problème.

## 1. Delta : Δ = φ(d2) / (S σ √T)

Dérivation : d2 = (ln S − ln K − σ²T/2) / (σ√T), donc ∂d2/∂S = 1/(S σ √T). Comme V = N(d2), ∂V/∂S = φ(d2) · ∂d2/∂S. Le code est identique à cette formule.

Vérification numérique : grille de 16 605 points (S/K ∈ [0,9 ; 1,1] × 41, σ ∈ [0,2 ; 1,5] × 27, T log-espacé de 5 min à 2 jours × 15), différence finie centrée à h = 1e-6·S. Erreur relative max : 5,1e-4, au point S/K = 1,065, σ = 1,05, T ≈ 48 min. Ce point est dans la queue où Δ ≈ 0 : c'est du bruit de soustraction en différence finie, pas un biais.

## 2. Gamma : Γ = −φ(d2) d1 / (S² σ² T)

Dérivation : ∂/∂S [φ(d2)/(Sσ√T)] = φ'(d2)/(Sσ√T)² − φ(d2)/(S²σ√T). Avec φ' = −xφ, on obtient −φ(d2)(d2 + σ√T)/(S²σ²T) = −φ(d2) d1/(S²σ²T). Le code est identique.

Vérification numérique : même grille, différence finie de Δ. À h = 1e-7·S, erreur relative max 2,8e-7. À h = 1e-4·S (hors test), l'erreur monte à 30 % : c'est la troncature de la différence finie (largeur de transition σ√T·S ≈ 62 $ à T = 5 min), pas le code. Le test `rel=1e-4, abs=1e-14` est donc correct mais peu sensible.

## 3. Annualisation

- `SECONDS_PER_YEAR = 365·24·3600` : base 365 jours, cohérente avec un marché ouvert 24/7.
- `year_fraction` : ms → s → années. Correct, couvert par `test_year_fraction`.
- EWMA : `sqrt(variance par seconde × SECONDS_PER_YEAR)` utilise la même base, donc cohérent avec une vol annualisée sur 365 jours.
- La DVOL est publiée en % annualisé. La conversion en décimal se fait à la lecture, dans `api/deribit.py` (division par 100). La base de 365 jours de la DVOL reste à confirmer dans la documentation Deribit.

## 4. implied_vol, branche S < K : le calcul est correct, le cas limite est géré

Branche : correcte. Avec x = ln(S/K) et v = σ√T, d2 = x/v − v/2. Sa dérivée en v est nulle en v² = −2x, donc le pic est en v* = √(2|x|), soit σ* = √(2|x|/T). Au pic, d2 = −v*, donc V_max = N(−√(2|x|)) < 0,5. Le code retient la racine basse (le prix croît avec σ). Les tests `roundtrip` et `non_monotone_branch` vérifient ce comportement.

Conséquence : pour S < K, d2 < 0 pour tout σ, donc V(σ) < 0,5 pour tout σ. `implied_vol` renvoie `None` dès que mid > N(−√(2|ln S/K|)). Seuil d'apparition du `None` :

| S/K | seuil N(−√(2·\|ln S/K\|)) |
|---|---|
| 0,9999 | 0,4944 |
| 0,999 | 0,4822 |
| 0,995 | 0,4601 |
| 0,99 | 0,4436 |
| 0,98 | 0,4203 |
| 0,95 | 0,3744 |

Exemples (T = 6 h, σ = 0,5 comme référence) :
- S/K = 0,999 : mid 0,45 donne σ = 0,315 ; mid 0,48 donne σ = 1,050 ; mid 0,49 donne `None`.
- S/K = 0,9999 : mid 0,49 donne σ = 0,167 ; mid 0,50 donne `None`.
- S = K : mid 0,50 donne `None` (V < 0,5 pour tout σ).
- Monte Carlo, 20 000 tirages S/K ∈ [0,9 ; 0,99999], mid ∈ [0,5 ; 0,99] : 100 % de `None`, comme attendu.

Le chemin `None` est couvert par `test_implied_vol_none_when_mid_above_peak`.

Fréquence sur la session du 12/10/2026 : nulle. Le YES cotait autour de 0,34 avec S sous K = 84 000 $, loin du pic, et les 4 880 valorisations ont toutes une σ implicite. Près de l'ATM, S traverse K en continu et le mid oscille autour de 0,5 : c'est là que le `None` apparaîtrait.

Un repli brut sur la DVOL poserait trois problèmes :
- (a) Changement de source à chaque tick. Autour de S/K = 0,999, la σ implicite vaut 1,05 alors que la DVOL vaut typiquement 0,5 : le Δ, donc la taille de couverture, change d'un facteur 2 selon la source. La stratégie dynamique ferait des allers-retours taker (4,5 bp).
- (b) Le motif du repli serait invisible dans le journal.
- (c) Un mid au-dessus du pic avec S < K signale un biais de drift ou un carnet périmé. Le modèle r = 0 n'est alors plus adéquat localement.

Le moteur applique une hystérésis. Si `implied_vol` renvoie `None`, il garde la dernière valeur implicite valide pendant 300 s (`HOLD_MS`), puis bascule sur la DVOL. La source retenue est journalisée à chaque valorisation (`sigma_used_source`, valeur `implied_held` pendant le maintien). La racine haute n'est pas utilisée : elle est l'artefact de la chute de la digitale.

## 5. EwmaVol : formule correcte, biais sur les mids

Formule : pour un mouvement brownien géométrique, E[r² | dt] = σ² dt. Avec num = Σ wᵏ rₖ² et den = Σ wᵏ dtₖ, on a E[num | dt] = σ² · den. La variance par seconde est donc sans biais, quels que soient les pas irréguliers. Le facteur d'annualisation est correct.

Monte Carlo sur prix propres (200 graines, 1 jour, dt ∈ {1, 2, 5, 10} s, demi-vie 1800 s, σ = 0,6) : moyenne 0,5991 (biais −0,16 %), écart-type 0,016. Le biais de Jensen de la racine est négligeable (N_eff de plusieurs milliers d'observations).

Biais microstructure, si la source `ewma` est calculée sur les mids du carnet : mêmes simulations avec bruit i.i.d. ajouté au mid, dt = 1 s :
- bruit 1 bp : vol estimée 0,706, soit +18 % ;
- bruit 5 bp : vol estimée 1,958, soit +226 %.

Cause : r² est dominé par le bruit aux petits dt (rebond bid-ask, mid qui saute), dans `EwmaVol.update`.

Corrections possibles :
- (i) rééchantillonner à pas fixe avant l'EWMA ;
- (ii) utiliser un estimateur à deux échelles (Zhang, Mykland, Aït-Sahalia), ou soustraire 2σ_bruit²/dt ;
- (iii) calculer `ewma` sur les trades HL plutôt que sur les mids.

Le moteur retient (i) : la dernière observation de chaque minute alimente l'EWMA, sur une grille de 60 s. `test_ewma_recovers_known_vol_random_walk` utilise des prix sans bruit et ne voit pas le biais. `test_ewma_grid_contains_microstructure_noise` (`tests/test_engine.py`) ajoute un bruit de mid et vérifie que la grille le contient, alors qu'une alimentation tick par tick le laisse dominer.

Formule correcte. Le biais disparaît avec la grille de 60 s, il reste si `ewma` est branchée directement sur les mids.

## 6. Cas limites T → 0 et ordres de grandeur

Comportement analytique : pour S ≠ K, Δ et Γ tendent vers 0 quand T → 0 (φ(d2) décroît vite). L'explosion est concentrée à l'ATM : Δ ∝ T^(−1/2) et Γ ∝ T^(−1/2) (car d1 ≈ σ√T/2 à l'ATM, Γ = −φ(0)/(2S²σ√T)). Pour T ≤ 0, le code renvoie Δ = Γ = 0 et le prix égal au payoff, cohérent avec le kill-switch à T − 2 h.

Q = 1000 parts, S = K = 110 000 $, σ = 0,5, taille de couverture h = −QΔ en BTC :

| T | Δ/part (BTC) | h = −QΔ (BTC) | h notionnel ($) | Γ/part (BTC/$) | Q·Γ (BTC par $ de mouvement) | w = Sσ√T ($) | Mouvement pour déclencher le seuil dynamique (10 $/S) |
|---|---|---|---|---|---|---|---|
| 6 h | 2,77e-4 | −0,277 | −30 486 | −1,26e-9 | −1,26e-6 | 1 439 | ~72 $ |
| 2 h | 4,80e-4 | −0,480 | −52 805 | −2,18e-9 | −2,18e-6 | 831 | ~42 $ |
| 30 min | 9,60e-4 | −0,960 | −105 610 | −4,36e-9 | −4,36e-6 | 416 | ~21 $ |

Lecture :
- Le notionnel de couverture vaut −Q·φ(0)/(σ√T), indépendant de S. Il vaut 30 à 106 fois le payoff maximal de la position (1 000 $). C'est un delta, pas une couverture de valeur. À prendre en compte pour la marge et le levier HL (`max_leverage`).
- Le seuil dynamique 10 $/S ≈ 9,1e-5 BTC est dépassé après environ 21 à 72 $ de mouvement selon T. Le modèle linéaire n'est valable que pour |dS| ≪ w (415 à 1 440 $).
- `szDecimals` BTC vaut 5 sur Hyperliquid, soit un lot de 1e-5 BTC ([microstructure_review.md](microstructure_review.md)). Les tailles ci-dessus sont grandes devant ce lot.

Unités : V est en $ par part, S en $ par BTC, donc Δ est en BTC par part.

## Points traités

| Réf. | Fonction | Nature | Traitement |
|---|---|---|---|
| P4 | `implied_vol` | `None` pour S < K quand mid > pic | Hystérésis de 300 s sur la dernière σ implicite valide, puis DVOL ; source journalisée |
| P5 | `EwmaVol.update` | Biais si `ewma` est calculée sur les mids : +18 % à 1 bp, +226 % à 5 bp | Grille de 60 s ; test avec bruit de mid dans `tests/test_engine.py` |

Aucune erreur dans d2, le prix, Δ, Γ, `year_fraction` ou l'annualisation.
