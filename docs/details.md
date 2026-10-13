# Détails : hypothèses, méthode, loi racine carrée, résultats, validation

Retour au [README](../README.md). Tous les chiffres des blocs ci-dessous sont lus dans `results/` par `scripts/generer_readme_tete.py` ; un test vérifie qu'ils sont à jour.

Sommaire : [Ce que ce projet démontre](#ce-que-ce-projet-démontre) · [Hypothèses détaillées](#hypothèses-détaillées) · [Le problème](#le-problème) · [Méthode](#méthode--intuition-formules-attente) · [Loi racine carrée](#loi-racine-carrée--par-tranche-pas-par-ordre-parent) · [Résultats détaillés](#résultats-détaillés) · [Agrégateur et SOR](#agrégateur-de-liquidité-et-routage-dordres-sor) · [Tableau de bord](#comment-lire-le-tableau-de-bord) · [Validation et tests](#validation-et-tests) · [Dépôts voisins](#pour-aller-plus-loin--dépôts-voisins)

## Ce que ce projet démontre

Métiers visés : market making, exécution, plateformes de trading FX. La question est toujours la même : *combien me coûte réellement cet ordre, et que dois-je changer pour payer moins ?* Ce dépôt la traite de bout en bout, avec une séparation nette entre ce qui vient du marché (réel) et ce qui vient du modèle (supposé) :

- **Algos d'exécution** : TWAP, VWAP-proxy, IS, POV et leur cadre commun Almgren-Chriss, avec un banc de comparaison honnête (même ordre, mêmes jours, IC appariés).
- **Smart order routing** : la section agrégateur pose la question centrale du SOR, classer par prix affiché ou par prix effectif ajusté du risque de rejet, avec des statistiques de rejet apprises sur le flux. Ici 8 fournisseurs fictifs et une seule dimension de risque (le rejet) ; un vrai routeur en gère bien plus (profondeur, délai de détention, détection de cotes périmées).
- **Méthode de best execution** : implementation shortfall contre le prix d'arrivée, incertitude par bootstrap en blocs, test anti look-ahead, analyse de sensibilité au modèle d'impact.

Ce que ce n'est pas : une TCA sur fills réels. La méthode (shortfall contre le prix d'arrivée) est celle d'une TCA, mais le coût d'impact est simulé sous un modèle supposé ; aucune donnée de transaction n'est utilisée.

## Hypothèses détaillées

