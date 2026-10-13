# `notebooks/` : la visite guidée

| Fichier | Ce qu'il fait |
|---|---|
| `visite_guidee.ipynb` | Visite pas à pas, sections « intuition → formule → attente → code → lecture » : profil intrajournalier, Almgren-Chriss, modèles d'impact, TCA sur jours réels, test anti look-ahead, agrégateur et routeurs, lecture finale. Exécuté, sans erreur. Il importe le package `execfx` (`sys.path.insert(0, "..")`) et lit les minutes via `HISTDATA_DIR`. |

Réexécuter : `python -m jupyter nbconvert --to notebook --execute --inplace notebooks/visite_guidee.ipynb` (jupyter, nbconvert et ipykernel requis, données de marché requises).
