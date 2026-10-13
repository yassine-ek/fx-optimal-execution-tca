"""Simulateur d'agrégateur de liquidité FX avec LAST LOOK et routeur d'ordres (SOR).

Idée : N = 8 fournisseurs de liquidité (LP) cotent autour du mid. Les LP les plus serrés ont tendance à
avoir (1) des prix un peu périmés (latence) et (2) un LAST LOOK : après réception de l'ordre, ils regardent
le marché pendant quelques ms et peuvent REJETER si le prix a bougé contre eux. Un routeur qui envoie tout
au « meilleur prix affiché » choisit donc, par construction, la cote la plus susceptible d'être rejetée.

Tout est calculé en PIPS (1 pip = 0.0001 de prix EURUSD) et en « coût » du point de vue du client :
coût = sens * (prix payé - mid initial), donc positif = on paie plus cher que le mid d'arrivée,
que l'on achète (sens = +1) ou vende (sens = -1).

Le mid de référence vient du vrai EURUSD : la volatilité utilisée entre deux ticks est la volatilité
réalisée des 30 minutes précédentes (causale) d'une minute tirée au hasard dans les données réelles.
Tous les paramètres des LP sont des HYPOTHÈSES stylisées (aucune donnée de LP réelle).

Les aléas sont tirés AVANT (numpy default_rng) puis rejoués à l'identique pour chaque routeur
(« nombres aléatoires communs ») : les écarts entre routeurs sont appariés, pas du bruit de simulation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit

NB_LP = 8
NB_TOURS = 3          # un ordre rejeté est re-routé au plus 2 fois (3 tours en tout)
PAS_MS = 10           # pas de temps du chemin de prix
NB_AR, NB_AV = 40, 120  # 400 ms de passé (cotes périmées), 1200 ms de futur (last look, re-routage)
UPLINK_MS, DOWNLINK_MS = 10, 10  # délais réseau aller / retour

ROUTEURS = {"a_meilleur_affiche": 0, "b_prix_effectif": 1, "c_split": 2}


@dataclass(frozen=True)
class ParamsLP:
    """Un tableau de NB_LP valeurs par attribut. Pips, ms, millions d'EUR."""
    noms: tuple
    demi_spread: np.ndarray   # demi-spread propre du LP (pips)
    bruit: np.ndarray         # bruit de cote indépendant (pips, écart-type)
    latence: np.ndarray       # âge de la cote affichée (ms) : cote = mid d'il y a `latence` ms
    fenetre_ll: np.ndarray    # fenêtre de last look (ms) ; 0 = prix ferme, jamais de rejet
    seuil_ll: np.ndarray      # le LP ne rejette que si le marché a bougé de plus de ce seuil contre lui (pips)
    p_base: np.ndarray        # probabilité de rejet (quand le seuil est dépassé) à toxicité nulle
    p_pente: np.ndarray       # hausse de cette probabilité par unité de toxicité (toxicité dans [0, 1])
    profondeur: np.ndarray    # taille affichée au meilleur prix (M EUR)


def lp_par_defaut() -> ParamsLP:
    """3 LP « last look agressifs » (cotes serrées mais périmées), 2 modérés, 3 « prix fermes » plus larges."""
    return ParamsLP(
        noms=("LL1", "LL2", "LL3", "LM1", "LM2", "FERME1", "FERME2", "FERME3"),
        demi_spread=np.array([0.03, 0.04, 0.05, 0.08, 0.09, 0.10, 0.12, 0.15]),
        bruit=np.array([0.03, 0.03, 0.04, 0.04, 0.04, 0.05, 0.05, 0.05]),
        latence=np.array([150.0, 100.0, 80.0, 40.0, 30.0, 10.0, 10.0, 5.0]),
        fenetre_ll=np.array([150.0, 200.0, 120.0, 60.0, 50.0, 0.0, 0.0, 0.0]),
        seuil_ll=np.array([0.03, 0.04, 0.05, 0.08, 0.10, 0.0, 0.0, 0.0]),
        p_base=np.array([0.15, 0.15, 0.10, 0.05, 0.05, 0.0, 0.0, 0.0]),
        p_pente=np.array([0.80, 0.75, 0.70, 0.40, 0.40, 0.0, 0.0, 0.0]),
        profondeur=np.array([6.0, 6.0, 8.0, 8.0, 10.0, 8.0, 10.0, 10.0]),
    )


