"""Relance complète : TCA + agrégateur -> results/verdict_execution.json + figures/*.png.

Usage (depuis 03_execution_fx/) :  python scripts/run_all.py
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
warnings.filterwarnings("ignore", category=RuntimeWarning)  # moyennes de colonnes vides (minute 0 sans rendement)

import matplotlib  # noqa: E402

matplotlib.use("Agg")  # pas d'écran : on écrit des PNG
import numpy as np  # noqa: E402

from execfx import experiences as ex  # noqa: E402
from execfx import figures as fg  # noqa: E402
from execfx import tca  # noqa: E402
from execfx.donnees import executer_avec_message_clair  # noqa: E402
from execfx.impact import Hypotheses  # noqa: E402


def _sensibilite(cal, facteur: float) -> dict:
    out = ex.lancer_tca(cal, "lineaire", cal["hyp"].avec_impact_x(facteur), B=200)
    return {n: {"shortfall_moyen_bps": v["shortfall_moyen_bps"], "ecart_type_bps": v["ecart_type_bps"]}
            for n, v in out["resume"].items()}


def _resume_tca(t: dict) -> dict:
    return {"strategies": t["resume"], "meilleure_par_lambda": ex.meilleure_par_lambda(t["resume"])}


def _lecture(lin, rac, regime, agg) -> list[str]:
    r = lin["resume"]
    s = []
    a3 = lin["res"]["AC-lam3"]
    mini = min(r, key=lambda k: r[k]["shortfall_moyen_bps"])
    calme = min(r, key=lambda k: r[k]["ecart_type_bps"])
    s.append(f"Impact linéaire : coût moyen le plus bas = {mini} ({r[mini]['shortfall_moyen_bps']:.2f} bps), "
             f"risque le plus bas = {calme} (écart-type {r[calme]['ecart_type_bps']:.2f} bps, mais coût "
             f"{r[calme]['shortfall_moyen_bps']:.2f} bps) : on paie la réduction de risque en impact.")
    d = r["VWAP-proxy"]
    lo, hi = d["ic95_diff_moyen_vs_twap_bps"]
    ratio = abs(d["diff_moyen_vs_twap_bps"]) / r["TWAP"]["ecart_type_bps"]
    s.append(f"VWAP-proxy vs TWAP : écart de coût moyen {d['diff_moyen_vs_twap_bps']:+.3f} bps, IC95 [{lo:+.3f}, {hi:+.3f}] "
             f"(bootstrap par blocs de 5 jours, apparié) : "
             + ("l'IC contient 0, pas de différence détectable" if lo <= 0 <= hi else "statistiquement non nul")
             + f", mais économiquement faible ({ratio * 100:.1f} % de l'écart-type du shortfall du TWAP).")
    ac1, ac3 = r["AC-lam1"], r["AC-lam3"]
    s.append(f"Frontière : de AC-lam1 à AC-lam3 le coût moyen passe de {ac1['shortfall_moyen_bps']:.2f} à "
             f"{ac3['shortfall_moyen_bps']:.2f} bps et l'écart-type de {ac1['ecart_type_bps']:.2f} à "
             f"{ac3['ecart_type_bps']:.2f} bps : l'arbitrage coût/risque d'Almgren-Chriss se retrouve sur données réelles.")
    s.append(f"Hors échantillon (TRAIN -> VAL) : σ rms de la fenêtre {regime['sigma_rms_val_bps']:.2f} bps/min en VAL contre "
             f"{regime['sigma_rms_train_bps']:.2f} en TRAIN, activité du jour m moyen {regime['m_moyen_val']:.2f} (médiane "
             f"{regime['m_median_val']:.2f}) : la théorie calibrée sur TRAIN surestime le risque (TWAP : écart-type théorique "
             f"{r['TWAP']['theorie']['std_theorique_bps']:.1f} vs {r['TWAP']['ecart_type_bps']:.1f} empirique) et sous-estime "
             f"l'impact (TWAP : {r['TWAP']['theorie']['E_theorique_bps']:.2f} vs {r['TWAP']['shortfall_moyen_bps']:.2f} bps).")
    s.append(f"Pourquoi la théorie ne tombe pas pile : pour AC-lam3 l'écart-type du shortfall ({r['AC-lam3']['ecart_type_bps']:.2f} bps) mêle "
             f"le risque de prix ({a3.marche.std():.2f} bps contre {r['AC-lam3']['theorie']['std_theorique_bps']:.2f} en théorie) et la variabilité jour à jour de l'impact "
             f"({a3.impact.std():.2f} bps, absente de la théorie car le volume réel du jour varie).")
    gag = ex.meilleure_par_lambda(r)
    voulu = {f"lam={l}": f"AC-lam{i}" for i, l in enumerate(ex.LAMBDAS, start=1)}
    s.append("Meilleure stratégie par aversion au risque (utilité empirique E + λ·Var), théorie AC -> empirique : "
             + ", ".join(f"{k} : {voulu[k]} -> {gag[k]}" for k in gag)
             + ". Hors échantillon, le gagnant est moins agressif que l'optimum du modèle calibré sur TRAIN.")
    rr = rac["resume"]
    meme_ordre_risque = sorted(r, key=lambda k: r[k]["ecart_type_bps"]) == sorted(rr, key=lambda k: rr[k]["ecart_type_bps"])
    s.append(f"Impact racine carrée : classement des stratégies par risque {'identique' if meme_ordre_risque else 'différent'} "
             f"au linéaire ; coût d'une exécution agressive AC-lam3 = {rr['AC-lam3']['shortfall_moyen_bps']:.2f} bps contre "
             f"{ac3['shortfall_moyen_bps']:.2f} en linéaire : le modèle d'impact choisi déplace l'urgence optimale "
             f"(meilleure par λ en racine carrée : {', '.join(f'{k} -> {v}' for k, v in ex.meilleure_par_lambda(rr).items())}).")
    for k, v in agg.items():
        a, b, c = v["a_meilleur_affiche"], v["b_prix_effectif"], v["c_split"]
        dz = v["desaccord_a_vs_b"]
        s.append(f"SOR {k} : meilleur prix affiché = {a['meilleur_affiche_pips']:+.3f} pip mais prix obtenu par (a) = "
                 f"{a['prix_effectif_pips']['moyenne']:+.3f} pip (écart {a['prix_effectif_pips']['moyenne'] - a['meilleur_affiche_pips']:+.3f}) ; "
                 f"{a['ordres_avec_rejet'] * 100:.0f} % des ordres subissent un rejet. (b) obtient {b['prix_effectif_pips']['moyenne']:+.3f}, "
                 f"(c) {c['prix_effectif_pips']['moyenne']:+.3f}. (a) et (b) ne choisissent pas le même LP dans {dz['part_ordres'] * 100:.0f} % "
                 f"des ordres ; sur ceux-là (a) coûte {dz['cout_a_moins_cout_b_pips']['moyenne']:+.4f} pip de plus que (b) "
                 f"(IC95 [{dz['cout_a_moins_cout_b_pips']['ic95'][0]:+.4f}, {dz['cout_a_moins_cout_b_pips']['ic95'][1]:+.4f}]).")
    return s


LIMITES = [
    "Aucun volume FX : le profil de volume est un proxy d'activité de prix (|rendement| par minute), pas un volume.",
    "L'impact de marché est SUPPOSÉ (linéaire / racine carrée, paramètres documentés) et non estimé sur des fills : "
    "l'espérance du coût d'impact vient du modèle ; seules la dynamique de prix et l'activité du jour sont réelles.",
    "Les prix sont des BID de barres 1 minute ; le demi-spread est une constante supposée, l'exécution se fait au prix de la "
    "barre précédente (pas de simulation de carnet, pas d'effet de latence sous la minute pour le TCA).",
    "Les LP de l'agrégateur sont stylisés (8 LP, paramètres inventés pour représenter des LP serrés mais à last look "
    "face à des prix fermes plus larges) ; les ordres de grandeur en pips ne sont pas ceux d'un vrai agrégateur.",
    "Les statistiques de rejet du routeur (b) sont non conditionnelles à l'âge de la cote ; un vrai SOR conditionnerait.",
    "VAL (2019-2022) est moins actif que TRAIN (2010-2018) : les paramètres calibrés TRAIN sont donc légèrement hors régime.",
    "TEST (2023+) scellé, jamais lu. Une seule exécution de référence, pas de réglage sur VAL.",
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    (RACINE / "results").mkdir(exist_ok=True)
    (RACINE / "figures").mkdir(exist_ok=True)
    cal = ex.calibrer()
    hyp: Hypotheses = cal["hyp"]
    print(f"données : TRAIN {cal['n_jours_train']} jours, VAL {len(cal['fenetres_val'])}/{cal['n_jours_val_total']} jours utilisables")

    lin = ex.lancer_tca(cal, "lineaire")
    print("TCA linéaire ok", round(time.time() - t0, 1), "s")
    rac = ex.lancer_tca(cal, "racine")
    print("TCA racine carrée ok", round(time.time() - t0, 1), "s")
    sens = {"x0.5": _sensibilite(cal, 0.5), "x2": _sensibilite(cal, 2.0)}
    ctx = lin["ctx"]

    r_val = 1e4 * np.diff(np.log(cal["fenetres_val"]), axis=1)[:, hyp.pre_fenetre_min:]
    m_val = np.array([tca.activite_du_jour(p, ctx) for p in cal["fenetres_val"]])
    regime = {"sigma_rms_val_bps": float(np.sqrt(np.mean(r_val ** 2))), "sigma_rms_train_bps": ctx.sigma_ac,
              "m_moyen_val": float(m_val.mean()), "m_median_val": float(np.median(m_val)),
              "part_jours_m_au_plancher": float(np.mean(m_val <= hyp.m_min + 1e-9))}

    agg = ex.lancer_agregation(cal)
    print("agrégateur ok", round(time.time() - t0, 1), "s")
    front = ex.frontiere_theorique(ctx)

    lp = agg["lp"]
    verdict = {
        "projet": "Exécution optimale et agrégation de liquidité FX (EURUSD)",
        "meta": {"seed": ex.SEED, "split": "TRAIN <= 2018 (calibration) ; VAL 2019-2022 (évaluation) ; TEST 2023+ scellé, jamais chargé",
                 "jours_train": cal["n_jours_train"], "jours_val_utilises": int(len(cal["fenetres_val"])),
                 "jours_val_total": cal["n_jours_val_total"], "echantillons_par_strategie": int(2 * len(cal["fenetres_val"])),
                 "bootstrap": "1 000 rééchantillons par blocs de 5 jours, IC95 percentile, mêmes blocs pour toutes les stratégies",
                 "duree_s": round(time.time() - t0, 1)},
        "hypotheses": ex.hypotheses_dict(hyp, ctx, rac["ctx"].modele.y),
        "regime_val_vs_train": regime,
        "tca_impact_lineaire": _resume_tca(lin),
        "tca_impact_racine_carree": _resume_tca(rac),
        "sensibilite_impact_lineaire": sens,
        "frontiere_theorique": {k: v[::4] for k, v in front.items()},
        "agregation": {
            "ordre": "20 M EUR, 20 000 ordres VAL par niveau de toxicité, stats du routeur apprises sur 10 000 ordres TRAIN, "
                     "mêmes aléas rejoués pour les 3 routeurs (nombres aléatoires communs)",
            "unite": "pips (0.0001 EURUSD) ; coût = sens*(prix payé - mid d'arrivée), positif = on paie plus cher",
            "lp": {"noms": lp.noms, "demi_spread_pips": lp.demi_spread, "bruit_pips": lp.bruit, "latence_cote_ms": lp.latence,
                   "fenetre_last_look_ms": lp.fenetre_ll, "seuil_rejet_pips": lp.seuil_ll, "p_rejet_base": lp.p_base,
                   "p_rejet_pente_toxicite": lp.p_pente, "profondeur_meur": lp.profondeur},
            "resultats": agg["resultats"],
        },
    }
    verdict["lecture"] = _lecture(lin, rac, regime, agg["resultats"])
    verdict["limites"] = LIMITES

    with open(RACINE / "results" / "verdict_execution.json", "w", encoding="utf-8") as f:
        json.dump(ex.json_serialisable(verdict), f, ensure_ascii=False, indent=1)

    fg.fig_trajectoires(ctx, ex.LAMBDAS, RACINE / "figures" / "trajectoires_ac.png")
    fg.fig_frontiere(front, lin["strategies"], lin["resume"], RACINE / "figures" / "frontiere_efficiente.png")
    fg.fig_profil(cal["profil"], hyp, RACINE / "figures" / "profil_intrajournalier.png")
    fg.fig_distributions(lin["res"], lin["resume"], RACINE / "figures" / "distributions_shortfall.png")
    fg.fig_sor(agg["resultats"], RACINE / "figures" / "comparaison_routeurs_sor.png")
    print("terminé en", round(time.time() - t0, 1), "s")
    for ligne in verdict["lecture"]:
        print("-", ligne)


if __name__ == "__main__":
    executer_avec_message_clair(main)  # sans les minutes HistData : message guidé, pas de trace brute
