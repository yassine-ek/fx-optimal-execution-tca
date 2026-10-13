"""Figures « vitrine » du README : hero_equity.png, toutes_variantes.png, overfit_scatter.png.

Lit UNIQUEMENT results/couts_quotidiens.csv et results/variantes_train_val.json : aucune donnée de marché, TEST jamais
chargé (le CSV s'arrête au 2022-12-30). Ici la « performance » est un COÛT : l'équivalent de la courbe d'equity est
le coût cumulé d'exécution, en euros (un achat + une vente de 50 M EUR par jour) et en bps cumulés (somme des
shortfalls quotidiens, en bps du notionnel d'un ordre).

Usage : python scripts/generer_figures_vitrine.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from execfx.figures import COULEURS  # noqa: E402

RESULTATS, FIGURES = RACINE / "results", RACINE / "figures"
DPI = 130
GRIS_TRAIN = "#e7e9ee"
MARQUEURS = {"lin": "o", "rac": "s", "lin_x05": "^", "lin_x2": "v"}


def f2(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}".replace(".", ",").replace("-", "−")


def charger():
    v = json.loads((RESULTATS / "variantes_train_val.json").read_text(encoding="utf-8"))
    csv = pd.read_csv(RESULTATS / "couts_quotidiens.csv", index_col=0, parse_dates=True)
    assert csv.index.max() < pd.Timestamp("2023-01-01"), "TEST interdit"
    return v, csv


def eur_par_bps(p: dict) -> float:
    """1 bp cumulé (somme des shortfalls quotidiens) = 2 ordres x notionnel x 1e-4 euros."""
    return 2 * p["notionnel_eur"] * 1e-4


def texte_frais(p: dict) -> str:
    return (f"demi-spread {f2(p['demi_spread_bps'], 1)} bp, impact temporaire {f2(p['eta_bps'], 0)} bps × participation, permanent {f2(p['gamma_bps'], 1)} bp, "
            f"{p['notionnel_eur'] / 1e6:.0f} M EUR par ordre, fenêtre {p['debut_heure_ny']}h-{p['debut_heure_ny'] + 1}h New York, barres BID 1 min, impact supposé")


def _axe_eur(ax, p):
    k = eur_par_bps(p) / 1e6
    sec = ax.secondary_yaxis("right", functions=(lambda y: y / k, lambda b: b * k))
    sec.set_ylabel("bps cumulés (somme des shortfalls quotidiens)")


def hero(v, csv):
    p, k = v["parametres"], eur_par_bps(v["parametres"]) / 1e6
    fin_train = pd.Timestamp(v["meta"]["periodes"]["TRAIN"][1])
    val = csv.loc[csv.index > fin_train]
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 7.4), sharex=True, gridspec_kw={"height_ratios": [3, 1.35], "hspace": 0.08})
    noms = list(v["strategies"])
    cum = {s: val[f"lin__{s}"].cumsum() * k for s in noms}
    for s in sorted(noms, key=lambda s: -cum[s].iloc[-1]):  # légende du plus cher au moins cher
        gras = s == "TWAP"
        lib = v["strategies"][s]["libelle"] + (" (référence)" if gras else "")
        ax.plot(cum[s].index, cum[s].values, color="#111111" if gras else COULEURS[s], lw=3.0 if gras else 1.7,
                zorder=5 if gras else 3, label=f"{lib} : {f2(cum[s].iloc[-1], 1)} M€")
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    ax.set_xlim(val.index[0], val.index[-1])
    ax.set_ylabel("coût cumulé d'exécution (M EUR)")
    ax.grid(alpha=0.3)
    _axe_eur(ax, p)
    ax.set_title(f"Un achat + une vente de {p['notionnel_eur'] / 1e6:.0f} M EUR EURUSD par jour : coût cumulé sur VAL 2019-2022 (hors échantillon)",
                 fontsize=11.5, pad=26)
    ax.text(0.5, 1.02, "frais : " + texte_frais(p), transform=ax.transAxes, ha="center", va="bottom", fontsize=8.2, color="0.25")
    # bas : coût moyen sur 60 jours, pour voir les régimes (VAL plus calme que TRAIN)
    for s in noms:
        gras = s == "TWAP"
        r = val[f"lin__{s}"].rolling(60).mean()
        ax2.plot(r.index, r.values, color="#111111" if gras else COULEURS[s], lw=2.2 if gras else 1.2)
    ax2.set_ylabel("coût du jour,\nmoyenne 60 jours (bps)")
    ax2.set_yscale("log")
    ax2.set_yticks([1, 2, 3, 5, 10, 15])
    ax2.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda y, _: f"{y:g}"))
    ax2.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax2.grid(alpha=0.3, which="major", axis="y")
    fig.savefig(FIGURES / "hero_equity.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def toutes_variantes(v, csv):
    p, k = v["parametres"], eur_par_bps(v["parametres"]) / 1e6
    fin_train = pd.Timestamp(v["meta"]["periodes"]["TRAIN"][1])
    fig, ax = plt.subplots(figsize=(11, 6.4))
    ax.axvspan(csv.index[0], fin_train, color=GRIS_TRAIN, zorder=0)
    ax.axvline(fin_train + pd.Timedelta(days=1), color="0.35", ls="--", lw=1, zorder=1)
    cum = csv.cumsum() * k
    for c in csv.columns:
        ax.plot(cum.index, cum[c].values, color="0.62", lw=0.9, alpha=0.9)
    for s in v["strategies"]:
        if s != "TWAP":
            ax.plot(cum.index, cum[f"lin__{s}"].values, color=COULEURS[s], lw=1.4, alpha=0.95)
    ax.plot(cum.index, cum["lin__TWAP"].values, color="#111111", lw=3.0, zorder=5, label="TWAP, impact linéaire (référence)")
    ax.plot([], [], color="0.62", lw=1, label="les 28 variantes (7 stratégies × 4 modèles d'impact)")
    ax.plot([], [], color=COULEURS["AC-lam2"], lw=1.4, label="les 7 stratégies, impact linéaire (couleurs)")
    ax.set_ylabel("coût cumulé d'exécution (M EUR)")
    ax.set_ylim(0)
    ax.set_xlim(csv.index[0], csv.index[-1])
    ax.grid(alpha=0.3)
    _axe_eur(ax, p)
    trans = ax.get_xaxis_transform()
    ax.text(csv.index[0] + (fin_train - csv.index[0]) / 2, 0.96, "TRAIN 2010-2018\n(profil et paramètres AC calibrés ici : in-sample)", transform=trans, ha="center", va="top", fontsize=9.5)
    ax.text(fin_train + (csv.index[-1] - fin_train) / 2, 0.96, "VAL 2019-2022\n(hors échantillon)", transform=trans, ha="center", va="top", fontsize=9.5)
    ax.legend(loc="center left", bbox_to_anchor=(0.01, 0.62), fontsize=9, frameon=False)
    fig.suptitle("Toutes les variantes testées : coût cumulé d'exécution, rien n'est écarté", fontsize=12.5, y=0.99)
    ax.set_title("frais : " + texte_frais(p), fontsize=8.2, color="0.25", pad=6)
    fig.savefig(FIGURES / "toutes_variantes.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def overfit_scatter(v):
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 6.2))
    var = v["variantes"]
    for x in var.values():
        c = COULEURS[x["strategie"]]
        t, a_ = x["TRAIN"]["shortfall_moyen_bps"], x["VAL"]["shortfall_moyen_bps"]
        a.scatter([t], [a_], s=62, marker=MARQUEURS[x["modele"]], color=c, edgecolor="white", linewidth=0.7, zorder=4)
        if x["modele"] == "lin" and x["strategie"] in ("AC-lam1", "AC-lam2", "AC-lam3", "IS-front-loaded"):
            a.annotate(v["strategies"][x["strategie"]]["court"], (t, a_), textcoords="offset points", xytext=(7, -11), fontsize=8.5, color=c)
    a.annotate("TWAP, VWAP, POV", (2.45, 2.45), textcoords="offset points", xytext=(18, -30), fontsize=8.5, color="0.3",
               arrowprops={"arrowstyle": "-", "color": "0.5", "lw": 0.8})
    lim = [0.9, 25]
    for ax, ref in ((a, "VAL = TRAIN (pas d'écart)"), (b, "réalisé = théorie (pas d'écart)")):
        ax.plot(lim, lim, color="0.4", ls="--", lw=1, label=ref)
        ax.set_xscale("log"), ax.set_yscale("log")
        ax.set_xlim(lim), ax.set_ylim(lim)
        ax.grid(alpha=0.3, which="both")
        for axe in (ax.xaxis, ax.yaxis):
            axe.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda y, _: f"{y:g}"))
    a.set_xlabel("coût moyen TRAIN, in-sample (bps)")
    a.set_ylabel("coût moyen VAL, hors échantillon (bps)")
    a.set_title("Réalisé : TRAIN contre VAL, 28 variantes", fontsize=11)
    for m, lab in (("lin", "impact linéaire"), ("rac", "racine carrée"), ("lin_x05", "linéaire ×0,5"), ("lin_x2", "linéaire ×2")):
        a.scatter([], [], marker=MARQUEURS[m], color="0.4", label=lab)
    a.legend(loc="upper left", fontsize=8.5, frameon=False)
    # droite : théorie (calibrée TRAIN, activité attendue) contre réalisé, familles d'impact linéaire (la théorie est linéaire)
    for x in var.values():
        if x["theorie"] is None or x["modele"] == "rac":
            continue
        c, e = COULEURS[x["strategie"]], x["theorie"]["E_theorique_bps"]
        b.scatter([e], [x["TRAIN"]["shortfall_moyen_bps"]], s=58, marker=MARQUEURS[x["modele"]], facecolors="none", edgecolors=c, linewidth=1.3, zorder=3)
        b.scatter([e], [x["VAL"]["shortfall_moyen_bps"]], s=58, marker=MARQUEURS[x["modele"]], color=c, edgecolor="white", linewidth=0.7, zorder=4)
    b.scatter([], [], marker="o", facecolors="none", edgecolors="0.3", label="réalisé TRAIN (in-sample)")
    b.scatter([], [], marker="o", color="0.3", label="réalisé VAL (hors échantillon)")
    for m, lab in (("lin_x05", "impact ×0,5"), ("lin", "impact ×1"), ("lin_x2", "impact ×2")):
        b.scatter([], [], marker=MARQUEURS[m], color="0.4", label=lab)
    b.set_xlabel("coût théorique attendu (bps), modèle calibré sur TRAIN, activité = 1")
    b.set_ylabel("coût moyen réalisé (bps)")
    b.set_title("Théorie contre réalisé : stratégies statiques, impact linéaire ×0,5 / ×1 / ×2", fontsize=11)
    b.legend(loc="upper left", fontsize=8.5, frameon=False)
    fig.suptitle("Overfit ? Le coût réalisé en VAL ressemble-t-il à celui du TRAIN, et à ce que la théorie annonçait ? (rien n'est écarté)", fontsize=12, y=1.0)
    fig.tight_layout()
    fig.savefig(FIGURES / "overfit_scatter.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    v, csv = charger()
    hero(v, csv)
    toutes_variantes(v, csv)
    overfit_scatter(v)
    print("figures/hero_equity.png, toutes_variantes.png, overfit_scatter.png écrites")


if __name__ == "__main__":
    main()
