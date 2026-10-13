# `docs/` : le tableau de bord interactif (GitHub Pages)

Page statique qui permet de choisir les conditions de départ (modèle d'impact, famille de stratégie, coût moyen TRAIN maximal, écart-type TRAIN maximal), de combiner les variantes retenues et de lire le **coût cumulé d'exécution** sur TRAIN (in-sample) puis VAL (hors échantillon), avec ses métriques recalculées dans le navigateur.
La sélection n'utilise que TRAIN ; le TEST n'apparaît jamais. Pas de serveur nécessaire : ouvrir `index.html` (les données sont dans `data.js`) ou publier le dossier avec GitHub Pages.

La page est en mode « coût » (`"mode": "cout"` dans `data.json`) : tout est en bps du notionnel, la courbe est le coût cumulé, et le voyant « Robuste ? » compare le classement des variantes retenues entre TRAIN et VAL (voir le README principal, section « Tableau de bord interactif »).

| Fichier | Rôle |
|---|---|
| `index.html` | La page (copie du gabarit commun des projets) ; charge Plotly depuis cdnjs. |
| `data.json` | Coût quotidien (en rendement négatif) des 28 variantes plus la référence TWAP, statistiques TRAIN \| VAL, filtres. Généré. |
| `data.js` | Même contenu que `data.json`, sous la forme `window.DATA = ...`, pour l'ouverture directe en `file://`. Généré. |
| `.nojekyll` | Fichier vide : demande à GitHub Pages de servir les fichiers tels quels. |

Régénérer `data.json`, `data.js` et la page : `python scripts/exporter_dashboard.py` (lit `results/`, aucune donnée de marché requise).
