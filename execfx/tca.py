"""Monte Carlo de TCA (Transaction Cost Analysis) sur trajectoires de prix RÉELLES.

Pour chaque jour VAL on exécute un ordre parent (acheter ET vendre 50 M EUR) dans la fenêtre 8h00-9h00
(heure de New York) avec chaque stratégie. Le « Monte Carlo » est le rejeu de ~1 000 jours réels, pas
une marche aléatoire simulée : le risque de marché est celui du vrai EURUSD.

Anti look-ahead (règle d'or) : à la tranche k (minute 8h00+k) la stratégie ne reçoit QUE
`prix[: H+k+1]`, c'est-à-dire les clôtures jusqu'à la minute précédente. Elle exécute ensuite au prix
d'ouverture de la minute (= clôture de la minute précédente en HistData) + impact simulé.

Convention d'indices d'une fenêtre `prix` (longueur H+N+1) :
  prix[H]   = clôture de la minute 7h59 = PRIX D'ARRIVÉE (benchmark de l'implementation shortfall)
  prix[H+k] = prix auquel on exécute la tranche k (k = 0..N-1), jamais utilisé pour décider la tranche k
              au-delà de ce que montre `prix[: H+k+1]`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import almgren_chriss as ac
from .impact import (Hypotheses, ModeleImpact, cout_impact_bps, modele_lineaire, modele_racine,
                     theta_par_tranche, volume_minute_eur)
from .profils import Profil, fenetre


@dataclass(frozen=True)
class Contexte:
    """Tout ce que les stratégies ont le droit de connaître : calibré sur le TRAIN, pas sur le jour."""
    hyp: Hypotheses
    modele: ModeleImpact
    part: np.ndarray          # (N,) part de volume des minutes de la fenêtre (proxy)
    sigma: np.ndarray         # (N,) volatilité par minute de la fenêtre (bps)
    act_attendue: np.ndarray  # (H+N,) |rendement| moyen attendu des barres vues par l'algo (pré-fenêtre + fenêtre)
    sigma_ac: float           # volatilité constante utilisée par Almgren-Chriss (rms sur la fenêtre)
    theta_ac: float           # impact temporaire constant utilisé par Almgren-Chriss (bps par fraction)

    @property
    def N(self) -> int:
        return self.hyp.horizon_min

    @property
    def H(self) -> int:
        return self.hyp.pre_fenetre_min


def construire_contexte(profil: Profil, hyp: Hypotheses, modele: str = "lineaire") -> Contexte:
    N, H, d = hyp.horizon_min, hyp.pre_fenetre_min, hyp.debut_min
    part, sigma = fenetre(profil, d, N)
    act_att = profil.activite_bps[d - H: d + N]  # barres d-H .. d+N-1, alignées sur les rendements r_1..r_{H+N}
    sigma_ac = float(np.sqrt(np.mean(sigma ** 2)))
    theta_ac = float(np.mean(theta_par_tranche(hyp, part)))
    if modele == "lineaire":
        mod = modele_lineaire(hyp)
    else:
        rho_ref = hyp.notionnel_eur / volume_minute_eur(hyp, part).sum()
        mod = modele_racine(hyp, float(np.mean(sigma)), rho_ref)
    return Contexte(hyp, mod, part, sigma, act_att, sigma_ac, theta_ac)


# ----------------------------------------------------------------------------- plannings statiques
def planning_twap(N: int) -> np.ndarray:
    return np.full(N, 1.0 / N)


def planning_vwap(part: np.ndarray) -> np.ndarray:
    """VWAP-proxy : on suit la courbe de volume attendue (ici l'activité de prix, faute de volume FX)."""
    return part / part.sum()


def planning_front_loaded(N: int, part_debut: float = 0.4, frac_temps: float = 1 / 6) -> np.ndarray:
    """IS « front-loaded » heuristique : 40 % de l'ordre dans le 1er sixième (10 min), le reste en linéaire.

    C'est ce que fait grossièrement un algo Implementation Shortfall à urgence élevée. Ce n'est PAS la
    trajectoire optimale : elle sert de point de comparaison à la frontière d'Almgren-Chriss.
    """
    n1 = max(1, int(round(N * frac_temps)))
    n = np.empty(N)
    n[:n1] = part_debut / n1
    n[n1:] = (1.0 - part_debut) / (N - n1)
    return n


# ----------------------------------------------------------------------------- stratégies
class StrategieStatique:
    """Planning décidé AVANT l'arrivée (TRAIN seulement) : ne regarde jamais les prix."""

    def __init__(self, nom: str, planning: np.ndarray):
        self.nom, self.planning = nom, np.asarray(planning, dtype=float)
        self.adaptative = False

    def quantite(self, k: int, reste: float, prix_visibles: np.ndarray) -> float:
        if k == len(self.planning) - 1:
            return reste  # on termine toujours l'ordre à l'horizon
        return min(reste, float(self.planning[k]))


class StrategiePOV:
    """POV-proxy (percentage of volume) : suit le volume ATTENDU mis à l'échelle de l'activité OBSERVÉE.

    À la tranche k on regarde les rendements des barres déjà terminées (prix_visibles), on compare leur
    activité à l'activité attendue du profil TRAIN, et on met le planning VWAP à cette échelle :
        m_hat = (somme|r| observée + w*abar) / (somme activité attendue + w*abar)   (rétréci vers 1)
        n_k   = max(part_k / somme(part) * m_hat, reste/(N-k)).
    Jour actif (m_hat > 1) -> on accélère (la liquidité est abondante, donc bon marché) ;
    jour calme -> on ralentit, mais jamais sous le rythme TWAP du reste (reste/(N-k)). Ce plancher est
    indispensable : un POV pur ne garantit pas la fin de l'ordre et finirait par solder une énorme
    tranche à la dernière minute, ce qui serait un artefact de simulation et non une vraie propriété du POV.
    """

    def __init__(self, ctx: Contexte, poids_prior_min: float = 20.0):
        self.nom, self.adaptative = "POV-proxy", True
        self.ctx, self.w = ctx, poids_prior_min
        self.base = planning_vwap(ctx.part)
        self.abar = float(np.mean(ctx.act_attendue))

    def quantite(self, k: int, reste: float, prix_visibles: np.ndarray) -> float:
        if k == len(self.base) - 1:
            return reste
        H = self.ctx.H
        r = 1e4 * np.diff(np.log(prix_visibles))  # H+k rendements, tous passés
        obs = np.abs(r).sum()
        att = self.ctx.act_attendue[: len(r)].sum()
        m_hat = (obs + self.w * self.abar) / (att + self.w * self.abar)
        m_hat = float(np.clip(m_hat, self.ctx.hyp.m_min, self.ctx.hyp.m_max))
        plancher = reste / (len(self.base) - k)  # rythme TWAP du reste : garantit la fin de l'ordre
        return min(reste, max(float(self.base[k] * m_hat), plancher))


def strategies_standard(ctx: Contexte, lams: tuple[float, float, float]) -> list:
    """Les 7 stratégies comparées : TWAP, VWAP-proxy, AC (3 lam), IS front-loaded, POV-proxy."""
    N = ctx.N
    liste = [StrategieStatique("TWAP", planning_twap(N)),
             StrategieStatique("VWAP-proxy", planning_vwap(ctx.part))]
    for i, lam in enumerate(lams, start=1):
        n = ac.trajectoire_optimale(N, lam, ctx.sigma_ac, ctx.theta_ac, ctx.hyp.gamma_bps)
        liste.append(StrategieStatique(f"AC-lam{i}", n))
    liste.append(StrategieStatique("IS-front-loaded", planning_front_loaded(N)))
    liste.append(StrategiePOV(ctx))
    return liste


# ----------------------------------------------------------------------------- exécution d'un jour
def decider(prix: np.ndarray, strat, ctx: Contexte) -> np.ndarray:
    """Quantités n_k décidées une à une ; la tranche k ne voit que prix[: H+k+1] (passé strict)."""
    N, H = ctx.N, ctx.H
    n = np.zeros(N)
    reste = 1.0
    for k in range(N):
        q = max(0.0, strat.quantite(k, reste, prix[: H + k + 1]))
        n[k] = q
        reste -= q
    return n


def activite_du_jour(prix: np.ndarray, ctx: Contexte) -> float:
    """LE MONDE, pas un décideur : facteur d'activité réalisé du jour (volume réel / volume attendu).

    Hypothèse de simulation : le volume réel de la fenêtre est proportionnel à l'activité de prix
    réalisée (relation volume-volatilité). Calculé ex post sur toute la fenêtre ; JAMAIS donné aux stratégies.
    """
    r = 1e4 * np.diff(np.log(prix))
    m = np.abs(r).sum() / ctx.act_attendue.sum()
    return float(np.clip(m, ctx.hyp.m_min, ctx.hyp.m_max))


def chiffrer(prix: np.ndarray, n: np.ndarray, ctx: Contexte) -> tuple[float, float]:
    """(coût de marché signé pour un ACHAT, coût d'impact) en bps pour un planning n.

    marché = sum n_k * (prix[H+k]/prix[H] - 1) : la dérive du prix pendant qu'on exécute (aléa réel).
    impact = temporaire(rho_k) + permanent(gamma*C_{k-1}) + demi-spread, avec un volume simulé V_k.
    Pour une VENTE : marché change de signe, l'impact est identique.
    """
    N, H = ctx.N, ctx.H
    marche = float(np.sum(n * 1e4 * np.log(prix[H: H + N] / prix[H])))
    m = activite_du_jour(prix, ctx)
    volumes = volume_minute_eur(ctx.hyp, ctx.part, m)
    return marche, cout_impact_bps(n, volumes, ctx.sigma, ctx.hyp, ctx.modele)


def preparer_fenetres(mat_ny: np.ndarray, hyp: Hypotheses, min_barres: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Extrait les fenêtres (jours, H+N+1) des clôtures ; remplit les minutes sans tick par le dernier prix.

    Retourne (fenetres, indices_jours_gardes). On écarte les jours avec < `min_barres` vraies barres ou sans
    barre d'arrivée (7h59) : un prix inventé à l'arrivée fausserait le benchmark.
    """
    N, H, d = hyp.horizon_min, hyp.pre_fenetre_min, hyp.debut_min
    brut = mat_ny[:, d - 1 - H: d + N]
    garde = (np.sum(~np.isnan(brut), axis=1) >= min_barres) & ~np.isnan(brut[:, H])
    fen = brut[garde].copy()
    for i in range(len(fen)):  # remplissage avant (dernier prix connu), puis arrière pour les NaN de tête
        ligne = fen[i]
        ok = ~np.isnan(ligne)
        idx = np.where(ok, np.arange(len(ligne)), 0)
        np.maximum.accumulate(idx, out=idx)
        ligne[:] = ligne[idx]
        if np.isnan(ligne[0]):
            ligne[:] = np.where(np.isnan(ligne), ligne[np.argmax(ok)], ligne)
    return fen, np.where(garde)[0]


@dataclass
class Resultat:
    n: np.ndarray        # (jours, N) planning réellement exécuté
    marche: np.ndarray   # (jours,) coût de marché d'un achat (bps)
    impact: np.ndarray   # (jours,) coût d'impact (bps), identique achat/vente

    def echantillons(self) -> np.ndarray:
        """(jours, 2) implementation shortfall d'un achat puis d'une vente, en bps."""
        return np.stack([self.marche + self.impact, -self.marche + self.impact], axis=1)


def executer_jours(fenetres: np.ndarray, strategies: list, ctx: Contexte) -> dict[str, Resultat]:
    res = {}
    for s in strategies:
        n_all, mar, imp = [], [], []
        for prix in fenetres:
            n = decider(prix, s, ctx)
            m, i = chiffrer(prix, n, ctx)
            n_all.append(n), mar.append(m), imp.append(i)
        res[s.nom] = Resultat(np.array(n_all), np.array(mar), np.array(imp))
    return res


# ----------------------------------------------------------------------------- statistiques
def indices_bootstrap(n_jours: int, bloc: int, B: int, rng: np.random.Generator) -> np.ndarray:
    """(B, n_jours) indices de jours : blocs de `bloc` jours consécutifs tirés avec remise.

    Les jours voisins se ressemblent (régimes de volatilité) : tirer des blocs et non des jours isolés
    évite de sous-estimer l'incertitude. Les MÊMES indices servent à toutes les stratégies : les
    différences entre stratégies sont donc appariées jour par jour.
    """
    n_blocs = int(np.ceil(n_jours / bloc))
    debuts = rng.integers(0, n_jours - bloc + 1, size=(B, n_blocs))
    idx = (debuts[:, :, None] + np.arange(bloc)).reshape(B, -1)
    return idx[:, :n_jours]


def _stat(S: np.ndarray, idx: np.ndarray, f) -> np.ndarray:
    """Applique f(échantillon poolé achat+vente) à chaque rééchantillon bootstrap -> (B,)."""
    return f(S[idx].reshape(len(idx), -1))


def resumer(res: dict[str, Resultat], rng: np.random.Generator, B: int = 1000, bloc: int = 5,
            reference: str = "TWAP") -> dict:
    """Moyenne, écart-type, quantiles du shortfall par stratégie + IC95 bootstrap par blocs + écart vs TWAP."""
    n_jours = len(next(iter(res.values())).marche)
    idx = indices_bootstrap(n_jours, bloc, B, rng)
    moy = lambda X: X.mean(axis=1)
    std = lambda X: X.std(axis=1, ddof=1)
    q95 = lambda X: np.quantile(X, 0.95, axis=1)
    ic = lambda v: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
    ref = res[reference].echantillons()
    out = {}
    for nom, r in res.items():
        S = r.echantillons()
        pool = S.ravel()
        bm, bs, bq = _stat(S, idx, moy), _stat(S, idx, std), _stat(S, idx, q95)
        dm = bm - _stat(ref, idx, moy)
        out[nom] = {
            "shortfall_moyen_bps": float(pool.mean()), "ic95_moyen_bps": ic(bm),
            "ecart_type_bps": float(pool.std(ddof=1)), "ic95_ecart_type_bps": ic(bs),
            "p95_bps": float(np.quantile(pool, 0.95)), "ic95_p95_bps": ic(bq),
            "p05_bps": float(np.quantile(pool, 0.05)),
            "cout_impact_moyen_bps": float(r.impact.mean()),
            "part_executee_mi_horizon": float(r.n[:, : r.n.shape[1] // 2].sum(axis=1).mean()),
            "diff_moyen_vs_twap_bps": float(pool.mean() - ref.mean()), "ic95_diff_moyen_vs_twap_bps": ic(dm),
        }
    return out


def theorie_statique(planning: np.ndarray, ctx: Contexte) -> dict:
    """(E, écart-type) prédits par le modèle pour un planning statique, à activité attendue (m = 1)."""
    theta_k = theta_par_tranche(ctx.hyp, ctx.part)
    E = ac.esperance_cout(planning, theta_k, ctx.hyp.gamma_bps, ctx.hyp.demi_spread_bps)
    V = ac.variance_cout(planning, ctx.sigma[:-1])
    return {"E_theorique_bps": E, "std_theorique_bps": float(np.sqrt(V))}
