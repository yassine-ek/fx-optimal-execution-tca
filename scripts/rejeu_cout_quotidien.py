"""Rejeu jour par jour du TCA sur TRAIN (in-sample) et VAL : 7 stratégies x 4 modèles d'impact = 28 variantes.

Pourquoi un second script à côté de `run_all.py` : `run_all.py` ne résume que VAL. Ici on garde AUSSI le coût de
chaque jour, pour tracer le coût cumulé (figure héro, tableau de bord) et comparer TRAIN et VAL.

TRAIN est IN-SAMPLE pour ce qui est calibré dessus (profil d'activité, sigma et theta d'Almgren-Chriss, planning
VWAP) : on y mesure ce que la théorie prédit quand elle est testée là où elle a été réglée. L'impact lui-même
(10 bps x participation, etc.) est SUPPOSÉ, il n'est estimé nulle part. Aucune variante n'est choisie sur VAL.
TEST (2023+) n'est jamais chargé : `donnees.charger_annee` le refuse.

Écrit :
  results/couts_quotidiens.csv       coût du jour (bps du notionnel) de chaque variante, une ligne par jour utilisable
  results/variantes_train_val.json   statistiques TRAIN | VAL par variante, hypothèses, robustesse TRAIN -> VAL

Coût du jour = moyenne de l'implementation shortfall d'un ACHAT et d'une VENTE de 50 M EUR : la dérive du prix
s'annule exactement, il reste le coût d'impact (modèle) calculé avec l'activité réelle du jour.

Usage : HISTDATA_DIR=... python scripts/rejeu_cout_quotidien.py        (environ 1 à 2 minutes)
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
warnings.filterwarnings("ignore", category=RuntimeWarning)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from execfx import almgren_chriss as ac  # noqa: E402
from execfx import donnees as dn  # noqa: E402
from execfx import experiences as ex  # noqa: E402
from execfx import tca  # noqa: E402

RESULTATS = RACINE / "results"

# identifiant -> (libellé, libellé court, type de modèle d'impact de execfx, facteur d'échelle sur eta et gamma)
MODELES = {
    "lin": ("linéaire", "lin", "lineaire", 1.0),
    "rac": ("racine carrée", "rac", "racine", 1.0),
    "lin_x05": ("linéaire ×0,5", "lin×0,5", "lineaire", 0.5),
    "lin_x2": ("linéaire ×2", "lin×2", "lineaire", 2.0),
}
# nom interne -> (libellé, court, famille)
STRATEGIES = {
    "TWAP": ("TWAP", "TWAP", "TWAP"),
    "VWAP-proxy": ("VWAP-proxy", "VWAP", "VWAP"),
    "AC-lam1": (f"Almgren-Chriss λ={ex.LAMBDAS[0]:g}".replace(".", ","), "AC1", "Almgren-Chriss"),
    "AC-lam2": (f"Almgren-Chriss λ={ex.LAMBDAS[1]:g}".replace(".", ","), "AC2", "Almgren-Chriss"),
    "AC-lam3": (f"Almgren-Chriss λ={ex.LAMBDAS[2]:g}".replace(".", ","), "AC3", "Almgren-Chriss"),
    "IS-front-loaded": ("IS front-loaded", "IS", "IS"),
    "POV-proxy": ("POV-proxy", "POV", "POV"),
}


def cle(modele: str, strategie: str) -> str:
    return f"{modele}__{strategie}"


def _resume_periode(r: dict, res, n_jours: int, notionnel: float) -> dict:
    """Statistiques d'une période pour une variante : celles de tca.resumer + coût en EUR."""
    out = {k: r[k] for k in ("shortfall_moyen_bps", "ic95_moyen_bps", "ecart_type_bps", "ic95_ecart_type_bps", "p95_bps",
                             "ic95_p95_bps", "p05_bps", "cout_impact_moyen_bps", "part_executee_mi_horizon",
                             "diff_moyen_vs_twap_bps", "ic95_diff_moyen_vs_twap_bps")}
    out["utilite"] = r["utilite"]
    out["ecart_type_marche_bps"] = float(res.marche.std())       # risque de prix d'un achat (aléa réel du jour)
    out["ecart_type_impact_jour_bps"] = float(res.impact.std())  # variabilité jour à jour du coût d'impact (activité du jour)
    out["n_jours"] = n_jours
    out["n_ordres"] = 2 * n_jours
    out["cout_par_ordre_eur"] = notionnel * r["shortfall_moyen_bps"] * 1e-4
    out["cout_total_eur"] = 2 * n_jours * out["cout_par_ordre_eur"]  # un achat + une vente de `notionnel` par jour
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    cal = ex.calibrer()
    hyp = cal["hyp"]
    d_tr, m_tr = dn.matrice_ny(dn.ANNEES_TRAIN)
    fen_tr, garde_tr = tca.preparer_fenetres(m_tr, hyp)
    dates_tr, dates_va = d_tr[garde_tr], cal["dates_val"]
    assert max(dates_tr.max(), dates_va.max()) < np.datetime64("2023-01-01"), "le TEST ne doit jamais être chargé"
    periodes = {"TRAIN": (dates_tr, fen_tr), "VAL": (dates_va, cal["fenetres_val"])}
    print(f"TRAIN {len(dates_tr)}/{cal['n_jours_train']} jours utilisables, VAL {len(dates_va)}/{cal['n_jours_val_total']}")

    variantes, quotidien, ctx_ref, y_racine = {}, {"TRAIN": {}, "VAL": {}}, None, None
    robustesse = {}
    for mid, (lib_m, court_m, type_m, facteur) in MODELES.items():
        hyp_m = hyp.avec_impact_x(facteur)
        par_periode = {}
        for nom_p, (dates_p, fen_p) in periodes.items():
            out = ex.lancer_tca({**cal, "fenetres_val": fen_p}, type_m, hyp_m, B=1000)
            par_periode[nom_p] = out
            for strat, r in out["res"].items():
                quotidien[nom_p][cle(mid, strat)] = r.echantillons().mean(axis=1)
            print(f"  {mid:8s} {nom_p:5s} ok  {time.time() - t0:5.1f} s")
        ctx = par_periode["VAL"]["ctx"]
        if mid == "lin":
            ctx_ref = ctx
        if mid == "rac":
            y_racine = ctx.modele.y
        for strat, (lib_s, court_s, famille) in STRATEGIES.items():
            rv, rt = par_periode["VAL"]["resume"][strat], par_periode["TRAIN"]["resume"][strat]
            variantes[cle(mid, strat)] = {
                "id": f"{court_s}·{court_m}", "cle": cle(mid, strat), "strategie": strat, "strategie_libelle": lib_s,
                "famille": famille, "modele": mid, "modele_libelle": lib_m, "facteur_impact": facteur,
                "theorie": rv["theorie"],
                "TRAIN": _resume_periode(rt, par_periode["TRAIN"]["res"][strat], len(dates_tr), hyp.notionnel_eur),
                "VAL": _resume_periode(rv, par_periode["VAL"]["res"][strat], len(dates_va), hyp.notionnel_eur),
            }
        moy_t = [variantes[cle(mid, s)]["TRAIN"]["shortfall_moyen_bps"] for s in STRATEGIES]
        moy_v = [variantes[cle(mid, s)]["VAL"]["shortfall_moyen_bps"] for s in STRATEGIES]
        robustesse[mid] = {
            "spearman_cout_moyen_train_val": float(spearmanr(moy_t, moy_v).statistic),
            "rapport_val_sur_train_cout_moyen": {s: v / t for s, t, v in zip(STRATEGIES, moy_t, moy_v)},
            "meilleure_par_lambda_train": ex.meilleure_par_lambda(par_periode["TRAIN"]["resume"]),
            "meilleure_par_lambda_val": ex.meilleure_par_lambda(par_periode["VAL"]["resume"]),
        }

    # régime : le TRAIN calibre, le VAL évalue ; est-ce le même marché ?
    def regime(fen):
        r = 1e4 * np.diff(np.log(fen), axis=1)[:, hyp.pre_fenetre_min:]
        m = np.array([tca.activite_du_jour(p, ctx_ref) for p in fen])
        return {"sigma_rms_fenetre_bps": float(np.sqrt(np.mean(r ** 2))), "m_moyen": float(m.mean()),
                "m_median": float(np.median(m)), "inverse_m_moyen": float(np.mean(1.0 / m))}  # impact ∝ 1/m : E[1/m] >= 1/E[m]
    reg = {"TRAIN": regime(fen_tr), "VAL": regime(cal["fenetres_val"])}

    # série quotidienne : TRAIN puis VAL, une ligne par jour utilisable
    cols = list(variantes)
    idx = pd.DatetimeIndex(np.concatenate([dates_tr, dates_va])).strftime("%Y-%m-%d")
    tab = pd.DataFrame({c: np.concatenate([quotidien["TRAIN"][c], quotidien["VAL"][c]]) for c in cols}, index=idx)
    tab.index.name = "date"
    RESULTATS.mkdir(exist_ok=True)
    tab.to_csv(RESULTATS / "couts_quotidiens.csv", float_format="%.7g")

    cfg = {
        "notionnel_eur": hyp.notionnel_eur, "horizon_min": hyp.horizon_min, "debut_heure_ny": hyp.debut_min // 60,
        "eta_bps": hyp.eta_bps, "gamma_bps": hyp.gamma_bps, "demi_spread_bps": hyp.demi_spread_bps,
        "volume_jour_eur": hyp.volume_jour_eur, "participation_twap_nominale":
            float(hyp.notionnel_eur / (hyp.volume_jour_eur * ctx_ref.part.sum())),
        "y_racine": float(y_racine), "sigma_ac_bps": ctx_ref.sigma_ac, "theta_ac_bps": ctx_ref.theta_ac,
        "lambdas_ac": list(ex.LAMBDAS),
        "kappa_T_des_lambdas": [float(ac.kappa(l, ctx_ref.sigma_ac, ctx_ref.theta_ac, hyp.gamma_bps) * ctx_ref.N)
                                for l in ex.LAMBDAS],
    }
    verdict = {
        "projet": "Exécution FX : coût d'exécution quotidien, TRAIN | VAL, 28 variantes",
        "meta": {
            "seed": ex.SEED,
            "periodes": {"TRAIN": [str(dates_tr.min()), str(dates_tr.max())], "VAL": [str(dates_va.min()), str(dates_va.max())]},
            "jours_utilises": {"TRAIN": len(dates_tr), "VAL": len(dates_va)},
            "jours_ouvres": {"TRAIN": cal["n_jours_train"], "VAL": cal["n_jours_val_total"]},
            "test": "2023+ scellé : jamais chargé (donnees.charger_annee refuse l'année)",
            "bootstrap": "1 000 rééchantillons par blocs de 5 jours, IC95 percentile, mêmes blocs pour toutes les stratégies",
            "convention_cout_du_jour": "moyenne du shortfall d'un achat et d'une vente de 50 M EUR : la dérive du prix s'annule, "
                                       "il reste le coût d'impact du modèle avec l'activité réelle du jour",
            "convention_cout_total_eur": "n_jours x (1 achat + 1 vente) x 50 M EUR x shortfall moyen",
            "train_in_sample": "profil d'activité, sigma et theta d'Almgren-Chriss, planning VWAP calibrés sur TRAIN : "
                               "le rejeu TRAIN est in-sample pour eux ; l'impact est supposé, jamais estimé",
            "duree_s": round(time.time() - t0, 1),
        },
        "parametres": cfg,
        "modeles": {k: {"libelle": v[0], "court": v[1], "type": v[2], "facteur": v[3]} for k, v in MODELES.items()},
        "strategies": {k: {"libelle": v[0], "court": v[1], "famille": v[2]} for k, v in STRATEGIES.items()},
        "regime": reg,
        "robustesse": robustesse,
        "variantes": variantes,
    }
    with open(RESULTATS / "variantes_train_val.json", "w", encoding="utf-8") as f:
        json.dump(ex.json_serialisable(verdict), f, ensure_ascii=False, indent=1)
    print(f"results/couts_quotidiens.csv ({tab.shape[0]} jours x {tab.shape[1]} variantes) et "
          f"results/variantes_train_val.json écrits en {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
