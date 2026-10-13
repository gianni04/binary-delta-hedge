# Réplication d'un put spread par un strip de binaires

Note théorique sur la réplication statique d'un put spread par des NO Kalshi. Conventions : $`r=0`$, Black-Scholes, $`T`$ en années (365 j), $`S`$ spot, $`\sigma`$ annualisée, $`N`$ et $`\varphi`$ = CDF et densité normales standard. Cohérent avec `core/math_engine.py` : $`\text{YES}(K)=N(d_2)`$, donc $`\text{NO}(K)=N(-d_2)`$.

## 1. Réplication statique

Identité, pour tout $`S\ge 0`$ :


```math
(K-S)^+=\int_0^K \mathbf{1}\lbrace S\lt k\rbrace \ dk \qquad(1)
```


Si $`S\lt K`$, l'intégrande vaut 1 sur $`(S,K)`$ et l'intégrale vaut $`K-S`$. Si $`S\ge K`$, l'intégrande est nulle sur $`(0,K)`$.

Le NO au strike $`k`$ paie $`\mathbf{1}\lbrace S_T\lt k\rbrace`$. Son prix sous Black-Scholes est :


```math
\text{NO}(k)=N(-d_2(k)),\qquad d_2(k)=\frac{\ln(S/k)-\sigma^2T/2}{\sigma\sqrt T} \qquad(2)
```


Pour un put spread sur $`[K_{\min},K_{\max}]`$, (1) donne :


```math
(K_{\max}-S)^+-(K_{\min}-S)^+=\int_{K_{\min}}^{K_{\max}}\mathbf{1}\lbrace S\lt k\rbrace \ dk \qquad(3)
```


Strip : grille $`K_i=K_{\min}+i\ \Delta K`$, $`i=0,\dots,M`$, avec $`M=(K_{\max}-K_{\min})/\Delta K`$. On détient $`n_i=Q\ \Delta K`$ contrats NO au strike $`K_i`$ :


```math
\Pi_{\text{strip}}(S)=\sum_{i=0}^{M} Q\ \Delta K\ \mathbf{1}\lbrace S\lt K_i\rbrace \ \approx\ Q\big[(K_{\max}-S)^+-(K_{\min}-S)^+\big] \qquad(4)
```


Prix juste, avec $`r=0`$ : $`\sum_i Q\ \Delta K\ N(-d_2(K_i))\approx Q\ [P(K_{\max})-P(K_{\min})]`$, où $`P`$ est le put Black-Scholes.

**Erreur de discrétisation.** Pour un $`S`$ fixé, $`k\mapsto\mathbf{1}\lbrace S\lt k\rbrace`$ est monotone et bornée par 1. La somme de Riemann à pas $`\Delta K`$ diffère donc de l'intégrale d'au plus une cellule. Par scénario :


```math
\Big|\Pi_{\text{strip}}(S)-Q\big[(K_{\max}-S)^+-(K_{\min}-S)^+\big]\Big|\le Q\ \Delta K \qquad(5)
```


L'erreur est nulle si $`S`$ tombe exactement sur la grille (à la convention de bord près). Elle est bornée par $`\Delta K`$ par unité de $`Q`$, et non par $`\Delta K`$ multiplié par le nombre de strikes.

**Troncature : on réplique un put spread, pas un put.** Avec $`W=K_{\max}-K_{\min}`$ :

- Si $`S\le K_{\min}`$ : $`\Pi=Q\ W`$ (constante, pas de protection supplémentaire).
- Si $`K_{\min}\lt S\lt K_{\max}`$ : $`\Pi=Q\ (K_{\max}-S)`$.
- Si $`S\ge K_{\max}`$ : $`\Pi=0`$.

Le payoff est borné dans $`[0,QW]`$. Un put vanilla exigerait $`K_{\min}\to 0`$, donc une grille couvrant tout le bas de la distribution, ce que Kalshi ne liste pas. Avec $`K_{\min}\gt 0`$, l'écart par rapport à un put vanilla vaut $`Q\ (K_{\min}-S)^+\le Q\ K_{\min}`$, et il tombe dans la queue basse.

## 2. Binaire, call spread, gamma

Avec $`r=0`$, la parité put-call $`C-P=S-K`$ donne $`P(K+\varepsilon)-P(K)=C(K+\varepsilon)-C(K)+\varepsilon`$. D'où :


```math
\text{YES}(K)=\mathbf{1}\lbrace S\gt K\rbrace =\lim_{\varepsilon\to 0}\frac{C(K)-C(K+\varepsilon)}{\varepsilon},\qquad \text{NO}=1-\text{YES} \qquad(6)
```


Un YES est donc un call spread long, de largeur $`\varepsilon`$, pondéré par $`1/\varepsilon`$ (Hull, Taleb). Un NO est un put spread du même type, comme en (3).

Identité utile, avec $`r=0`$ : $`S\ \varphi(d_1)=K\ \varphi(d_2)`$. Elle découle de $`d_1+d_2=2\ln(S/K)/(\sigma\sqrt T)`$.

Gamma de $`\text{YES}`$, tel que codé dans `math_engine.py` :


```math
\Gamma_{\text{YES}}=-\frac{\varphi(d_2)\ d_1}{S^2\sigma^2T}=-\frac{d_1\varphi(d_1)}{K S\sigma^2T}
```


