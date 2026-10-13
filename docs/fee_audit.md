# Contrôle des frais sur le journal de run

Outil : `python -m risk.audit data/journal_<run>.jsonl [--final]`. Le code de sortie vaut 1 si un contrôle échoue. Avec `--final`, un contrôle qui ne peut pas être évalué compte comme un échec.

Barème de référence : `risk/fees.py`, sourcé dans [microstructure_review.md](microstructure_review.md).

## Résultat sur la session du 12/10/2026

Journal `data/journal_20261012_083715.jsonl` (11 352 lignes, de 08:37 à 10:04 UTC).

| # | Contrôle | Résultat |
|---|---|---|
| 1 | Frais recalculés par fill (tolérance 1e-9) | OK |
| 2 | Aucun fill taker à frais nul | OK |
| 3 | HL maker réservé à `static_hedge` | OK |
| 4 | Somme des fills = frais du dernier mark | OK |
| 5 | `pnl_total` = `pnl_pm + pnl_hl − fees_pm − fees_hl − funding` | OK |
| 6 | Frais cumulés monotones | OK |
| 7 | Aucun fill non-kill après un `kill_*` | OK (kill-switch jamais déclenché) |
| 8 | Premier `kill_*` ≥ expiry − 2 h | Non évaluable |
| 9 | Position à plat au dernier mark | Non évaluable |
| 10 | `kill_close_ms` présent | Non évaluable |

L'enregistrement s'arrête à 10:04 UTC. Le kill-switch se déclenche à T − 2 h, soit 14:00 UTC pour une échéance à 16:00 UTC (`expiry_ms` = 1791820800000). Les contrôles 8 à 10 n'ont donc rien à vérifier sur cette session.

| Stratégie | Fills | Frais PM | Frais HL | Prime payée | Frais / prime | Rebalancements dyn. | Notionnel HL |
|---|---|---|---|---|---|---|---|
| statique | 42 | 16,05133 $ | 5,70051 $ | 356,22 $ | 6,106 % | 0 | 38 003,37 $ |
| dynamique | 1 550 | 16,05133 $ | 181,43478 $ | 356,22 $ | 55,439 % | 1 548 | 403 188,39 $ |

Les frais Polymarket sont identiques dans les deux stratégies, puisque l'achat d'entrée est le même. L'écart vient des frais taker Hyperliquid de la couverture dynamique : 181,43 $, soit 55,4 % de la prime, contre 6,1 % pour la statique (frais seuls, hors spread et funding).

## Limites

- Les frais maker Polymarket sont fixés à 0. Le rebate maker (20 % des frais taker, distribué chaque jour) n'est pas modélisé.
- Le champ Gamma `takerBaseFee = 1000` n'est pas expliqué par les pages consultées. Il n'entre pas dans le calcul.
- Le contrôle 6 vérifie la monotonie des frais. Le signe du funding n'est pas contrôlé : le journal ne contient pas de taux de référence.
- La résolution du marché « Bitcoin above » n'est pas traitée ici.
