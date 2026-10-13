# Exécution optimale FX : coût d'un ordre de 50 M EUR sous impact supposé, et agrégation de liquidité simulée

Simulation du coût d'exécution d'un ordre de 50 M EUR d'EURUSD (Almgren-Chriss, TWAP, VWAP, POV, IS) rejouée sur 3 366 jours réels dont 1 037 hors échantillon, **sous un impact de marché supposé** (le paramètre η et la taille du pool de liquidité sont hypothétiques), puis d'un agrégateur de liquidité à **8 fournisseurs fictifs** avec *last look*.

- **What:** cost/risk frontier of a 50 M EUR EURUSD order (Almgren-Chriss, TWAP, VWAP, POV, IS) replayed on real 1-minute data (TRAIN 2010-2018 in-sample, VAL 2019-2022 out-of-sample, 2023+ never opened), plus a liquidity-aggregator simulator with last look.
- **Read first:** market impact (η = 10 bps at 100 % participation, 5 bn EUR/day accessible pool) is *assumed*, not estimated, so absolute bps are indicative; only price risk, the ranking of strategies and the shape of the frontier are empirical. The 8 liquidity providers are *fictitious*. A cost simulation, not a TCA on real fills.
- **Run:** `pip install -r requirements.txt && python -m pytest -q` (no market data needed); the full replay needs free HistData files, see « Obtenir les données ».

