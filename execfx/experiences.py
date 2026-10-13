"""Orchestration des expériences (partagée par scripts/run_all.py et le notebook).

Découpage temporel : TRAIN (<= 2018) calibre profils, paramètres et statistiques du routeur ;
VAL (2019-2022) évalue ; TEST (2023+) n'est jamais chargé (donnees.charger_annee le refuse).
"""
from __future__ import annotations

import numpy as np

from . import agregation as ag
from . import almgren_chriss as ac
from . import donnees as dn
from . import tca
from .impact import Hypotheses
from .profils import calibrer_profil

LAMBDAS = (0.01, 0.05, 0.3)   # aversion au risque (1/bps) : faible, moyenne, forte
TOXICITES = (0.1, 0.5, 0.9)   # part de flux « toxique » perçue par les LP à last look
SEED = 20261013


def calibrer(hyp: Hypotheses | None = None) -> dict:
    """Charge TRAIN et VAL, calibre le profil sur TRAIN, extrait les fenêtres 8h-9h de VAL."""
    hyp = hyp or Hypotheses()
    d_tr, m_tr = dn.matrice_ny(dn.ANNEES_TRAIN)
    d_va, m_va = dn.matrice_ny(dn.ANNEES_VAL)
    profil = calibrer_profil(m_tr)
    fen, gardes = tca.preparer_fenetres(m_va, hyp)
    return {"hyp": hyp, "profil": profil, "mat_train": m_tr, "mat_val": m_va, "dates_val": d_va[gardes],
            "fenetres_val": fen, "n_jours_val_total": len(m_va), "n_jours_train": len(m_tr)}


def lancer_tca(cal: dict, modele: str = "lineaire", hyp: Hypotheses | None = None, B: int = 1000,
               seed: int = SEED) -> dict:
    """TCA complète d'un jeu d'hypothèses : stratégies, résumé bootstrap, théorie, utilités empiriques."""
    hyp = hyp or cal["hyp"]
    ctx = tca.construire_contexte(cal["profil"], hyp, modele)
    strats = tca.strategies_standard(ctx, LAMBDAS)
    res = tca.executer_jours(cal["fenetres_val"], strats, ctx)
    resume = tca.resumer(res, np.random.default_rng(seed), B=B)
    for s in strats:
        if s.adaptative:
            resume[s.nom]["theorie"] = None
        else:
            resume[s.nom]["theorie"] = tca.theorie_statique(s.planning, ctx)
    # utilité empirique E + lam*Var : qui gagne pour quelle aversion au risque ?
    for nom, r in res.items():
        pool = r.echantillons().ravel()
        resume[nom]["utilite"] = {f"lam={lam}": float(pool.mean() + lam * pool.var(ddof=1)) for lam in LAMBDAS}
    return {"ctx": ctx, "strategies": strats, "res": res, "resume": resume}


def meilleure_par_lambda(resume: dict) -> dict:
    return {f"lam={lam}": min(resume, key=lambda k: resume[k]["utilite"][f"lam={lam}"]) for lam in LAMBDAS}


def frontiere_theorique(ctx: tca.Contexte, n_points: int = 60) -> dict:
    lams = np.concatenate([[0.0], np.logspace(-3, 1, n_points)])
    f = ac.frontiere(lams, ctx.N, ctx.sigma_ac, ctx.theta_ac, ctx.hyp.gamma_bps, ctx.hyp.demi_spread_bps)
    return f


def lancer_agregation(cal: dict, n_train: int = 10000, n_eval: int = 20000, seed: int = SEED,
                      toxicites: tuple = TOXICITES, taille_meur: float = 20.0) -> dict:
    """Monte Carlo de l'agrégateur : stats du SOR apprises sur TRAIN, évaluation sur VAL, 3 routeurs."""
    rng = np.random.default_rng(seed + 1)
    lp = ag.lp_par_defaut()
    al_tr = ag.generer_aleas(rng, ag.tirer_minutes(cal["mat_train"], n_train, rng))
    al_va = ag.generer_aleas(rng, ag.tirer_minutes(cal["mat_val"], n_eval, rng))
    out = {f"toxicite={t}": ag.comparer_routeurs(al_va, al_tr, lp, t, taille_meur) for t in toxicites}
    return {"lp": lp, "resultats": out}


def json_serialisable(x):
    if isinstance(x, dict):
        return {str(k): json_serialisable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [json_serialisable(v) for v in x]
    if isinstance(x, np.ndarray):
        return json_serialisable(x.tolist())
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def hypotheses_dict(hyp: Hypotheses, ctx: tca.Contexte, y_racine: float) -> dict:
    rho_ref = hyp.notionnel_eur / (hyp.volume_jour_eur * ctx.part.sum())
    return {
        "ordre_parent": f"{hyp.notionnel_eur / 1e6:.0f} M EUR (achat ET vente rejoués chaque jour), "
                        f"{hyp.horizon_min} min, 1 tranche/min, fenêtre {hyp.debut_min // 60}h00 New York",
        "volume_fx": "AUCUN volume FX dans les données (colonne volume = 0) : l'activité de prix |rendement| "
                     "moyen par minute (TRAIN) sert de proxy de volume",
        "volume_jour_accessible_eur": hyp.volume_jour_eur,
        "volume_fenetre_attendu_eur": float(hyp.volume_jour_eur * ctx.part.sum()),
        "participation_twap_nominale": float(rho_ref),
        "impact_temporaire_lineaire": f"slippage_bps = {hyp.eta_bps} * participation",
        "impact_racine_carree": f"slippage_bps = y * sigma_minute_bps * sqrt(participation), y={y_racine:.3f}, "
                                "calibré pour égaler le linéaire au TWAP nominal",
        "impact_permanent_bps_ordre_complet": hyp.gamma_bps,
        "demi_spread_bps": hyp.demi_spread_bps,
        "activite_du_jour": f"volume réel = volume attendu x m, m = activité réalisée / attendue, borné "
                            f"[{hyp.m_min}, {hyp.m_max}] ; jamais visible des stratégies",
        "sigma_ac_bps_par_racine_min": ctx.sigma_ac,
        "theta_ac_bps_par_fraction": ctx.theta_ac,
        "lambdas_ac": list(LAMBDAS),
        "kappa_T_des_lambdas": [float(ac.kappa(l, ctx.sigma_ac, ctx.theta_ac, hyp.gamma_bps) * ctx.N)
                                for l in LAMBDAS],
        "tca_nature": "TCA fondée sur un MODÈLE d'impact supposé appliqué à de vraies trajectoires de prix : "
                      "l'espérance du coût d'impact vient du modèle, le risque de prix (écart-type, queues) "
                      "vient des données réelles",
    }
