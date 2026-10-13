"""Exporte le tableau de bord interactif (gabarit commun projets_cv/_outils/dashboard) dans docs/.

Lit UNIQUEMENT des fichiers de results/ (aucune donnée de marché requise, donc exécutable en CI) :
  - results/couts_quotidiens.csv        coût du jour (bps) de chaque variante, TRAIN puis VAL (le TEST n'existe pas)
  - results/variantes_train_val.json    statistiques TRAIN | VAL, hypothèses, périodes
Écrit docs/data.json, docs/data.js (même contenu, pour l'ouverture en file://), docs/index.html (copie du gabarit
s'il est présent à côté du dépôt, sinon on garde celui de docs/) et docs/.nojekyll.

Ici la série est un COÛT : le « rendement » d'un jour vaut -(coût du jour)/10 000 (convention de stockage du gabarit) et
la page, en mode "cout" (data.mode), l'affiche en bps : coût moyen, écart-type, p95, coût cumulé (bps et EUR), voyant
« Robuste ? » (le classement des variantes est-il le même en TRAIN et en VAL ?). Ni Sharpe ni voyant « Overfit ? ».
Le TRAIN est IN-SAMPLE (le profil d'activité et les paramètres d'Almgren-Chriss y sont calibrés) ; l'impact, lui,
est supposé, jamais estimé. La « sélection » par les filtres n'utilise que des statistiques TRAIN.

Usage : python scripts/exporter_dashboard.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parents[1]
RESULTATS = RACINE / "results"
DOCS = RACINE / "docs"
GABARIT = RACINE.parent / "_outils" / "dashboard" / "index.html"  # présent dans le dépôt du portfolio, absent d'un dépôt isolé
FIN_TRAIN, FIN_VAL = "2018-12-31", "2022-12-31"                    # découpage du projet (TRAIN <= 2018, VAL 2019-2022)


def _chiffre(x: float) -> float:
    return float(f"{x:.7g}")


def _virgule(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def texte_frais(p: dict, meta: dict) -> str:
    morceaux = [
        f"Ordre parent de {p['notionnel_eur'] / 1e6:.0f} M EUR (un achat et une vente par jour), {p['horizon_min']} tranches d'une minute, "
        f"fenêtre {p['debut_heure_ny']}h00-{p['debut_heure_ny'] + 1}h00 heure de New York, prix BID EURUSD 1 minute",
        f"demi-spread {_virgule(p['demi_spread_bps'], 1)} bp sur tout l'ordre ; impact temporaire linéaire {_virgule(p['eta_bps'], 0)} bps × participation "
        f"(ou racine carrée calibrée dessus, y = {_virgule(p['y_racine'], 3)}), ×0,5 et ×2 en sensibilité ; impact permanent {_virgule(p['gamma_bps'], 1)} bp pour l'ordre complet ; "
        f"liquidité accessible {p['volume_jour_eur'] / 1e9:.0f} Md EUR par jour (participation TWAP nominale {_virgule(100 * p['participation_twap_nominale'], 1)} %). "
        "L'impact est SUPPOSÉ, jamais estimé sur des fills",
        f"TRAIN {meta['periodes']['TRAIN'][0][:4]}-{meta['periodes']['TRAIN'][1][:4]} (profil d'activité et paramètres d'Almgren-Chriss calibrés ici : "
        f"le rejeu TRAIN est in-sample), VAL {meta['periodes']['VAL'][0][:4]}-{meta['periodes']['VAL'][1][:4]} hors échantillon, TEST 2023+ scellé",
        "Lecture : le coût du jour est la moyenne du shortfall de l'achat et de la vente, en bps du notionnel d'un ordre ; la courbe est le coût cumulé "
        "(1 bp = 0,01 % du notionnel) et le voyant « Robuste ? » dit si le classement des variantes retenues est le même en TRAIN et en VAL. "
        "Le risque de prix (écart-type du shortfall d'un seul ordre) est dans les filtres, pas dans les courbes (achat et vente moyennés)",
    ]
    return ". ".join(m[0].upper() + m[1:] for m in morceaux) + "."


def main() -> None:
    v = json.loads((RESULTATS / "variantes_train_val.json").read_text(encoding="utf-8"))
    csv = pd.read_csv(RESULTATS / "couts_quotidiens.csv", index_col=0)
    dates = list(csv.index)
    assert dates[-1] <= FIN_VAL and dates[-1] < "2023-01-01", "le TEST ne doit jamais apparaître"

    def stats(x: dict) -> dict:
        t, a = x["TRAIN"], x["VAL"]
        return {
            "cout_moyen_train_bps": round(t["shortfall_moyen_bps"], 4), "ecart_type_train_bps": round(t["ecart_type_bps"], 4),
            "p95_train_bps": round(t["p95_bps"], 4), "cout_total_train_meur": round(t["cout_total_eur"] / 1e6, 3),
            "cout_moyen_val_bps": round(a["shortfall_moyen_bps"], 4), "ecart_type_val_bps": round(a["ecart_type_bps"], 4),
            "p95_val_bps": round(a["p95_bps"], 4), "cout_total_val_meur": round(a["cout_total_eur"] / 1e6, 3),
        }

    variantes = []
    for cle, x in v["variantes"].items():
        r = [_chiffre(-c / 1e4) for c in csv[cle]]
        variantes.append({"id": x["id"], "libelle": f"{x['strategie_libelle']}, impact {x['modele_libelle']}", "groupe": x["famille"],
                          "modele_impact": x["modele_libelle"], "rendements": r, "stats": stats(x)})
    ref = next(x for x in v["variantes"].values() if x["strategie"] == "TWAP" and x["modele"] == "lin")
    variantes.append({"id": "REF-TWAP", "libelle": "Référence : TWAP, impact linéaire (ni filtrée ni combinée)", "groupe": "TWAP",
                      "modele_impact": ref["modele_libelle"], "reference": True,
                      "rendements": [_chiffre(-c / 1e4) for c in csv[f"{ref['modele']}__TWAP"]], "stats": stats(ref)})

    filtres = [
        {"cle": "modele_impact", "libelle": "Modèle d'impact", "type": "choix"},
        {"cle": "groupe", "libelle": "Famille de stratégie", "type": "choix"},
        {"cle": "cout_moyen_train_bps", "libelle": "Coût moyen TRAIN max (bps)", "type": "max", "pas": 0.1},
        {"cle": "ecart_type_train_bps", "libelle": "Écart-type TRAIN max (bps, risque de prix d'un ordre)", "type": "max", "pas": 0.1},
    ]
    data = {
        "mode": "cout",
        "notionnel_eur": v["parametres"]["notionnel_eur"],
        "ordres_par_jour": 2,                                  # un achat et une vente par jour
        "titre": "Projet 03 : coût d'exécution de 50 M EUR d'EURUSD, 28 variantes",
        "sous_titre": "7 stratégies × 4 modèles d'impact. Filtrer sur le coût et le risque TRAIN (in-sample), moyenner les variantes retenues, "
                      "lire le coût cumulé sur TRAIN puis VAL (hors échantillon). La courbe monte (coût cumulé en bps) : plus elle monte vite, plus l'exécution coûte.",
        "frais": texte_frais(v["parametres"], v["meta"]),
        "frontieres": {"train_fin": FIN_TRAIN, "val_fin": FIN_VAL},
        "dates": dates,
        "variantes": variantes,
        "filtres": filtres,
        "combinaison": "moyenne",
    }
    texte = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DOCS.mkdir(exist_ok=True)
    (DOCS / "data.json").write_text(texte, encoding="utf-8")
    (DOCS / "data.js").write_text("window.DATA = " + texte + ";\n", encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    if GABARIT.exists():
        shutil.copyfile(GABARIT, DOCS / "index.html")
    assert (DOCS / "index.html").exists(), "docs/index.html manquant (gabarit introuvable)"
    print(f"docs/data.json + data.js : {len(texte) / 1e6:.2f} Mo, {len(dates)} dates ({dates[0]} -> {dates[-1]}), {len(variantes)} variantes")


if __name__ == "__main__":
    main()
