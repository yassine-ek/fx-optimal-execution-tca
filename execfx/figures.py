"""Figures PNG (dpi 130). Palette Okabe-Ito (lisible en daltonisme), une couleur fixe par stratégie.

Le backend « Agg » (sans écran) est choisi par scripts/run_all.py, pas ici : un notebook garde son affichage inline.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from . import almgren_chriss as ac
from .agregation import ROUTEURS

DPI = 130
COULEURS = {"TWAP": "#555555", "VWAP-proxy": "#56B4E9", "AC-lam1": "#0072B2", "AC-lam2": "#009E73",
            "AC-lam3": "#D55E00", "IS-front-loaded": "#CC79A7", "POV-proxy": "#E69F00"}
COULEURS_ROUTEURS = {"a_meilleur_affiche": "#D55E00", "b_prix_effectif": "#0072B2", "c_split": "#009E73"}
NOMS_ROUTEURS = {"a_meilleur_affiche": "(a) meilleur prix affiché", "b_prix_effectif": "(b) prix effectif",
                 "c_split": "(c) split 3 LP"}


def _style():
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.alpha": 0.25, "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold"})


def _sauver(fig, chemin: Path):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(chemin, dpi=DPI)
    plt.close(fig)


def fig_trajectoires(ctx, lams, chemin: Path):
    """Quantité restante x_j/X pour plusieurs aversions au risque : plus lam est grand, plus on vend tôt."""
    _style()
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    N = ctx.N
    t = np.arange(N + 1)
    ax.plot(t, ac.detentions(N, 0.0, ctx.sigma_ac, ctx.theta_ac, ctx.hyp.gamma_bps), color=COULEURS["TWAP"],
            ls="--", label="λ → 0 : TWAP (linéaire)")
    for i, lam in enumerate(lams, start=1):
        kT = ac.kappa(lam, ctx.sigma_ac, ctx.theta_ac, ctx.hyp.gamma_bps) * N
        ax.plot(t, ac.detentions(N, lam, ctx.sigma_ac, ctx.theta_ac, ctx.hyp.gamma_bps),
                color=COULEURS[f"AC-lam{i}"], label=f"λ = {lam}  (κT = {kT:.1f})")
    ax.set(xlabel="minutes depuis l'arrivée de l'ordre", ylabel="fraction de l'ordre restant  x(t)/X",
           title="Almgren-Chriss : trajectoires optimales selon l'aversion au risque λ")
    ax.legend(frameon=False)
    _sauver(fig, chemin)


def fig_frontiere(front: dict, strategies, resume: dict, chemin: Path):
    """Frontière efficiente théorique (courbe) + points théoriques (ronds vides) + points empiriques (barres IC95)."""
    _style()
    fig, ax = plt.subplots(figsize=(8, 5.2))
    ax.plot(front["std_bps"], front["E_bps"], color="#999999", lw=2, label="frontière théorique AC (σ, θ du TRAIN)", zorder=1)
    for s in strategies:
        r = resume[s.nom]
        c = COULEURS[s.nom]
        if r["theorie"] is not None:
            ax.scatter(r["theorie"]["std_theorique_bps"], r["theorie"]["E_theorique_bps"],
                       facecolors="none", edgecolors=c, s=70, lw=1.6, zorder=3)
        ic_m, ic_s = r["ic95_moyen_bps"], r["ic95_ecart_type_bps"]
        ax.errorbar(r["ecart_type_bps"], r["shortfall_moyen_bps"],
                    xerr=[[r["ecart_type_bps"] - ic_s[0]], [ic_s[1] - r["ecart_type_bps"]]],
                    yerr=[[r["shortfall_moyen_bps"] - ic_m[0]], [ic_m[1] - r["shortfall_moyen_bps"]]],
                    fmt="o", color=c, ms=7, capsize=2, label=s.nom, zorder=4)
    ax.scatter([], [], facecolors="none", edgecolors="k", s=70, label="point théorique du même planning")
    ax.set(xlabel="risque : écart-type du shortfall (bps)", ylabel="coût moyen : implementation shortfall (bps)",
           title="Frontière efficiente : théorie (TRAIN) vs trajectoires réelles VAL 2019-2022")
    ax.legend(frameon=False, fontsize=8.5)
    _sauver(fig, chemin)


def fig_profil(profil, hyp, chemin: Path):
    """Activité de prix par minute de la journée (proxy du volume FX) + zoom sur la fenêtre d'exécution."""
    _style()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.3), gridspec_kw={"width_ratios": [2, 1.2]})
    m = np.arange(1440) / 60
    a1.plot(m, profil.activite_bps, color="#0072B2", lw=0.8)
    d, N = hyp.debut_min, hyp.horizon_min
    a1.axvspan(d / 60, (d + N) / 60, color="#E69F00", alpha=0.3, label="fenêtre d'exécution")
    a1.set(xlabel="heure locale de New York", ylabel="|rendement| moyen d'une minute (bps)",
           title="Profil d'activité EURUSD (TRAIN 2010-2018) : proxy de volume", xlim=(0, 24), xticks=range(0, 25, 3))
    a1.legend(frameon=False)
    mm = np.arange(d, d + N)
    a2.bar(mm - d, profil.activite_bps[d: d + N], color="#0072B2", width=0.9, label="activité (proxy volume)")
    a2.plot(mm - d, profil.sigma_min_bps[d: d + N], color="#D55E00", lw=1.4, label="σ par minute (rms)")
    a2.set(xlabel="minute depuis 8h00 NY", ylabel="bps", title="Zoom 8h00-9h00 : pic des annonces US à 8h30")
    a2.legend(frameon=False)
    _sauver(fig, chemin)


