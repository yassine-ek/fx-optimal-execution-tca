# `execfx/` : le package

Tout le code de calcul. Le nom évite le mot-clé `exec`. Aucun chemin absolu : les données de marché sont cherchées via `HISTDATA_DIR` (voir `donnees.py`). Le TEST (2023+) est scellé : le chargeur refuse l'année.

| Fichier | Ce qu'il fait |
|---|---|
| `__init__.py` | Docstring du package (exécution optimale et agrégation de liquidité FX, EURUSD). |
| `donnees.py` | Lit les zips HistData M1 (prix BID, un zip par année), à l'heure locale de New York (heure d'été comprise, vérifié sur le NFP et l'ouverture hebdomadaire) ; `HISTDATA_DIR`, `donnees_disponibles()` ; **refuse toute année ≥ 2023**. |
| `profils.py` | Profil intrajournalier par minute calibré sur TRAIN : activité de prix (proxy de volume, le FX n'a pas de volume centralisé), σ par minute, part du jour. |
| `almgren_chriss.py` | Almgren-Chriss en version discrète exacte : κ, trajectoire optimale `x_j`, espérance et variance du coût, frontière efficiente ; `lambda -> 0` redonne le TWAP. |
| `impact.py` | Les hypothèses du projet (`Hypotheses` : 50 M EUR, 60 min, 8h00, 5 Md EUR par jour, η, γ, demi-spread) et les modèles d'impact linéaire, racine carrée et permanent. |
| `tca.py` | Les 7 stratégies, la décision tranche par tranche **sans look-ahead** (la tranche k ne voit que `prix[: H+k+1]`), le calcul du shortfall d'un achat et d'une vente, le bootstrap par blocs et la théorie des plannings statiques. |
| `agregation.py` | Simulateur d'agrégateur : 8 LP (demi-spread, bruit, latence de cote, last look), 3 routeurs (a) meilleur prix affiché, (b) prix effectif appris sur TRAIN, (c) split ; cœur numba, aléas communs. |
| `experiences.py` | Orchestration partagée par les scripts et le notebook : calibrage, TCA complète d'un jeu d'hypothèses, frontière théorique, agrégation, sérialisation JSON. |
| `figures.py` | Les 5 figures du calcul principal (trajectoires, frontière, profil, distributions, routeurs), palette Okabe-Ito ; la palette est réutilisée par les figures de la vitrine. |
