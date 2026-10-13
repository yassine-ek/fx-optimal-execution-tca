# `scripts/` : lancer les calculs et fabriquer les sorties

Les scripts « calcul » lisent les minutes HistData (`HISTDATA_DIR`) ; les scripts « vitrine » ne lisent que `results/` et tournent sans données. Aucun script ne charge le TEST.

| Fichier | Ce qu'il fait / produit |
|---|---|
| `run_all.py` | Relance complète du calcul principal (~20 s) : TCA en impact linéaire et racine carrée, sensibilités ×0,5 et ×2, agrégateur → `results/verdict_execution.json` et 5 figures (`trajectoires_ac`, `frontiere_efficiente`, `profil_intrajournalier`, `distributions_shortfall`, `comparaison_routeurs_sor`). |
| `rejeu_cout_quotidien.py` | Rejoue le TCA jour par jour sur TRAIN (in-sample) et VAL pour 7 stratégies × 4 modèles d'impact (~1 min) → `results/couts_quotidiens.csv` (coût du jour de chaque variante) et `results/variantes_train_val.json` (statistiques TRAIN \| VAL, hypothèses, robustesse). Ses chiffres VAL sont identiques à ceux de `run_all.py`. |
| `exporter_dashboard.py` | Écrit `docs/data.json`, `docs/data.js`, copie la page du gabarit commun et crée `docs/.nojekyll` (lit `results/`, sans données). Rendement du jour = −(coût du jour). |
| `generer_figures_vitrine.py` | Écrit `figures/hero_equity.png`, `toutes_variantes.png`, `overfit_scatter.png` (lit `results/`, sans données). |
| `generer_readme_tete.py` | Réécrit dans `README.md` les blocs de chiffres (`AUTO:TETE`, `ROBUSTE`, `VARIANTES`, `LECTURE`, `SOR`) depuis `results/` ; un test vérifie qu'ils sont à jour. |
