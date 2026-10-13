# `results/` : les sorties chiffrées (versionnées)

Les chiffres de tous les tableaux du README sont lus ici, jamais tapés à la main. Aucune donnée de marché brute, aucune donnée postérieure à 2022.

| Fichier | Ce qu'il contient | Script |
|---|---|---|
| `verdict_execution.json` | Calcul principal sur VAL : hypothèses, régime VAL contre TRAIN, TCA en impact linéaire et racine carrée (moyenne, IC95, écart-type, p95, théorie, utilité par λ), sensibilités ×0,5 et ×2, frontière théorique, agrégateur (3 toxicités × 3 routeurs : prix effectif, rejets, délai, désaccords a/b), phrases de lecture, limites. | `scripts/run_all.py` |
| `variantes_train_val.json` | Les 28 variantes (7 stratégies × 4 modèles d'impact), statistiques TRAIN \| VAL (moyenne et IC95, écart-type, p95, coût total en EUR, utilités), théorie, régime TRAIN \| VAL, robustesse (corrélation de rang, gagnants par λ), paramètres. | `scripts/rejeu_cout_quotidien.py` |
| `couts_quotidiens.csv` | Coût du jour (bps du notionnel, moyenne du shortfall d'un achat et d'une vente de 50 M EUR) de chacune des 28 variantes, une ligne par jour utilisable, TRAIN puis VAL (2010-01-04 à 2022-12-30). | `scripts/rejeu_cout_quotidien.py` |