<!-- AUTO:FRAIS_DETAIL -->
| Hypothèse | Valeur |
|---|---|
| Ordre | 50 M EUR d'EURUSD, **un achat ET une vente rejoués chaque jour**, 60 tranches d'une minute, fenêtre 8h00-9h00 heure de New York (les annonces US de 8h30 y sont), prix d'arrivée = clôture de 7h59 |
| Demi-spread | 0,1 bp du notionnel, constant et identique pour toutes les stratégies (**hypothèse** : les barres BID ne contiennent pas de spread réel) |
| Impact supposé | temporaire **linéaire** : 10 bps × participation (modèle principal) ; **racine carrée** : y·σ·√participation avec y = 1,557, calibré pour égaler le linéaire au TWAP nominal, **appliqué tranche par tranche (une minute)** : c'est un impact transitoire à décroissance complète, pas la loi de l'ordre parent (voir « Loi racine carrée » plus bas) ; permanent linéaire : 0,5 bp pour l'ordre complet. Sensibilités : impact ×0,5 et ×2. **Aucun impact n'est estimé sur des fills : les niveaux absolus en bps sont indicatifs** |
| Liquidité | 5 Md EUR par jour accessibles (hypothèse ; le marché fait environ 1 000 Md) donc participation TWAP nominale 14,9 % ; volume d'une minute = volume du jour × part de la minute (profil d'activité TRAIN) × activité réalisée du jour |
| Données | HistData EURUSD 1 minute, prix **BID** ; le FX est OTC, la colonne volume vaut 0 : l'activité de prix sert de proxy ; horloge = heure locale de New York (heure d'été comprise), vérifiée sur le NFP et l'ouverture hebdomadaire |
| Découpage | **TRAIN** 2010-2018 (2 329 jours utilisables sur 2 342 : profil, σ et θ d'Almgren-Chriss calibrés ici, donc le rejeu TRAIN est **in-sample**) · **VAL** 2019-2022 (1 037 jours sur 1 043 : évaluation hors échantillon) · **TEST 2023+ : scellé**, le chargeur refuse l'année |
| Délai d'exécution | la tranche k est décidée avec les clôtures jusqu'à la minute précédente (testé), exécutée au prix de la barre ; aucune latence sous la minute dans le simulateur de coûts (l'agrégateur, lui, simule la milliseconde) |
| Statistiques | shortfall en bps du notionnel, positif = on paie ; achat et vente moyennés (la dérive du prix s'annule : la moyenne mesure l'impact, l'écart-type le risque de prix) ; IC95 par bootstrap en blocs de 5 jours (1 000 tirages), mêmes blocs pour toutes les stratégies, donc variabilité d'échantillonnage des jours seulement, pas incertitude sur le modèle d'impact ; coût total en EUR = jours × (1 achat + 1 vente) × 50 M EUR × shortfall moyen |
| Essais | 28 variantes (7 stratégies × 4 modèles d'impact), toutes publiées, **aucune choisie sur VAL** : pas de DSR (rien à déflater) |
<!-- /AUTO:FRAIS_DETAIL -->

## Le problème

Acheter 50 M EUR d'EURUSD en une fois déplace le prix contre soi (**impact**). L'étaler dans le temps réduit l'impact mais expose au hasard du marché pendant plus longtemps (**risque**). Il n'existe pas de bonne réponse unique : il y a une **frontière efficiente** coût / risque, et le choix dépend de l'aversion au risque. Côté routage, un agrégateur qui voit 8 prix doit choisir où envoyer l'ordre : le meilleur prix *affiché* n'est pas forcément le meilleur prix *obtenu*, car certains fournisseurs peuvent rejeter l'ordre (last look) si le marché a bougé.

## Méthode : intuition, formules, attente

**Almgren-Chriss** (ordre parent = 1, tranches d'une minute, `n_k` = fraction négociée, `x_j` = reste). Intuition : plus on exécute vite, plus l'impact est fort ; plus on traîne, plus le prix a le temps de bouger. Formule : `E = eps + sum_k theta_k n_k^2 + gamma * sum_k n_k C_{k-1}` et `V = sigma^2 * sum_{j<N} x_j^2`. Minimiser `E + lambda*V` donne `x_j = sinh(kappa (T - t_j)) / sinh(kappa T)`, avec `cosh(kappa) = 1 + kappa~^2/2` (version discrète exacte ; en continu on retrouve `kappa^2 = lambda sigma^2 / eta`). Attente : `lambda -> 0` donne le TWAP, `lambda` grand exécute vite. Un test vérifie que cette trajectoire est bien l'optimum de `E + lambda V` (200 perturbations admissibles, aucune ne fait mieux).

**Profil de volume (proxy).** Le FX est OTC : aucun volume centralisé, la colonne volume vaut 0. On utilise le |rendement| moyen par minute de la journée (TRAIN) comme proxy, normalisé en part du jour. **Fuseau** : malgré leur documentation (« EST sans heure d'été »), les zips HistData sont à l'heure *locale* de New York, heure d'été comprise : le NFP (8h30 ET) fait le pic de la journée à 8h30 l'été comme l'hiver, la semaine rouvre le dimanche à 17h00 et ferme le vendredi à 16h59 en toute saison (en UTC-5 fixe on aurait 7h30, 16h00 et 15h59 l'été). Aucune conversion n'est donc appliquée et les pics d'annonces (8h30, 10h00) sont fins dans le profil (voir `figures/profil_intrajournalier.png` ; test de régression `test_fuseau_...` dans `tests/test_tca.py`). La fenêtre d'exécution est **8h00-9h00 heure de New York** (13h-14h UTC l'hiver, 12h-13h UTC l'été).

**Impact** (hypothèses, `execfx/impact.py`). Temporaire linéaire `slippage = eta * participation` ; racine carrée `slippage = y * sigma_minute * sqrt(participation)` calibrée pour coïncider avec le linéaire au TWAP nominal et appliquée **par tranche** (voir la section suivante) ; permanent linéaire. Le volume simulé d'une minute vaut `V_jour * part_de_la_minute * m`, où `m` est l'activité de prix réalisée du jour sur l'activité attendue (relation volume-volatilité, **proxy**) ; `m` n'est jamais visible des stratégies. Les paramètres sont dans l'encadré des hypothèses.

**Simulateur de coûts** (`execfx/tca.py`). Pour chaque jour, un achat et une vente de 50 M EUR dans la fenêtre, avec 7 stratégies : TWAP, VWAP-proxy (suit le profil d'activité), Almgren-Chriss (3 valeurs de λ : 0,01 / 0,05 / 0,3, soit une urgence κ·T d'environ 1,7 / 3,7 / 9,1), IS front-loaded (40 % de l'ordre en 10 minutes) et POV-proxy (suit l'activité observée, avec plancher TWAP sur le reste pour garantir la fin de l'ordre). Prix d'arrivée = clôture de 7h59. **Anti look-ahead** : à la tranche k la stratégie ne reçoit que les clôtures jusqu'à la minute précédente (`prix[: H+k+1]`) ; les tests changent le futur et vérifient que les décisions passées ne bougent pas, et que POV réagit bien à un changement du passé (le test a du pouvoir). Moyennée sur achat + vente, la dérive du prix disparaît : la moyenne du shortfall mesure l'impact (supposé), l'écart-type mesure le risque de prix réel. IC95 par bootstrap en blocs de 5 jours, mêmes blocs pour toutes les stratégies (différences appariées). Le rejeu TRAIN (`scripts/rejeu_cout_quotidien.py`) utilise exactement le même code que VAL.

**Agrégateur** (`execfx/agregation.py`). 8 LP **fictifs** cotant autour du mid réel : demi-spread propre, bruit, latence de la cote (âge), et last look (fenêtre, seuil en pips, probabilité de rejet = base + pente × toxicité). Volatilité sous-minute = volatilité réalisée causale (30 min) d'une minute tirée dans les données réelles. Routeurs : (a) meilleur prix affiché ; (b) coût attendu = prix + P(rejet) × coût de re-routage, avec P et le surcoût **appris sur TRAIN** (pas d'oracle) ; (c) split en 3 parts sur les 3 meilleurs de (b). Ordres de 20 M EUR, rejetés puis re-routés (3 tours max). Les 3 routeurs rejouent exactement les mêmes aléas.

| Paramètre | Valeur | Remarque |
|---|---|---|
| λ (Almgren-Chriss) | 0,01 / 0,05 / 0,3 | aversion au risque faible, moyenne, forte ; grille grossière fixée a priori |
| IS front-loaded | 40 % de l'ordre en 10 minutes | heuristique de comparaison, pas l'optimum |
| LP | 8 (3 last look agressifs, 2 modérés, 3 prix fermes) | paramètres **inventés** : voir `results/verdict_execution.json` > `agregation.lp` |
| Toxicité du flux | 0,1 / 0,5 / 0,9 | part de flux « toxique » (informé) perçue par les LP à last look |

## Loi racine carrée : par tranche, pas par ordre parent

**Ce que fait le code.** Le modèle « racine carrée » applique `slippage_k = y · σ_minute · √ρ_k` à **chaque tranche d'une minute**, avec `ρ_k = n_k X / V_k` la participation de cette minute. L'impact temporaire de chaque tranche s'éteint entièrement avant la suivante (impact transitoire à décroissance complète) ; seul l'impact permanent, linéaire, s'accumule d'une tranche à l'autre (`execfx/impact.py`, `cout_impact_bps`).

**Ce que dit la littérature.** La loi racine carrée de Bouchaud, Tóth et coauteurs vaut pour l'**ordre parent entier** (le métaordre) : coût ≈ Y · σ_jour · √(Q / V_jour), avec Y de l'ordre de l'unité. Appliquée tranche par tranche, c'est autre chose : un impact temporaire concave, comme celui estimé par Almgren, Thum, Hauptmann et Li (« Direct estimation of equity market impact », Risk, 2005) sur des actions américaines, dont l'exposant du terme temporaire était d'environ 0,6.

**Conséquences, à lire avant d'interpréter la variante « racine carrée ».**

1. Le coefficient y = 1,557 est calibré pour égaler le linéaire au TWAP nominal : la variante racine carrée est donc le **linéaire déformé** (concave), pas un second modèle indépendant. Que le classement des stratégies tienne sous les deux modèles (corrélation de rang TRAIN → VAL de 1,00 et 0,96) est rassurant, mais ne vaut pas confirmation par deux modèles distincts.
2. Le planning Almgren-Chriss reste **dérivé sous impact linéaire** : il n'est pas optimal sous l'impact concave. Que AC λ=0,3 coûte 3,4 bps en racine carrée contre 11,8 en linéaire mesure le risque de modèle, pas une meilleure stratégie.
3. **Variante « ordre parent » non ajoutée.** Elle n'est pas simple : la loi du métaordre donne un coût total fonction de Q / V_jour seulement, donc **le même coût pour tous les plannings** ; pour classer des plannings il faut en plus un noyau de décroissance de l'impact (modèle à propagateur), ce qui est un autre modèle avec d'autres paramètres supposés. L'ajouter changerait aussi les résultats publiés (nouvelles variantes dans `results/`, dans le tableau de bord et dans les tableaux). Piste de suite, non réalisée ici.

## Résultats détaillés

Tous les chiffres sont lus dans `results/` (VAL : 2019-2022, achat et vente poolés, IC95 par bootstrap en blocs).

<!-- AUTO:LECTURE -->
- **L'arbitrage d'Almgren-Chriss se retrouve sur données réelles, jusqu'à un point.** (Comparer les coûts moyens seuls est circulaire : TWAP est Almgren-Chriss à λ → 0 ; l'information est la frontière coût / risque.) Le coût moyen le plus bas est celui de VWAP-proxy (2,47 bps), le risque le plus bas celui de Almgren-Chriss λ=0,05 (écart-type 4,81, mais coût 5,16). De TWAP à AC λ=0,05 le risque baisse (8,26 → 4,81 bps) et le coût est multiplié par 2,0 (2,59 → 5,16). Plus loin (AC λ=0,3) le risque *remonte* (5,30) : l'écart-type du shortfall mêle le risque de prix (2,66 bps contre 3,50 en théorie) et la variabilité jour à jour de l'impact (4,58 bps, absente de la théorie car le volume du jour fluctue) ; le coût moyen explose (11,82).
- **VWAP-proxy : un peu moins cher que le TWAP, mais plus risqué.** Écart de coût moyen −0,118 bp, IC95 [−0,123 ; −0,112] (apparié, bootstrap par blocs), soit 1,4 % de l'écart-type du shortfall TWAP ; écart-type 8,86 contre 8,26. Il concentre l'ordre sur les minutes actives, dont 8h30 : moins d'impact là où le volume est fort, plus de risque là où σ est fort. Effet économiquement faible.
- **IS front-loaded : au-dessus de la frontière Almgren-Chriss.** Coût moyen 3,85, écart-type 6,43 ; une exécution Almgren-Chriss interpolée au même coût moyen aurait un écart-type d'environ 6,0. Le planning heuristique (40 % de l'ordre dans les 10 premières minutes) paie son urgence sans l'optimiser.
- **Le risque de modèle est le vrai sujet.** En impact racine carrée (appliqué par tranche d'une minute, voir « Loi racine carrée »), AC λ=0,3 coûte 3,42 bps au lieu de 11,82, le classement des risques change pour les stratégies les plus agressives (AC λ=0,3 : écart-type 2,74, la moins risquée) et les gagnants par λ deviennent Almgren-Chriss λ=0,01, Almgren-Chriss λ=0,05, Almgren-Chriss λ=0,3 (en linéaire : POV-proxy, Almgren-Chriss λ=0,01, Almgren-Chriss λ=0,05). Avec l'impact linéaire ×0,5 / ×2, le TWAP coûte 1,34 / 5,08 bps et AC λ=0,3 8,14 / 17,07. L'urgence optimale dépend donc du modèle d'impact, qu'on ne peut pas estimer sans données de fills ; le planning Almgren-Chriss restant dérivé sous impact linéaire, il est mal spécifié sous l'impact concave.
<!-- /AUTO:LECTURE -->

![Frontière efficiente coût / risque : théorie calibrée sur TRAIN contre trajectoires réelles VAL](../figures/frontiere_efficiente.png)

**Comment lire ce graphique.** Abscisse : le risque (écart-type du shortfall d'un ordre). Ordonnée : le coût moyen. La courbe grise est la frontière théorique d'Almgren-Chriss (σ et θ du TRAIN). Chaque couleur est une stratégie : le rond vide est le point que la théorie prédit pour ce planning, le rond plein avec ses barres (IC95) est ce qu'on mesure en VAL. Si la théorie était juste, les ronds pleins tomberaient sur les ronds vides, sur la courbe. Écart typique : le coût mesuré est au-dessus de la théorie (proxy de volume) et le risque en dessous (VAL plus calme) ; les points les plus agressifs se replient vers la droite au lieu de continuer à descendre, parce que la variance du coût d'impact (activité du jour aléatoire) s'ajoute au risque de prix, ce que la théorie à liquidité constante ignore.

![Trajectoires optimales d'Almgren-Chriss selon l'aversion au risque](../figures/trajectoires_ac.png)

**Comment lire ce graphique.** Fraction de l'ordre qui reste à exécuter au fil des minutes. Plus l'aversion au risque λ est grande, plus la courbe plonge tôt (on exécute vite pour se débarrasser du risque, au prix de l'impact) ; quand λ tend vers 0 on retrouve la droite du TWAP.

![Profil d'activité intrajournalier EURUSD et zoom sur la fenêtre d'exécution](../figures/profil_intrajournalier.png)

**Comment lire ce graphique.** À gauche, le |rendement| moyen d'une minute selon l'heure de New York (TRAIN) : c'est le proxy de volume. La bande orange est la fenêtre d'exécution. À droite, le zoom 8h00-9h00 : le pic à 8h30 est l'annonce des chiffres américains. Le VWAP-proxy et le simulateur de volume suivent cette courbe.

![Distribution du shortfall par stratégie](../figures/distributions_shortfall.png)

**Comment lire ce graphique.** Un violon par stratégie : la distribution du shortfall d'un ordre (achats et ventes), trait plein = moyenne, pointillé = p95. Un violon haut = coût élevé ; un violon étroit = peu de risque. Les stratégies pressées (Almgren-Chriss à λ élevé) montent et se resserrent, le TWAP reste bas et large.

## Agrégateur de liquidité et routage d'ordres (SOR)

Un agrégateur voit 8 prix, **tous fictifs**. Les LP les plus serrés ont des cotes un peu périmées et un *last look* : après réception de l'ordre, ils regardent le marché quelques millisecondes et rejettent si le prix a bougé contre eux. Un routeur qui envoie tout au meilleur prix affiché choisit donc par construction la cote la plus susceptible d'être rejetée. Trois routeurs sont comparés sur les mêmes aléas, pour trois niveaux de toxicité du flux.

<!-- AUTO:SOR -->
| Toxicité | Routeur | Meilleur prix affiché (pips) | Prix obtenu [IC95] (pips) | Rejets par ordre | Ordres avec rejet | Remplissage | Délai jusqu'au dernier fill (ms) |
|---|---|---|---|---|---|---|---|
| 0,1 | (a) meilleur prix affiché | −0,014 | +0,023 [+0,022 ; +0,024] | 0,18 | 15 % | 100,00 % | 198 |
| 0,1 | (b) prix effectif | −0,014 | +0,023 [+0,022 ; +0,024] | 0,18 | 15 % | 100,00 % | 195 |
| 0,1 | (c) split 3 LP | −0,014 | +0,025 [+0,024 ; +0,026] | 0,18 | 15 % | 100,00 % | 197 |
| 0,5 | (a) meilleur prix affiché | −0,014 | +0,035 [+0,034 ; +0,036] | 0,48 | 31 % | 99,92 % | 215 |
| 0,5 | (b) prix effectif | −0,014 | +0,035 [+0,034 ; +0,036] | 0,45 | 30 % | 99,93 % | 205 |
| 0,5 | (c) split 3 LP | −0,014 | +0,037 [+0,036 ; +0,038] | 0,46 | 30 % | 99,92 % | 207 |
| 0,9 | (a) meilleur prix affiché | −0,014 | +0,049 [+0,049 ; +0,050] | 0,79 | 41 % | 99,78 % | 230 |
| 0,9 | (b) prix effectif | −0,014 | +0,049 [+0,048 ; +0,050] | 0,71 | 38 % | 99,80 % | 202 |
| 0,9 | (c) split 3 LP | −0,014 | +0,051 [+0,050 ; +0,052] | 0,72 | 38 % | 99,76 % | 206 |

*Ordres de 20 M EUR, 20 000 ordres VAL par niveau de toxicité, coût en pips contre le mid d'arrivée (positif = on paie plus cher), mêmes aléas rejoués pour les 3 routeurs. Paramètres des 8 LP **inventés** (3 à last look agressif, 2 modérés, 3 prix fermes).*

- **Le meilleur prix affiché n'est pas le prix obtenu.** Le meilleur prix affiché est meilleur que le mid (−0,014 pip, cote périmée ou bruitée), mais le prix obtenu est plus cher de 0,04 à 0,06 pip selon la toxicité, et 15 % à 41 % des ordres subissent au moins un rejet.
- **Le routeur (b) apporte surtout de la fiabilité, pas du prix** : moins de rejets (0,71 contre 0,79 par ordre à toxicité 0,9) et moins de délai (202 contre 230 ms). Son gain de coût est de l'ordre du millième de pip : (a) et (b) ne choisissent pas le même LP pour 3 % / 10 % / 20 % des ordres (toxicité 0,1 / 0,5 / 0,9) et sur ceux-là (a) coûte −0,0003 [−0,0012 ; +0,0006] / +0,0011 [+0,0000 ; +0,0021] / +0,0013 [+0,0005 ; +0,0021] pip de plus. Détectable seulement à toxicité forte.
- **Le split (c) est dominé ici** : prix obtenu 0,051 contre 0,049 pip pour (b) à toxicité 0,9, sans réduction de dispersion. Le modèle ne valorise pas ce qu'un split apporte en pratique (moins de fuite d'information, profondeur).
- **Ces niveaux dépendent de LP inventés** : seule la mécanique (cote périmée + last look, donc écart affiché / obtenu qui croît avec la toxicité) est démontrée, pas des niveaux de pips réalistes.
<!-- /AUTO:SOR -->

![Comparaison des trois routeurs : prix effectif, rejets, délai](../figures/comparaison_routeurs_sor.png)

**Comment lire ce graphique.** Trois panneaux selon la toxicité du flux. À gauche : coût contre le mid d'arrivée (pips, positif = on paie plus cher) ; la ligne pointillée noire est le meilleur prix *affiché*, que personne n'obtient. Au milieu : nombre de rejets par ordre. À droite : délai jusqu'au dernier fill (ms). Les trois routeurs sont presque confondus sur le prix ; (b) se distingue par moins de rejets et un délai plus court quand la toxicité monte.

## Comment lire le tableau de bord

Le tableau de bord est en mode « coût » : tout est en bps du notionnel d'un ordre. Le coût du jour est la moyenne du shortfall de l'achat et de la vente ; la courbe est le coût cumulé (1 bp = 0,01 % du notionnel), il monte d'autant plus vite que l'exécution est chère. Les métriques donnent le coût moyen par jour, son écart-type et son p95, le coût cumulé en bps et en M EUR (50 M EUR par ordre, deux ordres par jour). Le voyant « Robuste ? » demande si le classement des variantes retenues est le même en TRAIN et en VAL (corrélation de rang de Spearman : vert à 0,8 et plus, orange de 0,5 à 0,8, rouge en dessous), et le nuage compare leur coût moyen TRAIN (abscisse) et VAL (ordonnée) autour de la diagonale. Le risque de prix d'un seul ordre est dans le filtre « Écart-type TRAIN », pas dans les courbes (achat et vente moyennés). Le TRAIN est in-sample pour le profil et les paramètres d'Almgren-Chriss ; le TEST n'apparaît jamais.

Essais instructifs : abaisser « Écart-type TRAIN max » pour ne garder que les stratégies les moins risquées (la courbe de coût cumulé monte plus vite : c'est le prix de la réduction de risque) ; ou ne garder que le modèle d'impact « racine carrée », puis « linéaire ×2 », et comparer l'ordre des stratégies.

## Validation et tests

`python -m pytest -q` : une dizaine de secondes avec les données de marché, quelques secondes sans (les tests qui lisent HistData sont sautés proprement si `HISTDATA_DIR` n'est pas défini ; c'est ce que fait la CI).

- **Almgren-Chriss** (`tests/test_almgren_chriss.py`) : trajectoire somme à 1 et monotone, formule en `sinh` explicite, λ → 0 donne le TWAP, la trajectoire minimise bien `E + λ V` (200 perturbations admissibles), variance de la formule confrontée à un Monte Carlo, espérance égale au coût du simulateur. La formule a aussi été contre-vérifiée par une optimisation numérique indépendante (écart maximal de l'ordre de 1e-8).
- **Simulateur de coûts** (`tests/test_tca.py`) : toutes les stratégies terminent l'ordre, **aucun look-ahead** (changer le futur ne change aucune décision passée, et le test a du pouvoir car POV réagit au passé), impact croissant avec l'urgence, calibrage de la racine carrée sur le linéaire, reproductibilité du bootstrap, achat + vente annulent la dérive, **TEST 2023 scellé**, deux tests de fuseau (NFP à 8h30 l'été comme l'hiver, ouverture du dimanche à 17h00).
- **Agrégateur** (`tests/test_agregation.py`) : le routeur (a) va chez le moins cher, le last look rejette quand le marché bouge contre le LP, le routeur (b) évite un LP très risqué, remplissage entre 0 et 1, reproductibilité.
- **Vitrine** (`tests/test_dashboard_et_readme.py`) : les chiffres VAL du rejeu TRAIN | VAL sont identiques au bit près à ceux de `run_all.py`, la série quotidienne est cohérente avec ses statistiques, `docs/data.json` cohérent avec `results/` et sans TEST, **blocs de chiffres du README et de ce fichier à jour** (un chiffre qui dérive fait échouer le test), l'écart théorie / réalisé du TWAP reconstruit exactement par le proxy de volume, structure du premier écran (≤ 400 lignes, tableaux larges repliés), un README par dossier, aucun chemin absolu de machine (parcours limité aux fichiers du dépôt, insensible à un `.venv`), recalcul des 60 premiers jours TRAIN depuis les minutes (sauté sans données).
- **Données absentes** (`tests/test_donnees_absentes.py`) : le message guidé (lien, arborescence, variable) remplace la trace brute.
- **Contre-vérification du 13/10/2026** : défaut de fuseau trouvé et corrigé (les données sont déjà à l'heure de New York ; l'ancienne conversion décalait les jours d'été d'une heure, donc la fenêtre 8h-9h ne contenait plus l'annonce de 8h30), avec test de régression et recalcul de tous les chiffres.

## Pour aller plus loin : dépôts voisins

Source : recherche `gh search repos` du 2026-10-13 (étoiles et dates lues dans les résultats de la recherche, code non exécuté lors de la recherche).

| Dépôt | Ce que c'est | Différence avec ce dépôt |
|---|---|---|
| [cuemacro/tcapy](https://github.com/cuemacro/tcapy) (251 étoiles, 2024) | TCA FX spot open source : slippage, markout, benchmarks sur gros jeux de ticks | Ici : exécution simulée de 7 stratégies rejouées sur jours réels, bootstrap, anti look-ahead. Pas de ticks ni de fills réels, pas de markout, pas d'infrastructure. |
| [joshuapjacob/almgren-chriss-optimal-execution](https://github.com/joshuapjacob/almgren-chriss-optimal-execution) (49, 2022) | Notebook Almgren-Chriss de liquidation optimale | Ici : version discrète exacte vérifiée par test d'optimalité, profil intrajournalier, comparaison à TWAP/VWAP/IS/POV sur FX réel. |
| [AshJha0/electronic-trading](https://github.com/AshJha0/electronic-trading) (29, 2026) | Almgren-Chriss, Avellaneda-Stoikov et analytique d'exécution en Python/C++/Rust/Java | Un seul langage ici ; en plus, Monte Carlo sur trajectoires réelles et simulateur d'agrégation. |
| [cvxgrp/vwap_opt_exec](https://github.com/cvxgrp/vwap_opt_exec) (44, 2019) | Exécution VWAP par optimisation convexe | Ici le VWAP-proxy suit un profil statique, sans prévision de volume ni optimisation. |
| [balancer/balancer-sor](https://github.com/balancer/balancer-sor) (263, 2026) | Smart order router DeFi, optimisation linéaire entre pools | Autre nature de liquidité (pools déterministes, pas de last look) ; ici le routeur traite le rejet et l'âge des cotes. |
| [jialuechen/flowforge](https://github.com/jialuechen/flowforge) (140, 2026) | Moteur de flux institutionnels et impact (loi racine carrée) | Ici l'impact racine carrée est supposé, calibré et appliqué par tranche, pas estimé sur métaordres. |
| [nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest) (4 878, 2025) | Backtest HFT avec latences et file d'attente sur carnet L2/L3 | Ici pas de carnet d'ordres ; la latence n'existe que dans l'agrégateur, à l'échelle de la milliseconde. |
| [JJJerome/mbt_gym](https://github.com/JJJerome/mbt_gym) (181, 2024) | Environnements gym d'exécution optimale et de market making, avec solutions analytiques | Même esprit de validation sur formule connue (test d'optimalité) ; pas d'apprentissage par renforcement ici. |