Le signe est inversé pour le NO : $`\Gamma_{\text{NO}}=+\varphi(d_2)d_1/(S^2\sigma^2T)`$. Le gamma du binaire unique est en $`1/(S^2\sigma^2T)`$. Près du strike quand $`T\to 0`$, il diverge en $`1/T`$.

Gamma du strip, obtenu à partir de (3) et de la section 3 :


```math
\Gamma_{\text{strip}}=\frac{Q}{S\sigma\sqrt T}\big[\varphi(d_1(K_{\max}))-\varphi(d_1(K_{\min}))\big]
```


C'est exactement le gamma d'un put spread vanilla, multiplié par $`Q`$. Il est borné : $`|\Gamma_{\text{strip}}|\le 0{,}4\ Q/(S\sigma\sqrt T)`$. Il ne diverge qu'en $`1/\sqrt T`$, comme un vanilla, et il est étalé sur la grille au lieu de se concentrer sur un strike.

## 3. Delta

Par contrat : $`\Delta_{\text{NO}}(K)=-\varphi(d_2(K))/(S\sigma\sqrt T)`$.

Strip :


```math
\Delta_{\text{total}}=\sum_i n_i\ \Delta_{\text{NO}}(K_i)=-Q\ \Delta K\sum_i\frac{\varphi(d_2(K_i))}{S\sigma\sqrt T}
```


Limite continue quand $`\Delta K\to 0`$ :


```math
\Delta_{\text{total}}\to -Q\int_{K_{\min}}^{K_{\max}}\frac{\varphi(d_2(k))}{S\sigma\sqrt T}\ dk
```


Avec $`\partial d_1/\partial k=-1/(k\sigma\sqrt T)`$ et $`\varphi(d_2)=(S/k)\varphi(d_1)`$ :


```math
\int_{K_{\min}}^{K_{\max}}\frac{\varphi(d_2(k))}{S\sigma\sqrt T}\ dk=\int_{d_1(K_{\max})}^{d_1(K_{\min})}\varphi(v)\ dv=N(d_1(K_{\min}))-N(d_1(K_{\max}))
```


Donc :


```math
\boxed{\ \Delta_{\text{total}}\to Q\big[N(d_1(K_{\max}))-N(d_1(K_{\min}))\big]\ }
```


Vérification : le delta BS d'un put est $`-N(-d_1)=N(d_1)-1`$. Le delta du put spread long $`P(K_{\max})-P(K_{\min})`$ est donc $`N(d_1(K_{\max}))-N(d_1(K_{\min}))`$. Il coïncide avec la limite ci-dessus.

Signe et bornes : $`d_1`$ décroît en $`K`$, donc $`N(d_1(K_{\max}))\lt N(d_1(K_{\min}))`$. D'où $`\Delta_{\text{total}}\in(-Q,0)`$, négatif comme un long NO. Pour $`K_{\min}\to 0`$ et $`K_{\max}\to\infty`$, $`\Delta\to -Q`$.

Conséquence pour la couverture : la perp à détenir vaut $`h=-\Delta_{\text{total}}`$ en BTC, soit $`h=Q\big[N(d_1(K_{\min}))-N(d_1(K_{\max}))\big]`$. Le backtest prend déjà $`h=-\Delta_{\text{NO}}\cdot`$ contrats pour le strike unique ; la même convention s'applique au strip.

## 4. Limites

- À prix justes, $`E_{\mathbb Q}[\Pi_{\text{strip}}]=Q[P(K_{\max})-P(K_{\min})]`$. Le strike unique a la même espérance. Le strip change la distribution du PnL couvert, pas son espérance. Les frais en retirent une partie.
- Frais Kalshi : $`\lceil 0{,}07\cdot C\cdot P(1-P)\rceil`$ au cent supérieur, par ordre. Un strip de $`M`$ ordres paie au moins $`M`$ arrondis. Le coût est donc plus élevé qu'un ordre unique.
- Spread bid-ask : un strip traverse $`M`$ spreads au lieu d'un.
- Une seule journée ne permet aucune conclusion statistique. L'erreur-type de la moyenne journalière est $`\sigma_{\text{PnL}}/\sqrt n`$ ; avec $`n=1`$, un résultat de −382 &#36; n'est pas informatif sur l'espérance.
- Le choix de poids non uniformes au-delà du pas constant est traité dans `strip_research_weights.md`. Ce document ne couvre que la réplication à pas constant.

## Sources

1. Carr, P. & Madan, D. (1998). « Towards a Theory of Volatility Trading ». In R. Jarrow (ed.), *Volatility: New Estimation Techniques for Pricing Derivatives*, Risk Books, pp. 417-427. Titre et pages relevés dans des références secondaires.
2. Breeden, D. T. & Litzenberger, R. H. (1978). « Prices of State-Contingent Claims Implicit in Option Prices ». *Journal of Business*, 51(4), 621-651. DOI 10.1086/296025.
3. Black, F. & Scholes, M. (1973). « The Pricing of Options and Corporate Liabilities ». *Journal of Political Economy*, 81(3), 637-654. 
4. Hull, J. C., *Options, Futures and Other Derivatives* (édition courante), chapitre « Exotic Options », section sur les binaires.
5. Taleb, N. N. (1997). *Dynamic Hedging: Managing Vanilla and Exotic Options*, Wiley. Voir les entrées « binary options » et « call spread » de l'index.
6. Carr, Ellis & Gupta (1998), *Journal of Finance*, 53(3), 1165-1190 : article distinct du précédent au titre voisin, à ne pas confondre.