def fig_distributions(res: dict, resume: dict, chemin: Path):
    """Distribution du shortfall (achats + ventes poolés) par stratégie, lignes = moyenne et p95."""
    _style()
    noms = list(res)
    donnees = [res[n].echantillons().ravel() for n in noms]
    fig, ax = plt.subplots(figsize=(10, 5))
    v = ax.violinplot(donnees, showextrema=False, widths=0.85)
    for corps, n in zip(v["bodies"], noms):
        corps.set_facecolor(COULEURS[n]), corps.set_alpha(0.55)
    for i, n in enumerate(noms, start=1):
        ax.plot([i - 0.3, i + 0.3], [resume[n]["shortfall_moyen_bps"]] * 2, color="k", lw=2)
        ax.plot([i - 0.3, i + 0.3], [resume[n]["p95_bps"]] * 2, color="k", lw=1, ls=":")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(range(1, len(noms) + 1), noms, rotation=20)
    n_jours = len(res[noms[0]].marche)
    ax.set(ylabel="implementation shortfall (bps)", ylim=(-35, 45),
           title=f"Distribution du shortfall, {n_jours} jours VAL, achats + ventes (trait plein = moyenne, pointillé = p95)")
    ax.title.set_fontsize(10)
    _sauver(fig, chemin)


def fig_sor(agg: dict, chemin: Path):
    """Comparaison des routeurs SOR selon la toxicité du flux."""
    _style()
    tox = list(agg)
    x = np.array([float(k.split("=")[1]) for k in tox])
    fig, ax = plt.subplots(1, 3, figsize=(13, 4.2))
    meilleur = [agg[k]["a_meilleur_affiche"]["meilleur_affiche_pips"] for k in tox]
    ax[0].plot(x, meilleur, color="k", ls="--", marker="s", label="meilleur prix AFFICHÉ (cible)")
    for r in ROUTEURS:
        y = np.array([agg[k][r]["prix_effectif_pips"]["moyenne"] for k in tox])
        lo = np.array([agg[k][r]["prix_effectif_pips"]["ic95"][0] for k in tox])
        hi = np.array([agg[k][r]["prix_effectif_pips"]["ic95"][1] for k in tox])
        ax[0].errorbar(x, y, yerr=[y - lo, hi - y], marker="o", color=COULEURS_ROUTEURS[r], capsize=2, label=NOMS_ROUTEURS[r])
        ax[1].plot(x, [agg[k][r]["rejets_par_ordre"] for k in tox], marker="o", color=COULEURS_ROUTEURS[r], label=NOMS_ROUTEURS[r])
        ax[2].plot(x, [agg[k][r]["delai_dernier_fill_ms"] for k in tox], marker="o", color=COULEURS_ROUTEURS[r], label=NOMS_ROUTEURS[r])
    ax[0].set(xlabel="toxicité du flux", ylabel="coût vs mid d'arrivée (pips)", title="Prix effectif payé vs prix affiché")
    ax[1].set(xlabel="toxicité du flux", ylabel="rejets par ordre", title="Rejets de last look")
    ax[2].set(xlabel="toxicité du flux", ylabel="ms jusqu'au dernier fill", title="Délai d'exécution")
    for a in ax:
        a.set_xticks(x)
    ax[0].legend(frameon=False, fontsize=8)
    _sauver(fig, chemin)
