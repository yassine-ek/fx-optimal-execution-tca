# `figures/` : les images du README

Toutes les figures sont calculées sur TRAIN et VAL seulement (le TEST n'existe pas dans ces images). Dpi 130, palette Okabe-Ito (une couleur fixe par stratégie).

| Image | Ce qu'elle montre | Script |
|---|---|---|
| `hero_equity.png` | Figure héro, un seul panneau compact aux polices de 11 à 13 pt (lisible réduite à environ 70 %) : coût cumulé d'exécution sur VAL (M EUR et bps cumulés) de chaque stratégie en impact linéaire, TWAP en référence en noir gras ; « impact supposé (niveaux indicatifs) » écrit dans le sous-titre. | `scripts/generer_figures_vitrine.py` |
| `toutes_variantes.png` | Les 28 variantes (7 stratégies × 4 modèles d'impact) en gris, les 7 stratégies en impact linéaire en couleur, TWAP en gras ; TRAIN grisé (in-sample), VAL à droite. | `scripts/generer_figures_vitrine.py` |
| `overfit_scatter.png` | À gauche, coût moyen TRAIN (x) contre VAL (y) pour les 28 variantes ; à droite, coût théorique attendu (x) contre coût réalisé TRAIN et VAL (y) pour les stratégies statiques. | `scripts/generer_figures_vitrine.py` |
| `frontiere_efficiente.png` | Frontière coût / risque théorique d'Almgren-Chriss (σ, θ du TRAIN), points théoriques et points réalisés en VAL avec IC95. | `scripts/run_all.py` |
| `trajectoires_ac.png` | Trajectoires optimales d'Almgren-Chriss selon l'aversion au risque λ (TWAP quand λ → 0). | `scripts/run_all.py` |
| `profil_intrajournalier.png` | Profil d'activité de prix par minute (proxy de volume FX) sur TRAIN et zoom sur la fenêtre 8h-9h. | `scripts/run_all.py` |
| `distributions_shortfall.png` | Distribution du shortfall d'un ordre par stratégie en VAL (moyenne, p95). | `scripts/run_all.py` |
| `comparaison_routeurs_sor.png` | Les trois routeurs selon la toxicité du flux : prix effectif contre meilleur prix affiché, rejets par ordre, délai. | `scripts/run_all.py` |