# ----------------------------------------------------------------------------- scénarios et aléas
def tirer_minutes(mat_ny: np.ndarray, n: int, rng: np.random.Generator, heure_min: int = 3 * 60,
                  heure_max: int = 12 * 60, fenetre_vol: int = 30) -> np.ndarray:
    """Volatilité réalisée causale (pips par racine de ms) de `n` minutes tirées au hasard (3h-12h New York).

    On utilise les 30 minutes AVANT la minute tirée seulement. Les minutes sans assez de données sont retirées.
    """
    sigma = np.empty(0)
    n_jours = len(mat_ny)
    while len(sigma) < n:
        k = int((n - len(sigma)) * 1.3) + 50
        j = rng.integers(0, n_jours, size=k)
        m = rng.integers(heure_min + fenetre_vol + 1, heure_max, size=k)
        idx = m[:, None] + np.arange(-fenetre_vol - 1, 0)[None, :]
        p = mat_ny[j[:, None], idx]
        d = np.diff(p, axis=1) / 1e-4  # variations 1 minute en pips (NaN si une clôture manque)
        valide = np.sum(~np.isnan(d), axis=1)
        with np.errstate(all="ignore"):
            s = np.sqrt(np.nanmean(d ** 2, axis=1))
        ok = (valide >= 20) & np.isfinite(s) & (s > 0)
        sigma = np.concatenate([sigma, s[ok] / np.sqrt(60000.0)])
    return sigma[:n]


def generer_aleas(rng: np.random.Generator, sigma_ms: np.ndarray) -> dict:
    """Chemin de mid (pips, relatif au mid initial) autour de t=0 + bruits de cote + tirages de rejet."""
    n = len(sigma_ms)
    sd = (sigma_ms * np.sqrt(PAS_MS))[:, None]
    av = np.cumsum(rng.standard_normal((n, NB_AV)) * sd, axis=1)
    ar = np.cumsum(rng.standard_normal((n, NB_AR)) * sd, axis=1)
    chemin = np.concatenate([ar[:, ::-1], np.zeros((n, 1)), av], axis=1)  # colonne NB_AR <-> t = 0
    return {"chemin": chemin,
            "zq": rng.standard_normal((n, NB_TOURS, NB_LP)),
            "u": rng.random((n, NB_TOURS, NB_LP)),
            "sens": rng.choice(np.array([1.0, -1.0]), size=n)}


# ----------------------------------------------------------------------------- cœur numba
@njit(cache=True)
def _idx(t_ms):
    j = int(np.floor(t_ms / PAS_MS + 0.5)) + NB_AR
    return min(max(j, 0), NB_AR + NB_AV)


