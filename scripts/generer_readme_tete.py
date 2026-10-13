"""Écrit dans README.md les blocs de chiffres, LUS dans results/*.json (jamais tapés à la main).

Des blocs délimités par des balises HTML (invisibles sur GitHub) sont réécrits à chaque exécution, dans deux fichiers :
README.md
  <!-- AUTO:CLES -->       les 3 « résultats clés », chaque chiffre avec sa réserve
  <!-- AUTO:FRAIS -->      encadré frais et hypothèses (8 lignes)
  <!-- AUTO:TETE -->       tableau de métriques TRAIN | VAL par stratégie (impact linéaire, 7 colonnes)
  <!-- AUTO:TABLES -->     tableaux complets (9 colonnes, impacts linéaire et racine carrée), repliés dans <details>
  <!-- AUTO:ROBUSTE -->    « Overfit ou pas ? » : théorie calibrée sur TRAIN contre réalisé TRAIN et VAL
  <!-- AUTO:VARIANTES -->  tableau des 28 variantes (7 stratégies x 4 modèles d'impact), replié dans <details>
docs/details.md
  <!-- AUTO:FRAIS_DETAIL --> encadré détaillé des hypothèses
  <!-- AUTO:LECTURE -->    lecture chiffrée des résultats VAL (frontière, VWAP, IS, risque de modèle)
  <!-- AUTO:SOR -->        agrégateur de liquidité : prix effectif, rejets, délai par routeur
Aucune donnée de marché requise, TEST jamais chargé. Sources : results/variantes_train_val.json et results/verdict_execution.json.

Usage : python scripts/generer_readme_tete.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
RESULTATS = RACINE / "results"
# fichier cible -> blocs AUTO qu'il contient (le test de fraîcheur relit exactement cette table)
DESTINATIONS = {
    "README.md": ("CLES", "FRAIS", "TETE", "TABLES", "ROBUSTE", "VARIANTES"),
    "docs/details.md": ("FRAIS_DETAIL", "LECTURE", "SOR"),
}
MODELES = ("lin", "rac")  # modèles détaillés en tête ; les sensibilités sont dans le tableau des variantes
NOMS_ROUTEURS = {"a_meilleur_affiche": "(a) meilleur prix affiché", "b_prix_effectif": "(b) prix effectif", "c_split": "(c) split 3 LP"}


# ------------------------------------------------------------------ formats français
def n(x, d=2):
    if x is None:
        return "n/d"
    return f"{x:.{d}f}".replace(".", ",").replace("-", "−")


def ns(x, d=2):
    """Nombre signé : +0,43 / −0,12."""
    s = n(x, d)
    return s if s.startswith("−") else "+" + s


def ic(b, d=2, signe=False):
    f = ns if signe else n
    return f"[{f(b[0], d)} ; {f(b[1], d)}]"


def pct(x, d=0):
    return n(100 * x, d) + " %"


def entier(x):
    return f"{round(x):,}".replace(",", " ")


def charger():
    v = json.loads((RESULTATS / "variantes_train_val.json").read_text(encoding="utf-8"))
    o = json.loads((RESULTATS / "verdict_execution.json").read_text(encoding="utf-8"))
    return v, o


def var(v, modele, strat):
    return v["variantes"][f"{modele}__{strat}"]


def lib(v, strat):
    return v["strategies"][strat]["libelle"]


# ------------------------------------------------------------------ bloc CLES
def reconstruction_proxy_volume(v, periode: str) -> dict:
    """Coût TWAP (impact linéaire) RECONSTRUIT à partir de la seule théorie et du facteur d'activité : preuve que l'écart théorie / réalisé vient du proxy de volume.

    Réalisé = impact temporaire théorique x E[1/m] + (demi-spread + impact permanent), où m est l'activité de prix du jour (le « volume » simulé).
    Pour un TWAP le permanent vaut gamma x (N-1)/(2N) et ne dépend pas de m ; l'égalité est exacte, pas un ajustement.
    """
    p = v["parametres"]
    N, fixe_spread = p["horizon_min"], p["demi_spread_bps"]
    permanent = p["gamma_bps"] * (N - 1) / (2 * N)
    theorie = var(v, "lin", "TWAP")["theorie"]["E_theorique_bps"]
    temporaire = theorie - fixe_spread - permanent
    inv_m = v["regime"][periode]["inverse_m_moyen"]
    return {"temporaire": temporaire, "inverse_m": inv_m, "fixe": fixe_spread + permanent, "reconstruit": temporaire * inv_m + fixe_spread + permanent,
            "realise": var(v, "lin", "TWAP")[periode]["shortfall_moyen_bps"], "theorie": theorie}


def ecarts_sor(o) -> tuple[list[float], list[float]]:
    """(écart prix obtenu - meilleur prix affiché en pips, part d'ordres avec rejet) du routeur (a), un par niveau de toxicité."""
    res = o["agregation"]["resultats"]
    a = [res[t]["a_meilleur_affiche"] for t in res]
    return [x["prix_effectif_pips"]["moyenne"] - x["meilleur_affiche_pips"] for x in a], [x["ordres_avec_rejet"] for x in a]


def bloc_cles(v, o) -> str:
    tw, ac2 = var(v, "lin", "TWAP")["VAL"], var(v, "lin", "AC-lam2")["VAL"]
    rob = v["robustesse"]
    rec = reconstruction_proxy_volume(v, "VAL")
    ecarts, taux = ecarts_sor(o)
    return "\n".join([
        f"- **Frontière coût / risque retrouvée sur {entier(v['meta']['jours_utilises']['VAL'])} jours hors échantillon (VAL 2019-2022).** TWAP : {n(tw['shortfall_moyen_bps'])} bps, écart-type {n(tw['ecart_type_bps'])} ; "
        f"Almgren-Chriss λ=0,05 : {n(ac2['shortfall_moyen_bps'])} bps, écart-type {n(ac2['ecart_type_bps'])}, soit un risque de prix divisé par {n(tw['ecart_type_bps'] / ac2['ecart_type_bps'], 1)} "
        f"pour un coût multiplié par {n(ac2['shortfall_moyen_bps'] / tw['shortfall_moyen_bps'], 1)}. "
        f"*Réserve : l'impact (η) et la taille du pool de liquidité sont des hypothèses, donc ces niveaux en bps sont **indicatifs** ; seuls le classement des stratégies "
        f"(corrélation de rang TRAIN → VAL : {n(rob['lin']['spearman_cout_moyen_train_val'])} en impact linéaire, {n(rob['rac']['spearman_cout_moyen_train_val'])} en racine carrée) "
        "et la forme de la frontière sont robustes. Pour situer : en pratique, un ordre de 50 M EUR coûte de l'ordre de quelques dixièmes de bp à quelques bps selon l'heure "
        "(ordre de grandeur qualitatif, non estimé ici).*",
        f"- **Le coût réalisé dépasse la théorie de {pct(rec['realise'] / rec['theorie'] - 1)} en VAL, et c'est le proxy de volume qui l'explique.** Le FX n'a pas de volume centralisé : le « volume » simulé suit l'activité de prix du jour m, "
        f"l'impact varie en 1/m et la moyenne de 1/m dépasse 1/(moyenne de m) (E[1/m] = {n(rec['inverse_m'])} en VAL). Le coût TWAP réalisé se reconstruit à partir de la théorie : "
        f"{n(rec['temporaire'], 3)} × {n(rec['inverse_m'], 3)} + {n(rec['fixe'], 3)} = {n(rec['reconstruit'], 3)} bps contre {n(rec['realise'], 3)} mesurés. "
        "*Réserve : c'est une propriété du modèle de volume, pas une observation de marché.*",
        f"- **Agrégateur de 8 fournisseurs de liquidité FICTIFS avec last look : le prix obtenu est plus cher que le meilleur prix affiché de {n(min(ecarts), 2)} à {n(max(ecarts), 2)} pip, "
        f"et {pct(min(taux))} à {pct(max(taux))} des ordres subissent au moins un rejet.** "
        "*Réserve : les paramètres des 8 LP sont inventés, l'écart est donc un paramètre d'entrée et non un résultat ; seule la mécanique (cote périmée + last look, "
        "écart croissant avec la toxicité du flux) est démontrée.*",
    ])


# ------------------------------------------------------------------ blocs FRAIS (8 lignes) et FRAIS_DETAIL
def bloc_frais(v) -> str:
    p, m = v["parametres"], v["meta"]
    pr, ju = m["periodes"], m["jours_utilises"]
    return "\n".join([
        "| Hypothèse | Valeur |",
        "|---|---|",
        f"| Ordre | {p['notionnel_eur'] / 1e6:.0f} M EUR d'EURUSD, **un achat ET une vente rejoués chaque jour**, {p['horizon_min']} tranches d'une minute, "
        f"fenêtre {p['debut_heure_ny']}h-{p['debut_heure_ny'] + 1}h New York, prix d'arrivée = clôture de 7h59, la tranche k ne voit que le passé |",
        f"| Impact **supposé** | temporaire linéaire η = {n(p['eta_bps'], 0)} bps à 100 % de participation (modèle principal) ; racine carrée **appliquée par tranche d'une minute** "
        f"(impact transitoire à décroissance complète, pas la loi de l'ordre parent), y = {n(p['y_racine'], 3)}, calibrée sur le linéaire ; permanent {n(p['gamma_bps'], 1)} bp ; "
        "sensibilités ×0,5 et ×2. **Aucun fill réel : niveaux absolus indicatifs** |",
        f"| Liquidité **supposée** | pool accessible de {p['volume_jour_eur'] / 1e9:.0f} Md EUR par jour (le marché fait environ 1 000 Md), participation TWAP nominale {pct(p['participation_twap_nominale'], 1)} ; "
        "volume d'une minute = pool × profil × activité de prix du jour (**proxy** : la colonne volume vaut 0) |",
        f"| Coûts | demi-spread {n(p['demi_spread_bps'], 1)} bp constant (supposé, barres BID) + impact ci-dessus ; agrégateur : **8 fournisseurs fictifs** avec rejets simulés |",
        f"| Données et découpage | HistData EURUSD 1 min, prix BID, heure de New York · **TRAIN** {pr['TRAIN'][0][:4]}-{pr['TRAIN'][1][:4]} (profil et paramètres Almgren-Chriss calibrés ici : in-sample) · "
        f"**VAL** {pr['VAL'][0][:4]}-{pr['VAL'][1][:4]} ({entier(ju['VAL'])} jours, hors échantillon) · **TEST 2023+ scellé** |",
        f"| Statistiques | shortfall en bps du notionnel (positif = on paie), achat et vente moyennés, IC95 par bootstrap en blocs de 5 jours ; {len(v['variantes'])} variantes toutes publiées, aucune choisie sur VAL (pas de DSR) |",
    ])


def encadre_frais(v) -> str:
    p, m = v["parametres"], v["meta"]
    pr = m["periodes"]
    ju, jo = m["jours_utilises"], m["jours_ouvres"]
    return "\n".join([
        "| Hypothèse | Valeur |",
        "|---|---|",
        f"| Ordre | {p['notionnel_eur'] / 1e6:.0f} M EUR d'EURUSD, **un achat ET une vente rejoués chaque jour**, {p['horizon_min']} tranches d'une minute, "
        f"fenêtre {p['debut_heure_ny']}h00-{p['debut_heure_ny'] + 1}h00 heure de New York (les annonces US de 8h30 y sont), prix d'arrivée = clôture de 7h59 |",
        f"| Demi-spread | {n(p['demi_spread_bps'], 1)} bp du notionnel, constant et identique pour toutes les stratégies (**hypothèse** : les barres BID ne contiennent pas de spread réel) |",
        f"| Impact supposé | temporaire **linéaire** : {n(p['eta_bps'], 0)} bps × participation (modèle principal) ; **racine carrée** : y·σ·√participation avec y = {n(p['y_racine'], 3)}, "
        f"calibré pour égaler le linéaire au TWAP nominal, **appliqué tranche par tranche (une minute)** : c'est un impact transitoire à décroissance complète, pas la loi de l'ordre parent "
        f"(voir « Loi racine carrée » plus bas) ; permanent linéaire : {n(p['gamma_bps'], 1)} bp pour l'ordre complet. Sensibilités : impact ×0,5 et ×2. "
        "**Aucun impact n'est estimé sur des fills : les niveaux absolus en bps sont indicatifs** |",
        f"| Liquidité | {p['volume_jour_eur'] / 1e9:.0f} Md EUR par jour accessibles (hypothèse ; le marché fait environ 1 000 Md) donc participation TWAP nominale "
        f"{pct(p['participation_twap_nominale'], 1)} ; volume d'une minute = volume du jour × part de la minute (profil d'activité TRAIN) × activité réalisée du jour |",
        "| Données | HistData EURUSD 1 minute, prix **BID** ; le FX est OTC, la colonne volume vaut 0 : l'activité de prix sert de proxy ; horloge = heure locale de New York "
        "(heure d'été comprise), vérifiée sur le NFP et l'ouverture hebdomadaire |",
        f"| Découpage | **TRAIN** {pr['TRAIN'][0][:4]}-{pr['TRAIN'][1][:4]} ({entier(ju['TRAIN'])} jours utilisables sur {entier(jo['TRAIN'])} : profil, σ et θ d'Almgren-Chriss calibrés ici, "
        f"donc le rejeu TRAIN est **in-sample**) · **VAL** {pr['VAL'][0][:4]}-{pr['VAL'][1][:4]} ({entier(ju['VAL'])} jours sur {entier(jo['VAL'])} : évaluation hors échantillon) · "
        "**TEST 2023+ : scellé**, le chargeur refuse l'année |",
        "| Délai d'exécution | la tranche k est décidée avec les clôtures jusqu'à la minute précédente (testé), exécutée au prix de la barre ; aucune latence sous la minute dans le simulateur de coûts "
        "(l'agrégateur, lui, simule la milliseconde) |",
        "| Statistiques | shortfall en bps du notionnel, positif = on paie ; achat et vente moyennés (la dérive du prix s'annule : la moyenne mesure l'impact, l'écart-type le risque de prix) ; "
        "IC95 par bootstrap en blocs de 5 jours (1 000 tirages), mêmes blocs pour toutes les stratégies, donc variabilité d'échantillonnage des jours seulement, pas incertitude sur le modèle d'impact ; "
        "coût total en EUR = jours × (1 achat + 1 vente) × 50 M EUR × shortfall moyen |",
        f"| Essais | {len(v['variantes'])} variantes ({len(v['strategies'])} stratégies × {len(v['modeles'])} modèles d'impact), toutes publiées, **aucune choisie sur VAL** : pas de DSR (rien à déflater) |",
    ])


# ------------------------------------------------------------------ blocs TETE (7 colonnes) et TABLES (9 colonnes, repliés)
def tableau_court(v) -> str:
    lignes = [
        "| Stratégie | Coût moyen TRAIN | Coût moyen VAL [IC95] | Écart-type TRAIN | Écart-type VAL | p95 VAL | Coût total VAL (M EUR) |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in v["strategies"]:
        x = var(v, "lin", s)
        t, a = x["TRAIN"], x["VAL"]
        lignes.append(f"| {lib(v, s)} | {n(t['shortfall_moyen_bps'])} | {n(a['shortfall_moyen_bps'])} {ic(a['ic95_moyen_bps'])} | {n(t['ecart_type_bps'])} | {n(a['ecart_type_bps'])} | "
                      f"{n(a['p95_bps'], 1)} | {n(a['cout_total_eur'] / 1e6, 1)} |")
    return "\n".join(lignes)


def bloc_tete(v) -> str:
    notes = ("*Shortfall en bps du notionnel (positif = coût), achats et ventes poolés ; l'écart-type est celui d'un seul ordre ; coût total VAL en M EUR pour un achat et une vente de 50 M EUR par jour. "
             "L'impact étant supposé, **lire le classement et la forme coût / risque, pas les niveaux absolus**. Tableaux complets (IC95 de l'écart à TWAP, p95 TRAIN, impact racine carrée) juste dessous.*")
    return "\n\n".join([tableau_court(v), notes])


def tableau_modele(v, modele) -> str:
    lib_m = v["modeles"][modele]["libelle"]
    lignes = [
        f"### Coût d'exécution par stratégie, impact {lib_m}, TRAIN | VAL côte à côte",
        "",
        "| Stratégie | Shortfall moyen TRAIN [IC95] | Shortfall moyen VAL [IC95] | Écart-type TRAIN | Écart-type VAL | p95 TRAIN | p95 VAL | Coût total VAL (M EUR) | Δ vs TWAP VAL [IC95] |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in v["strategies"]:
        x = var(v, modele, s)
        t, a = x["TRAIN"], x["VAL"]
        d = a["diff_moyen_vs_twap_bps"]
        dec = 3 if max(abs(d), *map(abs, a["ic95_diff_moyen_vs_twap_bps"])) < 0.05 else 2  # écart minuscule : 3 décimales
        delta = "référence" if s == "TWAP" else f"{ns(d, dec)} {ic(a['ic95_diff_moyen_vs_twap_bps'], dec, True)}"
        lignes.append(f"| {lib(v, s)} | {n(t['shortfall_moyen_bps'])} {ic(t['ic95_moyen_bps'])} | {n(a['shortfall_moyen_bps'])} {ic(a['ic95_moyen_bps'])} | "
                      f"{n(t['ecart_type_bps'])} | {n(a['ecart_type_bps'])} | {n(t['p95_bps'], 1)} | {n(a['p95_bps'], 1)} | {n(a['cout_total_eur'] / 1e6, 1)} | {delta} |")
    return "\n".join(lignes)


def bloc_tables(v) -> str:
    notes = ("*Les IC95 (bootstrap par blocs de 5 jours) ne mesurent que la variabilité d'échantillonnage des jours, pas l'incertitude sur le modèle d'impact, qui est supposé. "
             "Comparer deux coûts moyens est circulaire (TWAP est Almgren-Chriss à λ → 0, donc tout λ > 0 coûte plus cher en moyenne) : l'information est la frontière coût / risque.*")
    return "\n".join(["<details>", "<summary>Tableaux complets (9 colonnes) : impact linéaire et impact racine carrée par tranche</summary>", "",
                      tableau_modele(v, "lin"), "", tableau_modele(v, "rac"), "", notes, "", "</details>"])


# ------------------------------------------------------------------ bloc ROBUSTE
def interpolation_ac(v, modele, moyenne) -> float | None:
    """Écart-type VAL de la frontière empirique AC (interpolation linéaire entre les points AC voisins) au coût `moyenne`."""
    pts = sorted((var(v, modele, s)["VAL"]["shortfall_moyen_bps"], var(v, modele, s)["VAL"]["ecart_type_bps"]) for s in ("AC-lam1", "AC-lam2", "AC-lam3"))
    for (m0, s0), (m1, s1) in zip(pts, pts[1:]):
        if m0 <= moyenne <= m1:
            return s0 + (moyenne - m0) / (m1 - m0) * (s1 - s0)
    return None


def bloc_robuste(v) -> str:
    tw = var(v, "lin", "TWAP")
    e, sd = tw["theorie"]["E_theorique_bps"], tw["theorie"]["std_theorique_bps"]
    t, a = tw["TRAIN"], tw["VAL"]
    reg, rob = v["regime"], v["robustesse"]
    rapports = list(rob["lin"]["rapport_val_sur_train_cout_moyen"].values())
    gag_t, gag_v = rob["lin"]["meilleure_par_lambda_train"], rob["lin"]["meilleure_par_lambda_val"]
    memes = gag_t == gag_v
    ac2, ac3 = var(v, "lin", "AC-lam2")["VAL"], var(v, "lin", "AC-lam3")["VAL"]
    repliee = ac3["ecart_type_bps"] > ac2["ecart_type_bps"]
    rac3 = var(v, "rac", "AC-lam3")["VAL"]
    lams = " / ".join(k.split("=")[1].replace(".", ",") for k in gag_v)
    gagnants = f"pour λ = {lams}, " + " / ".join(lib(v, gag_v[k]) for k in gag_v)
    optimum = " / ".join(lib(v, f"AC-lam{i}") for i, _ in enumerate(gag_v, start=1))
    rec_t, rec_v = reconstruction_proxy_volume(v, "TRAIN"), reconstruction_proxy_volume(v, "VAL")
    lignes = [
        f"1. **La théorie calibrée sur TRAIN se trompe dans les deux sens hors échantillon, et l'écart de coût vient du proxy de volume.** TWAP : coût théorique {n(e)} bps et écart-type {n(sd, 1)} ; "
        f"réalisé en TRAIN (in-sample) {n(t['shortfall_moyen_bps'])} et {n(t['ecart_type_bps'], 1)} ; réalisé en VAL {n(a['shortfall_moyen_bps'])} et {n(a['ecart_type_bps'], 1)}. "
        f"Le coût est {pct(a['shortfall_moyen_bps'] / e - 1)} au-dessus de la théorie en VAL (déjà {pct(t['shortfall_moyen_bps'] / e - 1)} en TRAIN) et le risque {pct(1 - a['ecart_type_bps'] / sd)} en dessous. "
        f"*Attribution du coût :* le FX n'a pas de volume centralisé, le « volume » simulé est donc proportionnel à l'activité de prix du jour m et l'impact varie en 1/m. La moyenne de 1/m dépasse l'inverse de la moyenne de m "
        f"que la théorie suppose (inégalité de Jensen : E[1/m] = {n(reg['TRAIN']['inverse_m_moyen'])} en TRAIN pour une activité moyenne de {n(reg['TRAIN']['m_moyen'])}, {n(reg['VAL']['inverse_m_moyen'])} en VAL pour {n(reg['VAL']['m_moyen'])}). "
        f"Cela suffit : impact temporaire théorique {n(rec_v['temporaire'], 3)} × E[1/m] + {n(rec_v['fixe'], 3)} (demi-spread et impact permanent) = {n(rec_v['reconstruit'], 3)} bps en VAL pour {n(rec_v['realise'], 3)} mesurés "
        f"({n(rec_t['reconstruit'], 3)} contre {n(rec_t['realise'], 3)} en TRAIN). L'écart est donc une **conséquence du modèle de volume**, pas une observation de marché. "
        f"*Attribution du risque :* VAL est plus calme (σ de fenêtre {n(reg['VAL']['sigma_rms_fenetre_bps'])} contre {n(reg['TRAIN']['sigma_rms_fenetre_bps'])} bps/min), donc moins de risque de prix.",
        f"2. **Le classement, lui, tient.** Corrélation de rang (Spearman) des 7 coûts moyens TRAIN / VAL : {n(rob['lin']['spearman_cout_moyen_train_val'])} en impact linéaire, "
        f"{n(rob['rac']['spearman_cout_moyen_train_val'])} en racine carrée ; le coût VAL vaut {n(min(rapports))} à {n(max(rapports))} fois le coût TRAIN selon la stratégie (linéaire). "
        + ("Les gagnants par aversion au risque (utilité E + λ·Var) sont les mêmes en TRAIN et en VAL : " + gagnants
           if memes else "Les gagnants par aversion au risque (utilité E + λ·Var) diffèrent entre TRAIN et VAL ; en VAL " + gagnants)
        + f" (l'optimum du modèle serait {optimum}).",
        "3. **Choisi avant de lire VAL : les paramètres.** Taille, fenêtre, modèles d'impact et leurs paramètres, valeurs de λ, stratégies sont des constantes du code (`execfx/impact.py`, `execfx/experiences.py`), "
        "aucune n'a été ajustée pour améliorer un résultat VAL (une seule exécution de référence) ; la seule modification venue après un premier calcul est la correction du fuseau du 13/10 (elle déplace la fenêtre, pas les paramètres). "
        f"Les {len(v['variantes'])} variantes sont toutes publiées, aucune n'est retenue sur son résultat VAL, TEST scellé. Le vrai point faible n'est pas un surajustement mais l'**impact supposé** : "
        f"AC λ=0,3 coûte {n(ac3['shortfall_moyen_bps'])} bps en linéaire et {n(rac3['shortfall_moyen_bps'])} en racine carrée, et "
        + ("la frontière coût / risque empirique se replie : AC λ=0,3 est plus risquée (" + n(ac3['ecart_type_bps']) + ") qu'AC λ=0,05 (" + n(ac2['ecart_type_bps']) + ") car l'impact varie d'un jour à l'autre, ce que la théorie ignore."
           if repliee else "la frontière coût / risque empirique reste décroissante comme la théorie."),
        "",
        "| Stratégie (impact linéaire) | Coût théorique | Réalisé TRAIN | Réalisé VAL | Écart-type théorique | Écart-type TRAIN | Écart-type VAL |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in v["strategies"]:
        x = var(v, "lin", s)
        th = x["theorie"]
        lignes.append(f"| {lib(v, s)} | {n(th['E_theorique_bps']) if th else 'n/d (adaptative)'} | {n(x['TRAIN']['shortfall_moyen_bps'])} | {n(x['VAL']['shortfall_moyen_bps'])} | "
                      f"{n(th['std_theorique_bps']) if th else 'n/d'} | {n(x['TRAIN']['ecart_type_bps'])} | {n(x['VAL']['ecart_type_bps'])} |")
    lignes += ["", "*bps du notionnel. La théorie (formules d'Almgren-Chriss avec les σ et θ du TRAIN, activité du jour = 1) n'existe que pour les plannings statiques ; POV s'adapte à l'activité observée.*"]
    return "\n".join(lignes)


# ------------------------------------------------------------------ bloc VARIANTES
def bloc_variantes(v) -> str:
    lignes = ["| Variante | Impact | Shortfall moyen TRAIN | Shortfall moyen VAL | Écart-type TRAIN | Écart-type VAL | p95 VAL | Coût total VAL (M EUR) | Rapport VAL / TRAIN |",
              "|---|---|---|---|---|---|---|---|---|"]
    for mid in v["modeles"]:
        for s in v["strategies"]:
            x = var(v, mid, s)
            t, a = x["TRAIN"], x["VAL"]
            gras = "**" if (mid == "lin" and s == "TWAP") else ""
            lignes.append(f"| {gras}{x['id']}{gras} | {x['modele_libelle']} | {n(t['shortfall_moyen_bps'])} | {n(a['shortfall_moyen_bps'])} | {n(t['ecart_type_bps'])} | "
                          f"{n(a['ecart_type_bps'])} | {n(a['p95_bps'], 1)} | {n(a['cout_total_eur'] / 1e6, 1)} | {n(a['shortfall_moyen_bps'] / t['shortfall_moyen_bps'])} |")
    lignes += ["", "*bps du notionnel, sauf le coût total (M EUR). TWAP en impact linéaire (en gras) est la référence. Colonnes « Impact » : linéaire = modèle principal, racine carrée = calibrée dessus, "
               "×0,5 et ×2 = impacts linéaires multipliés.*"]
    return "\n".join(lignes)


# ------------------------------------------------------------------ bloc LECTURE
def bloc_lecture(v) -> str:
    r = {s: var(v, "lin", s)["VAL"] for s in v["strategies"]}
    rr = {s: var(v, "rac", s)["VAL"] for s in v["strategies"]}
    ac1, ac2, ac3 = r["AC-lam1"], r["AC-lam2"], r["AC-lam3"]
    tw, vw, isf = r["TWAP"], r["VWAP-proxy"], r["IS-front-loaded"]
    mini = min(r, key=lambda s: r[s]["shortfall_moyen_bps"])
    calme = min(r, key=lambda s: r[s]["ecart_type_bps"])
    interp = interpolation_ac(v, "lin", isf["shortfall_moyen_bps"])
    repliee = ac3["ecart_type_bps"] > ac2["ecart_type_bps"]
    ordre_lin = sorted(r, key=lambda s: r[s]["ecart_type_bps"])
    ordre_rac = sorted(rr, key=lambda s: rr[s]["ecart_type_bps"])
    sens = {k: {s: var(v, k, s)["VAL"] for s in v["strategies"]} for k in ("lin_x05", "lin_x2")}
    gag_rac = v["robustesse"]["rac"]["meilleure_par_lambda_val"]
    gag_lin = v["robustesse"]["lin"]["meilleure_par_lambda_val"]
    lignes = [
        f"- **L'arbitrage d'Almgren-Chriss se retrouve sur données réelles, jusqu'à un point.** (Comparer les coûts moyens seuls est circulaire : TWAP est Almgren-Chriss à λ → 0 ; l'information est la frontière coût / risque.) Le coût moyen le plus bas est celui de {lib(v, mini)} ({n(r[mini]['shortfall_moyen_bps'])} bps), "
        f"le risque le plus bas celui de {lib(v, calme)} (écart-type {n(r[calme]['ecart_type_bps'])}, mais coût {n(r[calme]['shortfall_moyen_bps'])}). "
        f"De TWAP à AC λ=0,05 le risque baisse ({n(tw['ecart_type_bps'])} → {n(ac2['ecart_type_bps'])} bps) et le coût est multiplié par {n(ac2['shortfall_moyen_bps'] / tw['shortfall_moyen_bps'], 1)} "
        f"({n(tw['shortfall_moyen_bps'])} → {n(ac2['shortfall_moyen_bps'])}). "
        + (f"Plus loin (AC λ=0,3) le risque *remonte* ({n(ac3['ecart_type_bps'])}) : l'écart-type du shortfall mêle le risque de prix ({n(ac3['ecart_type_marche_bps'])} bps contre "
           f"{n(var(v, 'lin', 'AC-lam3')['theorie']['std_theorique_bps'])} en théorie) et la variabilité jour à jour de l'impact ({n(ac3['ecart_type_impact_jour_bps'])} bps, absente de la théorie car le volume du jour fluctue) ; "
           f"le coût moyen explose ({n(ac3['shortfall_moyen_bps'])})."
           if repliee else f"AC λ=0,3 réduit encore le risque ({n(ac3['ecart_type_bps'])}) pour un coût de {n(ac3['shortfall_moyen_bps'])}."),
        f"- **VWAP-proxy : un peu moins cher que le TWAP, mais plus risqué.** Écart de coût moyen {ns(vw['diff_moyen_vs_twap_bps'], 3)} bp, IC95 {ic(vw['ic95_diff_moyen_vs_twap_bps'], 3, True)} "
        f"(apparié, bootstrap par blocs), soit {n(100 * abs(vw['diff_moyen_vs_twap_bps']) / tw['ecart_type_bps'], 1)} % de l'écart-type du shortfall TWAP ; écart-type {n(vw['ecart_type_bps'])} contre {n(tw['ecart_type_bps'])}. "
        "Il concentre l'ordre sur les minutes actives, dont 8h30 : moins d'impact là où le volume est fort, plus de risque là où σ est fort. Effet économiquement faible.",
        f"- **IS front-loaded : au-dessus de la frontière Almgren-Chriss.** Coût moyen {n(isf['shortfall_moyen_bps'])}, écart-type {n(isf['ecart_type_bps'])} ; "
        + (f"une exécution Almgren-Chriss interpolée au même coût moyen aurait un écart-type d'environ {n(interp, 1)}." if interp is not None else "hors du segment AC, pas d'interpolation.")
        + " Le planning heuristique (40 % de l'ordre dans les 10 premières minutes) paie son urgence sans l'optimiser.",
        f"- **Le risque de modèle est le vrai sujet.** En impact racine carrée (appliqué par tranche d'une minute, voir « Loi racine carrée »), AC λ=0,3 coûte {n(rr['AC-lam3']['shortfall_moyen_bps'])} bps au lieu de {n(ac3['shortfall_moyen_bps'])}, "
        f"le classement des risques {'est le même' if ordre_lin == ordre_rac else 'change pour les stratégies les plus agressives'} "
        f"(AC λ=0,3 : écart-type {n(rr['AC-lam3']['ecart_type_bps'])}, la moins risquée) et les gagnants par λ deviennent "
        + ", ".join(lib(v, gag_rac[k]) for k in gag_rac) + " (en linéaire : " + ", ".join(lib(v, gag_lin[k]) for k in gag_lin) + "). "
        f"Avec l'impact linéaire ×0,5 / ×2, le TWAP coûte {n(sens['lin_x05']['TWAP']['shortfall_moyen_bps'])} / {n(sens['lin_x2']['TWAP']['shortfall_moyen_bps'])} bps et AC λ=0,3 "
        f"{n(sens['lin_x05']['AC-lam3']['shortfall_moyen_bps'])} / {n(sens['lin_x2']['AC-lam3']['shortfall_moyen_bps'])}. "
        "L'urgence optimale dépend donc du modèle d'impact, qu'on ne peut pas estimer sans données de fills ; le planning Almgren-Chriss restant dérivé sous impact linéaire, il est mal spécifié sous l'impact concave.",
    ]
    return "\n".join(lignes)


# ------------------------------------------------------------------ bloc SOR
def bloc_sor(o) -> str:
    res = o["agregation"]["resultats"]
    lignes = ["| Toxicité | Routeur | Meilleur prix affiché (pips) | Prix obtenu [IC95] (pips) | Rejets par ordre | Ordres avec rejet | Remplissage | Délai jusqu'au dernier fill (ms) |",
              "|---|---|---|---|---|---|---|---|"]
    for tox, bloc in res.items():
        for r, nom in NOMS_ROUTEURS.items():
            x = bloc[r]
            p = x["prix_effectif_pips"]
            lignes.append(f"| {tox.split('=')[1].replace('.', ',')} | {nom} | {ns(x['meilleur_affiche_pips'], 3)} | {ns(p['moyenne'], 3)} {ic(p['ic95'], 3, True)} | "
                          f"{n(x['rejets_par_ordre'])} | {pct(x['ordres_avec_rejet'])} | {n(100 * x['taux_remplissage'], 2)} % | {n(x['delai_dernier_fill_ms'], 0)} |")
    lignes += ["", "*Ordres de 20 M EUR, 20 000 ordres VAL par niveau de toxicité, coût en pips contre le mid d'arrivée (positif = on paie plus cher), mêmes aléas rejoués pour les 3 routeurs. "
               "Paramètres des 8 LP **inventés** (3 à last look agressif, 2 modérés, 3 prix fermes).*", ""]
    k = list(res)
    a1, a9 = res[k[0]]["a_meilleur_affiche"], res[k[-1]]["a_meilleur_affiche"]
    b9, c9 = res[k[-1]]["b_prix_effectif"], res[k[-1]]["c_split"]
    ecarts = [res[t]["a_meilleur_affiche"]["prix_effectif_pips"]["moyenne"] - res[t]["a_meilleur_affiche"]["meilleur_affiche_pips"] for t in k]
    taux = [res[t]["a_meilleur_affiche"]["ordres_avec_rejet"] for t in k]
    tox = [t.split("=")[1].replace(".", ",") for t in k]
    dz = [res[t]["desaccord_a_vs_b"] for t in k]
    lignes += [
        f"- **Le meilleur prix affiché n'est pas le prix obtenu.** Le meilleur prix affiché est meilleur que le mid ({ns(a1['meilleur_affiche_pips'], 3)} pip, cote périmée ou bruitée), "
        f"mais le prix obtenu est plus cher de {n(min(ecarts), 2)} à {n(max(ecarts), 2)} pip selon la toxicité, et {pct(min(taux))} à {pct(max(taux))} des ordres subissent au moins un rejet.",
        f"- **Le routeur (b) apporte surtout de la fiabilité, pas du prix** : moins de rejets ({n(b9['rejets_par_ordre'])} contre {n(a9['rejets_par_ordre'])} par ordre à toxicité {tox[-1]}) "
        f"et moins de délai ({n(b9['delai_dernier_fill_ms'], 0)} contre {n(a9['delai_dernier_fill_ms'], 0)} ms). Son gain de coût est de l'ordre du millième de pip : (a) et (b) ne choisissent pas le même LP pour "
        + " / ".join(pct(d['part_ordres']) for d in dz) + f" des ordres (toxicité {' / '.join(tox)}) et sur ceux-là (a) coûte "
        + " / ".join(f"{ns(d['cout_a_moins_cout_b_pips']['moyenne'], 4)} {ic(d['cout_a_moins_cout_b_pips']['ic95'], 4, True)}" for d in dz)
        + " pip de plus. Détectable seulement à toxicité forte.",
        f"- **Le split (c) est dominé ici** : prix obtenu {n(c9['prix_effectif_pips']['moyenne'], 3)} contre {n(b9['prix_effectif_pips']['moyenne'], 3)} pip pour (b) à toxicité {tox[-1]}, "
        "sans réduction de dispersion. Le modèle ne valorise pas ce qu'un split apporte en pratique (moins de fuite d'information, profondeur).",
        "- **Ces niveaux dépendent de LP inventés** : seule la mécanique (cote périmée + last look, donc écart affiché / obtenu qui croît avec la toxicité) est démontrée, pas des niveaux de pips réalistes.",
    ]
    return "\n".join(lignes)


# ------------------------------------------------------------------ injection
def blocs(v, o) -> dict[str, str]:
    return {"CLES": bloc_cles(v, o), "FRAIS": bloc_frais(v), "TETE": bloc_tete(v), "TABLES": bloc_tables(v), "ROBUSTE": bloc_robuste(v),
            "VARIANTES": bloc_variantes(v), "FRAIS_DETAIL": encadre_frais(v), "LECTURE": bloc_lecture(v), "SOR": bloc_sor(o)}


def injecter(texte: str, nom: str, contenu: str) -> str:
    motif = re.compile(rf"(<!-- AUTO:{nom} -->)(.*?)(<!-- /AUTO:{nom} -->)", re.S)
    if not motif.search(texte):
        raise SystemExit(f"balises AUTO:{nom} introuvables")
    return motif.sub(lambda m: f"{m.group(1)}\n{contenu}\n{m.group(3)}", texte)


def main() -> None:
    v, o = charger()
    tous = blocs(v, o)
    for fichier, noms in DESTINATIONS.items():
        chemin = RACINE / fichier
        brut = chemin.read_bytes()
        crlf = brut.count(b"\r\n") > brut.count(b"\n") / 2
        texte = brut.decode("utf-8").replace("\r\n", "\n")
        for nom in noms:
            texte = injecter(texte, nom, tous[nom])
        chemin.write_bytes((texte.replace("\n", "\r\n") if crlf else texte).encode("utf-8"))
        print(f"{fichier} : blocs AUTO:{', '.join(noms)} réécrits depuis results/")


if __name__ == "__main__":
    main()
