"""Modèles d'impact de marché et HYPOTHÈSES du projet.

Aucune donnée de transaction : l'impact est SUPPOSÉ, pas estimé. Les valeurs ci-dessous sont des ordres
de grandeur plausibles pour 50 M EUR d'EURUSD, documentés ici pour qu'on puisse les contester et les
faire varier (le script `run_all.py` rejoue tout avec l'impact x0.5 et x2).

Notations : X = notionnel du parent, V_k = « volume » de la minute k (EUR), n_k = fraction du parent
négociée à la minute k, rho_k = n_k * X / V_k = taux de participation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np


@dataclass(frozen=True)
class Hypotheses:
    notionnel_eur: float = 50e6     # ordre parent : acheter ou vendre 50 M EUR
    horizon_min: int = 60           # exécution sur 1 h, une tranche par minute
    debut_min: int = 8 * 60         # fenêtre 8h00-9h00, heure de New York (annonces US de 8h30 dedans)
    pre_fenetre_min: int = 60       # minutes visibles AVANT l'arrivée (sert à estimer l'activité du jour)
    # « volume » EURUSD accessible à l'algo sur la journée entière (hypothèse). Le vrai marché fait
    # ~1 000 Md EUR/jour, mais un algo n'interagit qu'avec la liquidité de ses venues/LP : 5 Md EUR.
    volume_jour_eur: float = 5e9
    eta_bps: float = 10.0           # impact temporaire linéaire : slippage = eta_bps * rho (10 bps à 100 %)
    gamma_bps: float = 0.5          # impact permanent : le prix finit 0.5 bp plus loin si tout est exécuté
    demi_spread_bps: float = 0.1    # demi-spread fixe payé sur tout l'ordre (le même pour toutes les stratégies)
    m_min: float = 0.3              # bornes du facteur « activité du jour » (volume réel / volume attendu)
    m_max: float = 3.0

    def avec_impact_x(self, facteur: float) -> "Hypotheses":
        """Copie avec tous les impacts multipliés (analyse de sensibilité)."""
        return replace(self, eta_bps=self.eta_bps * facteur, gamma_bps=self.gamma_bps * facteur)


def volume_minute_eur(hyp: Hypotheses, part_jour: np.ndarray, m: float = 1.0) -> np.ndarray:
    """Volume simulé par minute = volume du jour * part de la minute dans le profil * activité du jour."""
    return hyp.volume_jour_eur * np.asarray(part_jour) * m


def theta_par_tranche(hyp: Hypotheses, part_jour: np.ndarray, m: float = 1.0) -> np.ndarray:
    """theta_k (bps par fraction de parent) du modèle linéaire : eta * X / V_k. Entrée d'Almgren-Chriss."""
    return hyp.eta_bps * hyp.notionnel_eur / volume_minute_eur(hyp, part_jour, m)


@dataclass(frozen=True)
class ModeleImpact:
    """Impact TEMPORAIRE d'une tranche (le permanent est commun, linéaire, géré à part).

    `lineaire`      : slippage_bps = eta_bps * rho
    `racine_carree` : slippage_bps = y * sigma_bps * sqrt(rho)   (loi « racine carrée » : coût ∝ sigma * sqrt(q/V))
    Le coefficient y est calibré pour que les deux modèles coïncident au point de référence
    (TWAP nominal, volume attendu) ; ils ne diffèrent qu'ailleurs : la racine carrée est concave,
    elle punit PLUS les petites tranches et MOINS les grosses que le linéaire.
    """
    nom: str
    eta_bps: float
    y: float = 0.0

    def temporaire_bps(self, rho: np.ndarray, sigma_bps: np.ndarray) -> np.ndarray:
        rho = np.maximum(rho, 0.0)
        if self.nom == "lineaire":
            return self.eta_bps * rho
        return self.y * sigma_bps * np.sqrt(rho)


def modele_lineaire(hyp: Hypotheses) -> ModeleImpact:
    return ModeleImpact("lineaire", hyp.eta_bps)


def modele_racine(hyp: Hypotheses, sigma_moy_bps: float, rho_ref: float) -> ModeleImpact:
    """Racine carrée calibrée : y * sigma_moy * sqrt(rho_ref) = eta * rho_ref au taux de référence."""
    y = hyp.eta_bps * np.sqrt(rho_ref) / sigma_moy_bps
    return ModeleImpact("racine_carree", hyp.eta_bps, float(y))


def cout_impact_bps(n: np.ndarray, volumes_eur: np.ndarray, sigma_bps: np.ndarray,
                    hyp: Hypotheses, modele: ModeleImpact) -> float:
    """Coût d'impact déterministe (bps du notionnel) d'un planning n : temporaire + permanent + demi-spread.

    Le permanent des tranches passées décale le prix des suivantes : gamma * C_{k-1} sur la tranche k.
    """
    n = np.asarray(n, dtype=float)
    rho = n * hyp.notionnel_eur / volumes_eur
    cum_avant = np.cumsum(n) - n
    par_tranche = modele.temporaire_bps(rho, sigma_bps) + hyp.gamma_bps * cum_avant + hyp.demi_spread_bps
    return float(np.sum(n * par_tranche))
