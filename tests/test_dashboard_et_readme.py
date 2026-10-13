"""Cohérence des sorties « vitrine » : résultats TRAIN | VAL, tableau de bord (docs/), blocs de chiffres du README, hygiène.

Tout est lu dans results/ (versionné) : aucune donnée de marché requise, sauf le test de reproductibilité, qui est sauté sans données."""
import importlib.util
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from outils_donnees import besoin_donnees

RACINE = Path(__file__).resolve().parents[1]
DOCS = RACINE / "docs"
RESULTATS = RACINE / "results"
GABARIT = RACINE.parent / "_outils" / "dashboard" / "index.html"


def _json(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


def _module(nom: str):
    spec = importlib.util.spec_from_file_location(nom, RACINE / "scripts" / f"{nom}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    mod = _module("generer_readme_tete")
    v, o = mod.charger()
    texte = (RACINE / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    for nom, contenu in mod.blocs(v, o).items():
        m = re.search(rf"<!-- AUTO:{nom} -->\n(.*?)\n<!-- /AUTO:{nom} -->", texte, re.S)
        assert m, f"balises AUTO:{nom} absentes du README"
        assert m.group(1) == contenu, f"bloc AUTO:{nom} périmé : relancer scripts/generer_readme_tete.py"


def test_chaque_dossier_a_son_readme_et_les_figures_citees_existent():
    for dossier in ("execfx", "tests", "scripts", "notebooks", "figures", "results", "docs"):
        assert (RACINE / dossier / "README.md").is_file(), dossier
    readme = (RACINE / "README.md").read_text(encoding="utf-8")
    for png in set(re.findall(r"\(figures/([\w.-]+\.png)\)", readme)):
        assert (RACINE / "figures" / png).is_file(), png
    for png in set(re.findall(r"`([\w.-]+\.png)`", (RACINE / "figures" / "README.md").read_text(encoding="utf-8"))):
        assert (RACINE / "figures" / png).is_file(), png


def test_aucun_chemin_absolu_de_machine_dans_le_depot():
    """Pas de chemin absolu de machine (lecteur, puis dossier Users) dans le code, les notebooks, les README et les résultats."""
    motif = re.compile(r"[A-Za-z]:[\\/]+Users")
    exclus = {"test_dashboard_et_readme.py"}
    fautifs = []
    for p in RACINE.rglob("*"):
        if (not p.is_file() or p.name in exclus or p.suffix not in {".py", ".md", ".json", ".ipynb", ".yml", ".txt", ".csv", ".js", ".html", ".ini"}
                or any(x in p.parts for x in ("__pycache__", ".pytest_cache", "histdata", ".git"))):
            continue
        if motif.search(p.read_text(encoding="utf-8", errors="ignore")):
            fautifs.append(str(p.relative_to(RACINE)))
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
