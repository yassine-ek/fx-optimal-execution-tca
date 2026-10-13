# `tests/` : la suite pytest

Lancer : `python -m pytest -q` (depuis la racine du dépôt). Les tests qui lisent les minutes HistData sont **sautés** (`skipif`) si `HISTDATA_DIR` n'est pas défini ; tous les autres sont synthétiques ou lisent `results/` et tournent n'importe où (c'est ce que fait l'intégration continue).
Principe : chaque brique est confrontée à une réponse connue (formule fermée, optimisation, simulation), et les garanties de causalité et de non-ouverture du TEST sont des tests.

| Fichier | Ce qu'il fait |
|---|---|
| `conftest.py` | Fixtures : profil d'activité synthétique, contexte, fenêtres de prix aléatoires (aucune donnée réelle). |
| `outils_donnees.py` | Détecte les minutes HistData locales et fournit le marqueur `besoin_donnees` (skip propre). |
| `test_almgren_chriss.py` | Trajectoire sommant à 1 et monotone, formule en `sinh`, λ → 0 donne le TWAP, optimalité de `E + λV` (200 perturbations), variance contre Monte Carlo, espérance contre le simulateur. |
| `test_tca.py` | Les stratégies terminent l'ordre, aucun look-ahead (avec garde-fou de pouvoir), impact croissant avec l'urgence, calibrage racine carrée, bootstrap reproductible, dérive annulée par achat + vente, TEST 2023 scellé, fuseau (NFP à 8h30 l'été, ouverture du dimanche à 17h00). |
| `test_agregation.py` | Routeur (a) au meilleur prix affiché, last look, routeur (b) évite un LP risqué, remplissage, reproductibilité. |
| `test_dashboard_et_readme.py` | Rejeu TRAIN \| VAL identique au verdict de `run_all.py`, série quotidienne cohérente, `docs/data.json` et `data.js` cohérents et sans TEST, page identique au gabarit, blocs de chiffres du README à jour, un README par dossier, aucun chemin absolu de machine, recalcul des 60 premiers jours TRAIN (données requises). |