@njit(cache=True)
def _un_ordre(sens, Q, mode, lp_force, tox, chemin, zq, u,
              s, nu, lat, w, x, pb, ps, prof, phat, cbar, m_split, sortie):
    """Simule UN ordre de taille Q (M EUR). mode : 0 meilleur affiché, 1 prix effectif, 2 split, 3 sonde LP imposé.

    sortie : [coût moyen, taux rempli, nb rejets, délai dernier fill (ms), meilleur affiché (tour 1),
              cote du LP imposé (tour 1), coût affiché moyen du plan initial, meilleure cote des autres LP (tour 1),
              LP principal du tour 1]
    """
    reste, rempli, somme_cout = Q, 0.0, 0.0
    utilise = np.zeros(NB_LP)
    exclu = np.zeros(NB_LP, dtype=np.bool_)
    n_rej, t_q, t_dernier = 0, 0.0, 0.0
    plan_somme, plan_q = 0.0, 0.0
    sortie[4] = 1e9
    for tour in range(NB_TOURS):
        if reste <= 1e-9:
            break
        cote = np.empty(NB_LP)
        score = np.empty(NB_LP)
        for i in range(NB_LP):
            # cote affichée = mid d'il y a `lat` ms + demi-spread + bruit (du point de vue du client)
            cote[i] = sens * chemin[_idx(t_q - lat[i])] + s[i] + nu[i] * zq[tour, i]
        dispo = np.ones(NB_LP, dtype=np.bool_)
        for i in range(NB_LP):
            dispo[i] = (not exclu[i]) and utilise[i] < prof[i] - 1e-12
        for i in range(NB_LP):
            score[i] = cote[i]
            if mode == 1 or mode == 2:
                # coût attendu = prix + P(rejet) * coût de re-routage, où le re-routage coûte
                # (meilleure cote des AUTRES LP + surcoût de marché appris) - cote de ce LP
                alt = 1e9
                for j in range(NB_LP):
                    if j != i and dispo[j] and cote[j] < alt:
                        alt = cote[j]
                if alt < 1e8:
                    score[i] = cote[i] + phat[i] * (alt + cbar[i] - cote[i])
            if not dispo[i]:
                score[i] = 1e9
        if tour == 0:
            sortie[4] = cote.min()
            sortie[5] = cote[lp_force] if lp_force >= 0 else 0.0
            alt0 = 1e9
            for j in range(NB_LP):
                if j != lp_force and cote[j] < alt0:
                    alt0 = cote[j]
            sortie[7] = alt0
        ordre = np.argsort(score)
        alloc = np.zeros(NB_LP)
        a_placer = reste
        if mode == 3 and tour == 0:
            alloc[lp_force] = a_placer
            a_placer = 0.0
        elif mode == 2 and tour == 0:
            for r in range(m_split):  # parts égales sur les m meilleurs, plafonnées par la profondeur
                i = ordre[r]
                if score[i] >= 1e9:
                    continue
                q = min(Q / m_split, prof[i] - utilise[i], a_placer)
                alloc[i] += q
                a_placer -= q
        for r in range(NB_LP):  # cascade : on remplit les LP du moins cher au plus cher (jusqu'à leur taille)
            i = ordre[r]
            if a_placer <= 1e-12 or score[i] >= 1e9:
                continue
            q = min(prof[i] - utilise[i] - alloc[i], a_placer)
            if q > 0:
                alloc[i] += q
                a_placer -= q
        if tour == 0:
            premier = 0
            for i in range(NB_LP):
                plan_somme += alloc[i] * cote[i]
                plan_q += alloc[i]
                if alloc[i] > alloc[premier]:
                    premier = i
            sortie[8] = premier
        non_place = a_placer
        a_re_router, t_suivant = 0.0, t_q
        for i in range(NB_LP):
            if alloc[i] <= 0:
                continue
            t_arr = t_q + UPLINK_MS
            rejet = False
            t_dec = t_arr
            if w[i] > 0:
                t_dec = t_arr + w[i]
                # le marché a-t-il bougé CONTRE le LP depuis l'âge de sa cote jusqu'à la décision ?
                adverse = sens * (chemin[_idx(t_dec)] - chemin[_idx(t_q - lat[i])])
                p = min(1.0, pb[i] + ps[i] * tox)
                rejet = (adverse > x[i]) and (u[tour, i] < p)
            if rejet:
                a_re_router += alloc[i]
                exclu[i] = True
                n_rej += 1
                t_suivant = max(t_suivant, t_dec + DOWNLINK_MS)
            else:
                rempli += alloc[i]
                utilise[i] += alloc[i]
                somme_cout += alloc[i] * cote[i]
                t_dernier = max(t_dernier, t_dec)
        reste = a_re_router + non_place
        t_q = t_suivant
    sortie[0] = somme_cout / rempli if rempli > 0 else np.nan
    sortie[1] = rempli / Q
    sortie[2] = n_rej
    sortie[3] = t_dernier if rempli > 0 else np.nan
    sortie[6] = plan_somme / plan_q if plan_q > 0 else np.nan


@njit(cache=True)
def _boucle(sens, Q, mode, lp_force, tox, chemin, zq, u, s, nu, lat, w, x, pb, ps, prof, phat, cbar, m_split, res):
    for t in range(chemin.shape[0]):
        _un_ordre(sens[t], Q, mode, lp_force, tox, chemin[t], zq[t], u[t],
                  s, nu, lat, w, x, pb, ps, prof, phat, cbar, m_split, res[t])


def simuler(aleas: dict, lp: ParamsLP, routeur: str, toxicite: float, taille_meur: float = 20.0,
            phat: np.ndarray | None = None, cbar: np.ndarray | None = None,
            lp_force: int = -1, m_split: int = 3) -> dict:
    """Rejoue les mêmes aléas avec un routeur donné. Retourne des tableaux par ordre (n,)."""
    n = len(aleas["sens"])
    res = np.full((n, 9), np.nan)
    mode = 3 if lp_force >= 0 else ROUTEURS[routeur]
    z = np.zeros(NB_LP)
    _boucle(aleas["sens"], taille_meur, mode, lp_force, toxicite, aleas["chemin"], aleas["zq"], aleas["u"],
            lp.demi_spread, lp.bruit, lp.latence, lp.fenetre_ll, lp.seuil_ll, lp.p_base, lp.p_pente,
            lp.profondeur, z if phat is None else phat, z if cbar is None else cbar, m_split, res)
    return {"cout_pips": res[:, 0], "remplissage": res[:, 1], "rejets": res[:, 2], "delai_ms": res[:, 3],
            "meilleur_affiche_pips": res[:, 4], "cote_lp_force_pips": res[:, 5], "plan_affiche_pips": res[:, 6],
            "meilleure_cote_autres_pips": res[:, 7], "premier_lp": res[:, 8]}