[![tests](https://github.com/yassine-ek/fx-optimal-execution-tca/actions/workflows/tests.yml/badge.svg)](https://github.com/yassine-ek/fx-optimal-execution-tca/actions/workflows/tests.yml) ![python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue) ![licence](https://img.shields.io/badge/licence-MIT-lightgrey)

## Résultats clés

<!-- AUTO:CLES -->
- **Frontière coût / risque retrouvée sur 1 037 jours hors échantillon (VAL 2019-2022).** TWAP : 2,59 bps, écart-type 8,26 ; Almgren-Chriss λ=0,05 : 5,16 bps, écart-type 4,81, soit un risque de prix divisé par 1,7 pour un coût multiplié par 2,0. *Réserve : l'impact (η) et la taille du pool de liquidité sont des hypothèses, donc ces niveaux en bps sont **indicatifs** ; seuls le classement des stratégies (corrélation de rang TRAIN → VAL : 1,00 en impact linéaire, 0,96 en racine carrée) et la forme de la frontière sont robustes. Pour situer : en pratique, un ordre de 50 M EUR coûte de l'ordre de quelques dixièmes de bp à quelques bps selon l'heure (ordre de grandeur qualitatif, non estimé ici).*
- **Le coût réalisé dépasse la théorie de 35 % en VAL, et c'est le proxy de volume qui l'explique.** Le FX n'a pas de volume centralisé : le « volume » simulé suit l'activité de prix du jour m, l'impact varie en 1/m et la moyenne de 1/m dépasse 1/(moyenne de m) (E[1/m] = 1,43 en VAL). Le coût TWAP réalisé se reconstruit à partir de la théorie : 1,568 × 1,431 + 0,346 = 2,590 bps contre 2,590 mesurés. *Réserve : c'est une propriété du modèle de volume, pas une observation de marché.*
- **Agrégateur de 8 fournisseurs de liquidité FICTIFS avec last look : le prix obtenu est plus cher que le meilleur prix affiché de 0,04 à 0,06 pip, et 15 % à 41 % des ordres subissent au moins un rejet.** *Réserve : les paramètres des 8 LP sont inventés, l'écart est donc un paramètre d'entrée et non un résultat ; seule la mécanique (cote périmée + last look, écart croissant avec la toxicité du flux) est démontrée.*
<!-- /AUTO:CLES -->

<p align="center"><img src="figures/hero_equity.png" width="720" alt="Coût cumulé d'exécution sur VAL 2019-2022 pour chaque stratégie, TWAP en référence (impact supposé)"></p>

*Coût cumulé d'exécution sur VAL (un achat et une vente de 50 M EUR par jour, impact linéaire supposé) : plus la courbe monte vite, plus l'exécution coûte ; TWAP, en noir, est la référence. Les courbes les plus chères sont celles qui réduisent le plus le risque : cette contrepartie se lit dans la frontière coût / risque.*

**Liens :** [tableau de bord interactif](https://yassine-ek.github.io/fx-optimal-execution-tca/) · [notebook : visite guidée](notebooks/visite_guidee.ipynb) · [détails : méthode, loi racine carrée, résultats, limites](docs/details.md)

## Frais et hypothèses (à lire avant les chiffres)

<!-- AUTO:FRAIS -->
| Hypothèse | Valeur |
|---|---|
| Ordre | 50 M EUR d'EURUSD, **un achat ET une vente rejoués chaque jour**, 60 tranches d'une minute, fenêtre 8h-9h New York, prix d'arrivée = clôture de 7h59, la tranche k ne voit que le passé |
| Impact **supposé** | temporaire linéaire η = 10 bps à 100 % de participation (modèle principal) ; racine carrée **appliquée par tranche d'une minute** (impact transitoire à décroissance complète, pas la loi de l'ordre parent), y = 1,557, calibrée sur le linéaire ; permanent 0,5 bp ; sensibilités ×0,5 et ×2. **Aucun fill réel : niveaux absolus indicatifs** |
| Liquidité **supposée** | pool accessible de 5 Md EUR par jour (le marché fait environ 1 000 Md), participation TWAP nominale 14,9 % ; volume d'une minute = pool × profil × activité de prix du jour (**proxy** : la colonne volume vaut 0) |
| Coûts | demi-spread 0,1 bp constant (supposé, barres BID) + impact ci-dessus ; agrégateur : **8 fournisseurs fictifs** avec rejets simulés |
| Données et découpage | HistData EURUSD 1 min, prix BID, heure de New York · **TRAIN** 2010-2018 (profil et paramètres Almgren-Chriss calibrés ici : in-sample) · **VAL** 2019-2022 (1 037 jours, hors échantillon) · **TEST 2023+ scellé** |
| Statistiques | shortfall en bps du notionnel (positif = on paie), achat et vente moyennés, IC95 par bootstrap en blocs de 5 jours ; 28 variantes toutes publiées, aucune choisie sur VAL (pas de DSR) |
<!-- /AUTO:FRAIS -->

Toutes les hypothèses, la loi racine carrée (appliquée par tranche, pas à l'ordre parent) et les limites : [docs/details.md](docs/details.md).

## Métriques : coût et risque par stratégie, impact linéaire, TRAIN | VAL

<!-- AUTO:TETE -->
| Stratégie | Coût moyen TRAIN | Coût moyen VAL [IC95] | Écart-type TRAIN | Écart-type VAL | p95 VAL | Coût total VAL (M EUR) |
|---|---|---|---|---|---|---|
| TWAP | 2,19 | 2,59 [2,49 ; 2,69] | 10,01 | 8,26 | 13,8 | 26,9 |
| VWAP-proxy | 2,09 | 2,47 [2,37 ; 2,57] | 10,65 | 8,86 | 14,4 | 25,6 |
| Almgren-Chriss λ=0,01 | 2,54 | 3,02 [2,90 ; 3,14] | 8,25 | 6,76 | 12,5 | 31,3 |
| Almgren-Chriss λ=0,05 | 4,30 | 5,16 [4,94 ; 5,38] | 5,82 | 4,81 | 11,8 | 53,5 |
| Almgren-Chriss λ=0,3 | 9,78 | 11,82 [11,29 ; 12,34] | 5,32 | 5,30 | 20,5 | 122,5 |
| IS front-loaded | 3,23 | 3,85 [3,69 ; 4,01] | 7,87 | 6,43 | 12,3 | 39,9 |
| POV-proxy | 2,29 | 2,65 [2,57 ; 2,74] | 8,98 | 7,58 | 13,5 | 27,5 |

*Shortfall en bps du notionnel (positif = coût), achats et ventes poolés ; l'écart-type est celui d'un seul ordre ; coût total VAL en M EUR pour un achat et une vente de 50 M EUR par jour. L'impact étant supposé, **lire le classement et la forme coût / risque, pas les niveaux absolus**. Tableaux complets (IC95 de l'écart à TWAP, p95 TRAIN, impact racine carrée) juste dessous.*
<!-- /AUTO:TETE -->

<!-- AUTO:TABLES -->
<details>
<summary>Tableaux complets (9 colonnes) : impact linéaire et impact racine carrée par tranche</summary>

### Coût d'exécution par stratégie, impact linéaire, TRAIN | VAL côte à côte

| Stratégie | Shortfall moyen TRAIN [IC95] | Shortfall moyen VAL [IC95] | Écart-type TRAIN | Écart-type VAL | p95 TRAIN | p95 VAL | Coût total VAL (M EUR) | Δ vs TWAP VAL [IC95] |
|---|---|---|---|---|---|---|---|---|
| TWAP | 2,19 [2,14 ; 2,24] | 2,59 [2,49 ; 2,69] | 10,01 | 8,26 | 16,5 | 13,8 | 26,9 | référence |
| VWAP-proxy | 2,09 [2,05 ; 2,14] | 2,47 [2,37 ; 2,57] | 10,65 | 8,86 | 17,4 | 14,4 | 25,6 | −0,12 [−0,12 ; −0,11] |
| Almgren-Chriss λ=0,01 | 2,54 [2,48 ; 2,61] | 3,02 [2,90 ; 3,14] | 8,25 | 6,76 | 14,1 | 12,5 | 31,3 | +0,43 [+0,41 ; +0,45] |
| Almgren-Chriss λ=0,05 | 4,30 [4,19 ; 4,42] | 5,16 [4,94 ; 5,38] | 5,82 | 4,81 | 12,0 | 11,8 | 53,5 | +2,57 [+2,45 ; +2,69] |
| Almgren-Chriss λ=0,3 | 9,78 [9,51 ; 10,05] | 11,82 [11,29 ; 12,34] | 5,32 | 5,30 | 17,8 | 20,5 | 122,5 | +9,23 [+8,80 ; +9,65] |
| IS front-loaded | 3,23 [3,15 ; 3,31] | 3,85 [3,69 ; 4,01] | 7,87 | 6,43 | 13,9 | 12,3 | 39,9 | +1,26 [+1,20 ; +1,32] |
| POV-proxy | 2,29 [2,25 ; 2,34] | 2,65 [2,57 ; 2,74] | 8,98 | 7,58 | 15,6 | 13,5 | 27,5 | +0,06 [+0,04 ; +0,08] |

### Coût d'exécution par stratégie, impact racine carrée, TRAIN | VAL côte à côte

| Stratégie | Shortfall moyen TRAIN [IC95] | Shortfall moyen VAL [IC95] | Écart-type TRAIN | Écart-type VAL | p95 TRAIN | p95 VAL | Coût total VAL (M EUR) | Δ vs TWAP VAL [IC95] |
|---|---|---|---|---|---|---|---|---|
| TWAP | 1,90 [1,88 ; 1,92] | 2,06 [2,02 ; 2,10] | 9,99 | 8,22 | 16,5 | 13,6 | 21,3 | référence |
| VWAP-proxy | 2,11 [2,08 ; 2,13] | 2,29 [2,24 ; 2,33] | 10,63 | 8,83 | 17,6 | 14,4 | 23,7 | +0,23 [+0,23 ; +0,24] |
| Almgren-Chriss λ=0,01 | 1,90 [1,87 ; 1,92] | 2,05 [2,01 ; 2,09] | 8,21 | 6,69 | 13,8 | 11,8 | 21,3 | −0,002 [−0,002 ; −0,002] |
| Almgren-Chriss λ=0,05 | 2,17 [2,15 ; 2,20] | 2,36 [2,31 ; 2,41] | 5,59 | 4,43 | 10,1 | 9,1 | 24,5 | +0,30 [+0,30 ; +0,31] |
| Almgren-Chriss λ=0,3 | 3,14 [3,10 ; 3,18] | 3,42 [3,35 ; 3,50] | 3,61 | 2,74 | 7,8 | 7,5 | 35,5 | +1,37 [+1,33 ; +1,40] |
| IS front-loaded | 1,99 [1,97 ; 2,01] | 2,16 [2,12 ; 2,20] | 7,78 | 6,29 | 13,2 | 11,2 | 22,4 | +0,10 [+0,10 ; +0,11] |
| POV-proxy | 2,12 [2,11 ; 2,13] | 2,22 [2,20 ; 2,25] | 8,96 | 7,54 | 15,5 | 13,3 | 23,0 | +0,16 [+0,15 ; +0,18] |

*Les IC95 (bootstrap par blocs de 5 jours) ne mesurent que la variabilité d'échantillonnage des jours, pas l'incertitude sur le modèle d'impact, qui est supposé. Comparer deux coûts moyens est circulaire (TWAP est Almgren-Chriss à λ → 0, donc tout λ > 0 coûte plus cher en moyenne) : l'information est la frontière coût / risque.*

</details>
<!-- /AUTO:TABLES -->

## Overfit ou pas ? Lecture en 30 secondes

<!-- AUTO:ROBUSTE -->
1. **La théorie calibrée sur TRAIN se trompe dans les deux sens hors échantillon, et l'écart de coût vient du proxy de volume.** TWAP : coût théorique 1,91 bps et écart-type 10,4 ; réalisé en TRAIN (in-sample) 2,19 et 10,0 ; réalisé en VAL 2,59 et 8,3. Le coût est 35 % au-dessus de la théorie en VAL (déjà 14 % en TRAIN) et le risque 21 % en dessous. *Attribution du coût :* le FX n'a pas de volume centralisé, le « volume » simulé est donc proportionnel à l'activité de prix du jour m et l'impact varie en 1/m. La moyenne de 1/m dépasse l'inverse de la moyenne de m que la théorie suppose (inégalité de Jensen : E[1/m] = 1,18 en TRAIN pour une activité moyenne de 1,00, 1,43 en VAL pour 0,84). Cela suffit : impact temporaire théorique 1,568 × E[1/m] + 0,346 (demi-spread et impact permanent) = 2,590 bps en VAL pour 2,590 mesurés (2,191 contre 2,191 en TRAIN). L'écart est donc une **conséquence du modèle de volume**, pas une observation de marché. *Attribution du risque :* VAL est plus calme (σ de fenêtre 2,18 contre 2,68 bps/min), donc moins de risque de prix.
2. **Le classement, lui, tient.** Corrélation de rang (Spearman) des 7 coûts moyens TRAIN / VAL : 1,00 en impact linéaire, 0,96 en racine carrée ; le coût VAL vaut 1,15 à 1,21 fois le coût TRAIN selon la stratégie (linéaire). Les gagnants par aversion au risque (utilité E + λ·Var) sont les mêmes en TRAIN et en VAL : pour λ = 0,01 / 0,05 / 0,3, POV-proxy / Almgren-Chriss λ=0,01 / Almgren-Chriss λ=0,05 (l'optimum du modèle serait Almgren-Chriss λ=0,01 / Almgren-Chriss λ=0,05 / Almgren-Chriss λ=0,3).
3. **Choisi avant de lire VAL : les paramètres.** Taille, fenêtre, modèles d'impact et leurs paramètres, valeurs de λ, stratégies sont des constantes du code (`execfx/impact.py`, `execfx/experiences.py`), aucune n'a été ajustée pour améliorer un résultat VAL (une seule exécution de référence) ; la seule modification venue après un premier calcul est la correction du fuseau du 13/10 (elle déplace la fenêtre, pas les paramètres). Les 28 variantes sont toutes publiées, aucune n'est retenue sur son résultat VAL, TEST scellé. Le vrai point faible n'est pas un surajustement mais l'**impact supposé** : AC λ=0,3 coûte 11,82 bps en linéaire et 3,42 en racine carrée, et la frontière coût / risque empirique se replie : AC λ=0,3 est plus risquée (5,30) qu'AC λ=0,05 (4,81) car l'impact varie d'un jour à l'autre, ce que la théorie ignore.

| Stratégie (impact linéaire) | Coût théorique | Réalisé TRAIN | Réalisé VAL | Écart-type théorique | Écart-type TRAIN | Écart-type VAL |
|---|---|---|---|---|---|---|
| TWAP | 1,91 | 2,19 | 2,59 | 10,40 | 10,01 | 8,26 |
| VWAP-proxy | 1,83 | 2,09 | 2,47 | 11,11 | 10,65 | 8,86 |
| Almgren-Chriss λ=0,01 | 2,21 | 2,54 | 3,02 | 8,51 | 8,25 | 6,76 |
| Almgren-Chriss λ=0,05 | 3,71 | 4,30 | 5,16 | 5,70 | 5,82 | 4,81 |
| Almgren-Chriss λ=0,3 | 8,36 | 9,78 | 11,82 | 3,50 | 5,32 | 5,30 |
| IS front-loaded | 2,79 | 3,23 | 3,85 | 8,01 | 7,87 | 6,43 |
| POV-proxy | n/d (adaptative) | 2,29 | 2,65 | n/d | 8,98 | 7,58 |

*bps du notionnel. La théorie (formules d'Almgren-Chriss avec les σ et θ du TRAIN, activité du jour = 1) n'existe que pour les plannings statiques ; POV s'adapte à l'activité observée.*
<!-- /AUTO:ROBUSTE -->

## Toutes les variantes

Rien n'est caché : 7 stratégies × 4 modèles d'impact (linéaire, racine carrée par tranche, linéaire ×0,5 et ×2), TRAIN et VAL, **y compris les cas où la théorie se trompe**. Aucune n'est retenue sur son résultat VAL.

![Coût cumulé d'exécution des 28 variantes, TRAIN grisé, VAL à droite](figures/toutes_variantes.png)

**Comment lire ce graphique.** Chaque ligne grise est le coût cumulé d'une des 28 variantes, sur TRAIN (zone grisée, in-sample) puis sur VAL (hors échantillon) ; les lignes de couleur sont les 7 stratégies en impact linéaire, TWAP en noir gras. Le modèle d'impact choisi (l'écart entre lignes de même couleur) déplace davantage le coût que le choix entre TWAP, VWAP-proxy et POV.

![Coût moyen TRAIN contre VAL, et théorie contre réalisé](figures/overfit_scatter.png)

**Comment lire ce graphique.** À gauche, un point par variante : coût moyen TRAIN en abscisse, VAL en ordonnée (échelles log) ; au-dessus de la diagonale, l'exécution coûte plus cher hors échantillon. À droite, pour les stratégies statiques en impact linéaire, le coût annoncé par la théorie d'Almgren-Chriss contre le coût réalisé (ronds vides en TRAIN, ronds pleins en VAL) : une théorie juste aurait tous les points sur la diagonale. L'écart est expliqué plus haut : c'est le proxy de volume.

<details>
<summary>Tableau des 28 variantes (9 colonnes)</summary>

<!-- AUTO:VARIANTES -->
| Variante | Impact | Shortfall moyen TRAIN | Shortfall moyen VAL | Écart-type TRAIN | Écart-type VAL | p95 VAL | Coût total VAL (M EUR) | Rapport VAL / TRAIN |
|---|---|---|---|---|---|---|---|---|
| **TWAP·lin** | linéaire | 2,19 | 2,59 | 10,01 | 8,26 | 13,8 | 26,9 | 1,18 |
| VWAP·lin | linéaire | 2,09 | 2,47 | 10,65 | 8,86 | 14,4 | 25,6 | 1,18 |
| AC1·lin | linéaire | 2,54 | 3,02 | 8,25 | 6,76 | 12,5 | 31,3 | 1,19 |
| AC2·lin | linéaire | 4,30 | 5,16 | 5,82 | 4,81 | 11,8 | 53,5 | 1,20 |
| AC3·lin | linéaire | 9,78 | 11,82 | 5,32 | 5,30 | 20,5 | 122,5 | 1,21 |
| IS·lin | linéaire | 3,23 | 3,85 | 7,87 | 6,43 | 12,3 | 39,9 | 1,19 |
| POV·lin | linéaire | 2,29 | 2,65 | 8,98 | 7,58 | 13,5 | 27,5 | 1,15 |
| TWAP·rac | racine carrée | 1,90 | 2,06 | 9,99 | 8,22 | 13,6 | 21,3 | 1,08 |
| VWAP·rac | racine carrée | 2,11 | 2,29 | 10,63 | 8,83 | 14,4 | 23,7 | 1,09 |
| AC1·rac | racine carrée | 1,90 | 2,05 | 8,21 | 6,69 | 11,8 | 21,3 | 1,08 |
| AC2·rac | racine carrée | 2,17 | 2,36 | 5,59 | 4,43 | 9,1 | 24,5 | 1,09 |
| AC3·rac | racine carrée | 3,14 | 3,42 | 3,61 | 2,74 | 7,5 | 35,5 | 1,09 |
| IS·rac | racine carrée | 1,99 | 2,16 | 7,78 | 6,29 | 11,2 | 22,4 | 1,08 |
| POV·rac | racine carrée | 2,12 | 2,22 | 8,96 | 7,54 | 13,3 | 23,0 | 1,05 |
| TWAP·lin×0,5 | linéaire ×0,5 | 1,15 | 1,34 | 9,99 | 8,23 | 12,8 | 13,9 | 1,17 |
| VWAP·lin×0,5 | linéaire ×0,5 | 1,10 | 1,29 | 10,63 | 8,83 | 13,4 | 13,3 | 1,17 |
| AC1·lin×0,5 | linéaire ×0,5 | 1,56 | 1,84 | 7,15 | 5,79 | 10,3 | 19,1 | 1,19 |
| AC2·lin×0,5 | linéaire ×0,5 | 3,00 | 3,60 | 4,76 | 3,82 | 9,1 | 37,4 | 1,20 |
| AC3·lin×0,5 | linéaire ×0,5 | 6,73 | 8,14 | 4,08 | 3,87 | 14,3 | 84,4 | 1,21 |
| IS·lin×0,5 | linéaire ×0,5 | 1,66 | 1,98 | 7,80 | 6,32 | 10,9 | 20,5 | 1,19 |
| POV·lin×0,5 | linéaire ×0,5 | 1,20 | 1,38 | 8,96 | 7,55 | 12,4 | 14,3 | 1,15 |
| TWAP·lin×2 | linéaire ×2 | 4,28 | 5,08 | 10,10 | 8,41 | 15,9 | 52,7 | 1,19 |
| VWAP·lin×2 | linéaire ×2 | 4,09 | 4,84 | 10,73 | 8,98 | 16,1 | 50,2 | 1,18 |
| AC1·lin×2 | linéaire ×2 | 4,57 | 5,43 | 9,12 | 7,59 | 15,0 | 56,3 | 1,19 |
| AC2·lin×2 | linéaire ×2 | 6,39 | 7,65 | 7,17 | 6,11 | 16,0 | 79,3 | 1,20 |
| AC3·lin×2 | linéaire ×2 | 14,14 | 17,07 | 7,06 | 7,31 | 29,4 | 177,1 | 1,21 |
| IS·lin×2 | linéaire ×2 | 6,35 | 7,60 | 8,14 | 6,87 | 16,5 | 78,8 | 1,20 |
| POV·lin×2 | linéaire ×2 | 4,49 | 5,20 | 9,05 | 7,70 | 15,7 | 53,9 | 1,16 |

*bps du notionnel, sauf le coût total (M EUR). TWAP en impact linéaire (en gras) est la référence. Colonnes « Impact » : linéaire = modèle principal, racine carrée = calibrée dessus, ×0,5 et ×2 = impacts linéaires multipliés.*
<!-- /AUTO:VARIANTES -->

</details>

## Tableau de bord interactif

Choisissez les conditions de départ (modèle d'impact, famille de stratégie, coût moyen TRAIN maximal, écart-type TRAIN maximal) : seules les variantes qui passent ces filtres sur **TRAIN** sont combinées (moyenne équipondérée) et leur coût cumulé est affiché sur TRAIN puis VAL.

- En ligne : <https://yassine-ek.github.io/fx-optimal-execution-tca/> ; ou ouvrir `docs/index.html` localement (données dans `docs/data.js`, aucun serveur nécessaire).
- Régénérer : `python scripts/exporter_dashboard.py` (lit `results/`, aucune donnée de marché requise). Le mode d'emploi détaillé est dans [docs/details.md](docs/details.md#comment-lire-le-tableau-de-bord).

## Limites

- **Impact et liquidité supposés, aucun fill réel** : les niveaux absolus en bps sont indicatifs ; seuls le risque de prix, le classement et la forme de la frontière viennent des données.
- **Pas de volume FX** : l'activité de prix sert de proxy, et l'écart théorie / réalisé en est une conséquence (voir « Overfit ou pas ? »).
- **Loi racine carrée appliquée par tranche d'une minute**, pas à l'ordre parent : c'est un impact temporaire concave calibré sur le linéaire, pas un second modèle indépendant ; le planning Almgren-Chriss reste dérivé sous impact linéaire ([détails](docs/details.md#loi-racine-carrée--par-tranche-pas-par-ordre-parent)).
- **8 fournisseurs de liquidité fictifs** : la mécanique (cote périmée + last look) est le résultat, pas les niveaux en pips.
- **Le rejeu TRAIN est in-sample** (profil, σ, θ, planning VWAP) ; seul VAL est hors échantillon ; TEST 2023+ scellé, une seule exécution de référence, aucun réglage sur VAL.
- **Barres 1 minute BID** : pas de carnet, demi-spread constant supposé, pas de latence sous la minute dans le simulateur de coûts ; fenêtre unique 8h-9h New York, une seule paire.

## Comment ce projet a été construit

Projet réalisé en octobre 2026 avec un assistant de programmation IA (Claude, Anthropic) que j'ai dirigé : choix des sujets, protocole, vérification des résultats. Tous les chiffres sont régénérés par les scripts du dépôt et contrôlés par les tests et la CI.

## Reproduire

```bash
pip install -r requirements.txt
python -m pytest -q                        # sans données de marché : les tests qui lisent HistData sont sautés

# Avec les minutes EURUSD HistData (non redistribuées, voir « Obtenir les données ») :
export HISTDATA_DIR=/chemin/vers/les/donnees      # PowerShell : $env:HISTDATA_DIR = "D:\chemin\vers\les\donnees"
python scripts/run_all.py                  # ~20 s : results/verdict_execution.json + 5 figures
python scripts/rejeu_cout_quotidien.py     # ~1 min : results/couts_quotidiens.csv + results/variantes_train_val.json
python scripts/exporter_dashboard.py       # docs/ (tableau de bord) ; sans données de marché
python scripts/generer_figures_vitrine.py  # hero_equity, toutes_variantes, overfit_scatter ; sans données de marché
python scripts/generer_readme_tete.py      # réécrit les blocs de chiffres du README et de docs/details.md ; sans données de marché
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/visite_guidee.ipynb   # facultatif
```

### Obtenir les données

Les minutes EURUSD ne sont pas redistribuées avec le dépôt. Elles sont téléchargeables gratuitement, à la main, sur <https://www.histdata.com> : EURUSD, barres 1 minute (M1), format MetaTrader, un zip par année de 2010 à 2022. Renommer chaque zip en `EURUSD_AAAA.zip` (le CSV à l'intérieur doit s'appeler `DAT_MT_EURUSD_M1_AAAA.csv`) et les ranger ainsi :

```
<HISTDATA_DIR>/histdata_raw/EURUSD/EURUSD_2010.zip   ...   EURUSD_2022.zip
```

Définir `HISTDATA_DIR` (sinon `data/histdata/` à la racine du dépôt est essayé, ignoré par git ; l'ancienne variable `EXECFX_DONNEES`, dossier des zips lui-même, reste acceptée). Le TEST (2023+) n'est jamais lu : `donnees.charger_annee` refuse l'année. Sans données, les scripts qui lisent le marché s'arrêtent avec ce même mode d'emploi, sans trace d'erreur brute.

## Structure du dépôt

```
.
├── README.md  LICENSE  requirements.txt  pytest.ini  .gitignore  .gitattributes
├── .github/workflows/tests.yml     intégration continue : Python 3.12, pytest -q
├── execfx/                         le package (nom évitant le mot-clé exec)
│   ├── donnees.py                  lecture HistData, heure de New York, TEST scellé, HISTDATA_DIR, message guidé
│   ├── profils.py                  profil d'activité par minute (proxy de volume), calibré TRAIN
│   ├── almgren_chriss.py           trajectoire x_j, espérance, variance, frontière, TWAP quand lambda -> 0
│   ├── impact.py                   hypothèses + impact linéaire / racine carrée par tranche / permanent
│   ├── tca.py                      stratégies, exécution sans look-ahead, shortfall, bootstrap par blocs
│   ├── agregation.py               8 LP fictifs, latence, last look, routeurs (a)(b)(c), coeur numba
│   └── experiences.py  figures.py  orchestration et figures (partagées avec le notebook)
├── tests/                          la suite pytest
├── scripts/                        run_all, rejeu_cout_quotidien, exporter_dashboard, figures et README de tête
├── notebooks/visite_guidee.ipynb   intuition -> formule -> attente -> code -> lecture (exécuté, 0 erreur)
├── figures/                        les images du README (dpi 130)
├── results/                        verdict_execution.json, variantes_train_val.json, couts_quotidiens.csv
└── docs/                           le tableau de bord interactif (GitHub Pages) et details.md
```

Un `README.md` dans chaque dossier décrit son rôle et chacun de ses fichiers.

## Licence

MIT, voir [`LICENSE`](LICENSE).
