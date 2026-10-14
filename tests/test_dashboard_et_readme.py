"""Cohérence des sorties « vitrine » : résultats TRAIN | VAL, tableau de bord (docs/), blocs de chiffres du README, hygiène.

Tout est lu dans results/ (versionné) : aucune donnée de marché requise, sauf le test de reproductibilité, qui est sauté sans données."""
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from outils_donnees import besoin_donnees

RACINE = Path(__file__).resolve().parents[1]
DOCS = RACINE / "docs"
RESULTATS = RACINE / "results"
GABARIT = RACINE.parent / "_outils" / "dashboard" / "index.html"
IGNORES = {".venv", "venv", ".git", "build", "__pycache__", ".pytest_cache", "site-packages", "node_modules", ".ipynb_checkpoints", "histdata"}


def _json(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


def _module(nom: str):
    spec = importlib.util.spec_from_file_location(nom, RACINE / "scripts" / f"{nom}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fichiers_du_depot() -> list[Path]:
    """Fichiers suivis ou à suivre par git (hors .gitignore) ; repli sur le parcours du dossier, sans environnement virtuel, build ni caches."""
    try:
        sortie = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=RACINE,
                                capture_output=True, text=True, check=True).stdout
        fichiers = [RACINE / ligne for ligne in sortie.splitlines() if ligne]
    except (OSError, subprocess.CalledProcessError):
        fichiers = []
    if not fichiers:
        fichiers = list(RACINE.rglob("*"))
    return [p for p in fichiers if p.is_file() and not (set(p.relative_to(RACINE).parts) & IGNORES)]


def test_variantes_val_identiques_au_verdict_de_run_all():
    """Le rejeu TRAIN | VAL réutilise les mêmes briques que run_all.py : ses chiffres VAL doivent être ceux du verdict, au bit près."""
    v, o = _json(RESULTATS / "variantes_train_val.json"), _json(RESULTATS / "verdict_execution.json")
    for mid, cle in (("lin", "tca_impact_lineaire"), ("rac", "tca_impact_racine_carree")):
        for s, r in o[cle]["strategies"].items():
            a = v["variantes"][f"{mid}__{s}"]["VAL"]
            for k in ("shortfall_moyen_bps", "ecart_type_bps", "p95_bps", "diff_moyen_vs_twap_bps", "ic95_moyen_bps"):
                assert np.allclose(a[k], r[k], rtol=0, atol=1e-12), (mid, s, k)
    for mid, cle in (("lin_x05", "x0.5"), ("lin_x2", "x2")):
        for s, r in o["sensibilite_impact_lineaire"][cle].items():
            assert np.isclose(v["variantes"][f"{mid}__{s}"]["VAL"]["shortfall_moyen_bps"], r["shortfall_moyen_bps"], rtol=0, atol=1e-12)


def test_serie_quotidienne_coherente_avec_les_statistiques_et_sans_test():
    v = _json(RESULTATS / "variantes_train_val.json")
    csv = pd.read_csv(RESULTATS / "couts_quotidiens.csv", index_col=0, parse_dates=True)
    assert csv.index.max() < pd.Timestamp("2023-01-01"), "le TEST ne doit jamais apparaître"
    assert csv.index.is_monotonic_increasing and csv.index.is_unique and list(csv.columns) == list(v["variantes"])
    fin_train = pd.Timestamp(v["meta"]["periodes"]["TRAIN"][1])
    for cle, x in v["variantes"].items():
        for nom, sel in (("TRAIN", csv.index <= fin_train), ("VAL", csv.index > fin_train)):
            serie = csv.loc[sel, cle]
            assert len(serie) == x[nom]["n_jours"]
            # coût du jour = moyenne achat/vente = coût d'impact : sa moyenne est le shortfall moyen (arrondi du CSV à 7 chiffres)
            assert np.isclose(serie.mean(), x[nom]["shortfall_moyen_bps"], rtol=1e-6), (cle, nom)
            assert np.isclose(x[nom]["cout_total_eur"], x[nom]["n_ordres"] * 50e6 * x[nom]["shortfall_moyen_bps"] * 1e-4)
        assert x["TRAIN"]["ic95_moyen_bps"][0] <= x["TRAIN"]["shortfall_moyen_bps"] <= x["TRAIN"]["ic95_moyen_bps"][1]


def test_donnees_du_tableau_de_bord_coherentes_et_sans_test():
    d, v = _json(DOCS / "data.json"), _json(RESULTATS / "variantes_train_val.json")
    csv = pd.read_csv(RESULTATS / "couts_quotidiens.csv", index_col=0)
    assert d["frontieres"] == {"train_fin": "2018-12-31", "val_fin": "2022-12-31"}
    assert d["mode"] == "cout" and d["notionnel_eur"] == v["parametres"]["notionnel_eur"] and d["ordres_par_jour"] == 2  # page en mode coût
    assert pd.Timestamp(d["dates"][-1]) < pd.Timestamp("2023-01-01"), "le TEST ne doit jamais apparaître"
    assert d["dates"] == list(csv.index)
    assert len(d["variantes"]) == len(v["variantes"]) + 1 and sum(1 for x in d["variantes"] if x.get("reference")) == 1  # + la référence TWAP
    for x, (cle, y) in zip(d["variantes"], v["variantes"].items()):
        r = np.array(x["rendements"], dtype=float)
        assert len(r) == len(d["dates"]) and x["id"] == y["id"]
        assert np.allclose(r, -csv[cle].to_numpy() / 1e4, rtol=1e-6, atol=0)   # rendement du jour = -(coût du jour), en fraction
        assert (r < 0).all(), "un coût d'exécution est toujours négatif en rendement"
        assert np.isclose(x["stats"]["cout_moyen_train_bps"], y["TRAIN"]["shortfall_moyen_bps"], atol=1e-4)
    for f in d["filtres"]:
        assert f["type"] in {"min", "max", "choix"}


def test_data_js_identique_a_data_json():
    brut = (DOCS / "data.json").read_text(encoding="utf-8")
    assert (DOCS / "data.js").read_text(encoding="utf-8") == "window.DATA = " + brut + ";\n"
    assert (DOCS / ".nojekyll").exists()


def test_page_du_tableau_de_bord_identique_au_gabarit_commun():
    if not GABARIT.exists():
        return  # dépôt isolé : pas de gabarit à côté
    assert (DOCS / "index.html").read_bytes() == GABARIT.read_bytes()


def test_blocs_de_chiffres_du_readme_lus_dans_results():
    """Chaque bloc AUTO (README.md et docs/details.md) est identique à ce que génère scripts/generer_readme_tete.py depuis results/."""
    mod = _module("generer_readme_tete")
    v, o = mod.charger()
    tous = mod.blocs(v, o)
    for fichier, noms in mod.DESTINATIONS.items():
        texte = (RACINE / fichier).read_text(encoding="utf-8").replace("\r\n", "\n")
        for nom in noms:
            m = re.search(rf"<!-- AUTO:{nom} -->\n(.*?)\n<!-- /AUTO:{nom} -->", texte, re.S)
            assert m, f"balises AUTO:{nom} absentes de {fichier}"
            assert m.group(1) == tous[nom], f"bloc AUTO:{nom} de {fichier} périmé : relancer scripts/generer_readme_tete.py"


def test_ecart_theorie_realise_du_twap_vient_entierement_du_proxy_de_volume():
    """Réalisé = impact temporaire théorique x E[1/m] + demi-spread + permanent : l'écart théorie / réalisé est une propriété du modèle de volume."""
    mod = _module("generer_readme_tete")
    v, _ = mod.charger()
    for periode in ("TRAIN", "VAL"):
        r = mod.reconstruction_proxy_volume(v, periode)
        assert abs(r["reconstruit"] - r["realise"]) < 1e-3, (periode, r)
        assert r["realise"] > r["theorie"]


def test_readme_premier_ecran_longueur_et_tableaux_replies():
    """Résultats clés et figure héro dans les 45 premières lignes, impact supposé et LP fictifs dits en tête, README court, tableaux de plus de 7 colonnes repliés."""
    lignes = (RACINE / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    assert len(lignes) <= 400, len(lignes)
    tete = "\n".join(lignes[:45])
    assert "## Résultats clés" in tete and "figures/hero_equity.png" in tete
    assert "actions/workflows/tests.yml/badge.svg" in tete
    assert "supposé" in tete and "fictif" in tete
    dans_details = 0
    for i, ligne in enumerate(lignes[:-1]):
        dans_details += ligne.count("<details>") - ligne.count("</details>")
        if ligne.startswith("|") and re.fullmatch(r"\|[-| :]+\|", lignes[i + 1].strip()) and not dans_details:
            assert ligne.count("|") - 1 <= 7, f"tableau de {ligne.count('|') - 1} colonnes hors <details> : ligne {i + 1}"


def test_chaque_dossier_a_son_readme_et_les_figures_citees_existent():
    for dossier in ("execfx", "tests", "scripts", "notebooks", "figures", "results", "docs"):
        assert (RACINE / dossier / "README.md").is_file(), dossier
    for source in ("README.md", "docs/details.md"):
        texte = (RACINE / source).read_text(encoding="utf-8")
        for png in set(re.findall(r"figures/([\w.-]+\.png)", texte)):
            assert (RACINE / "figures" / png).is_file(), (source, png)
    for png in set(re.findall(r"`([\w.-]+\.png)`", (RACINE / "figures" / "README.md").read_text(encoding="utf-8"))):
        assert (RACINE / "figures" / png).is_file(), png


def test_aucun_chemin_absolu_de_machine_dans_le_depot():
    """Pas de chemin absolu de machine (lecteur, puis dossier Users) dans le code, les notebooks, les README et les résultats."""
    motif = re.compile(r"[A-Za-z]:[\\/]+Users")
    exclus = {"test_dashboard_et_readme.py"}
    fautifs = [str(p.relative_to(RACINE)) for p in _fichiers_du_depot()
               if p.name not in exclus and p.suffix in {".py", ".md", ".json", ".ipynb", ".yml", ".txt", ".csv", ".js", ".html", ".ini"}
               and motif.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert not fautifs, fautifs


@besoin_donnees
def test_serie_quotidienne_reproductible_sur_les_premiers_jours_train():
    """Recalcule depuis les minutes HistData les 60 premiers jours TRAIN (impact linéaire, TWAP et AC λ=0,05) et compare au CSV."""
    from execfx import donnees as dn
    from execfx import experiences as ex
    from execfx import tca

    cal = ex.calibrer()
    hyp = cal["hyp"]
    d_tr, m_tr = dn.matrice_ny(dn.ANNEES_TRAIN)
    fen, garde = tca.preparer_fenetres(m_tr[:60], hyp)
    ctx = tca.construire_contexte(cal["profil"], hyp, "lineaire")
    strats = {s.nom: s for s in tca.strategies_standard(ctx, ex.LAMBDAS)}
    res = tca.executer_jours(fen, [strats["TWAP"], strats["AC-lam2"]], ctx)
    csv = pd.read_csv(RESULTATS / "couts_quotidiens.csv", index_col=0)
    dates = pd.DatetimeIndex(d_tr[:60][garde]).strftime("%Y-%m-%d")
    for nom, r in res.items():
        assert np.allclose(r.echantillons().mean(axis=1), csv.loc[dates, f"lin__{nom}"].to_numpy(), rtol=1e-5), nom