def allouer_tour1(cotes: np.ndarray, profondeurs: np.ndarray, taille: float) -> np.ndarray:
    """Allocation du tour 1 du routeur (a) « meilleur prix affiché » : remplir du moins cher au plus cher.

    Fonction pure, en Python, qui reflète la cascade du cœur numba ; sert surtout à tester le routeur (a).
    """
    alloc = np.zeros(len(cotes))
    reste = taille
    for i in np.argsort(cotes):
        q = min(profondeurs[i], reste)
        alloc[i] = q
        reste -= q
        if reste <= 1e-12:
            break
    return alloc


# ----------------------------------------------------------------------------- statistiques du routeur
def calibrer_stats(aleas_train: dict, lp: ParamsLP, toxicite: float, taille_sonde_meur: float = 1.0) -> tuple:
    """Taux de rejet et coût de re-routage de chaque LP, appris sur des données TRAIN.

    On sonde chaque LP seul avec un petit ordre ; en cas de rejet l'ordre est re-routé au meilleur prix
    affiché ailleurs. phat_i = fréquence des rejets ; cbar_i = surcoût moyen quand il y a eu rejet, mesuré
    contre la meilleure cote des AUTRES LP au moment de l'envoi (le marché a bougé contre nous + temps perdu). C'est ce qu'un vrai SOR mesure en continu sur son propre flux.
    """
    phat, cbar = np.zeros(NB_LP), np.zeros(NB_LP)
    for i in range(NB_LP):
        r = simuler(aleas_train, lp, "a_meilleur_affiche", toxicite, taille_sonde_meur, lp_force=i)
        rej = r["rejets"] > 0
        phat[i] = rej.mean()
        extra = (r["cout_pips"] - r["meilleure_cote_autres_pips"])[rej]
        cbar[i] = np.nanmean(extra) if rej.any() else 0.0
    return phat, cbar


def _moyenne_ic(v: np.ndarray) -> dict:
    """Moyenne et IC95 normal (les ordres sont indépendants, contrairement aux jours du TCA)."""
    v = v[np.isfinite(v)]
    m, se = float(v.mean()), float(v.std(ddof=1) / np.sqrt(len(v)))
    return {"moyenne": m, "ic95": [m - 1.96 * se, m + 1.96 * se]}


def comparer_routeurs(aleas_eval: dict, aleas_train: dict, lp: ParamsLP, toxicite: float, taille_meur: float = 20.0) -> dict:
    """Évalue les 3 routeurs sur les mêmes aléas ; (b) et (c) utilisent des stats apprises sur le TRAIN."""
    phat, cbar = calibrer_stats(aleas_train, lp, toxicite)
    res = {r: simuler(aleas_eval, lp, r, toxicite, taille_meur, phat, cbar) for r in ROUTEURS}
    ref = res["b_prix_effectif"]
    out = {"stats_apprises": {"p_rejet": {n: float(p) for n, p in zip(lp.noms, phat)},
                              "surcout_reroutage_pips": {n: float(c) for n, c in zip(lp.noms, cbar)}}}
    a = res["a_meilleur_affiche"]
    desaccord = a["premier_lp"] != ref["premier_lp"]  # ordres où (a) et (b) n'envoient pas au même LP en premier
    for nom, r in res.items():
        d = r["cout_pips"] - ref["cout_pips"]
        out[nom] = {
            "prix_effectif_pips": _moyenne_ic(r["cout_pips"]),
            "meilleur_affiche_pips": float(np.mean(r["meilleur_affiche_pips"])),
            "plan_affiche_pips": float(np.nanmean(r["plan_affiche_pips"])),
            "ecart_effectif_moins_plan_pips": float(np.nanmean(r["cout_pips"] - r["plan_affiche_pips"])),
            "taux_remplissage": float(np.mean(r["remplissage"])),
            "rejets_par_ordre": float(np.mean(r["rejets"])),
            "ordres_avec_rejet": float(np.mean(r["rejets"] > 0)),
            "delai_dernier_fill_ms": float(np.nanmean(r["delai_ms"])),
            "ecart_type_cout_pips": float(np.nanstd(r["cout_pips"], ddof=1)),
            "p95_cout_pips": float(np.nanquantile(r["cout_pips"], 0.95)),
            "diff_vs_b_pips": _moyenne_ic(d),
        }
    out["desaccord_a_vs_b"] = {"part_ordres": float(desaccord.mean()),
                               "cout_a_moins_cout_b_pips": _moyenne_ic((a["cout_pips"] - ref["cout_pips"])[desaccord])}
    return out
