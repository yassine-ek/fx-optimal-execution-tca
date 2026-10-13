"""Almgren-Chriss (2000) : exécution optimale d'un ordre parent, version discrète exacte.

Unités (tout est normalisé, c'est ce qui rend les formules lisibles) :
  - ordre parent = 1 (on raisonne en FRACTIONS de l'ordre) ; une tranche = 1 minute (tau = 1)
  - sigma : volatilité du prix en bps par racine de tranche
  - theta : impact temporaire, bps par unité de fraction négociée dans UNE tranche
            (coût d'une tranche n = theta * n**2 ; c'est l'eta de l'article, converti)
  - gamma : impact permanent, bps de décalage de prix quand tout l'ordre est exécuté
  - eps   : demi-spread fixe, bps
  - lam   : aversion au risque, en 1/bps (on minimise E[coût] + lam * Var[coût])

Un achat de n_k à la tranche k est exécuté au prix du DÉBUT de la tranche (celui qu'on voit), donc :
  coût = eps + sum_k theta_k n_k^2 + gamma * sum_k n_k * C_{k-1}  + (bruit de marché)
  avec C_{k-1} = fraction déjà exécutée avant la tranche k (l'impact permanent des tranches passées
  décale le prix des suivantes).
"""
from __future__ import annotations

import numpy as np


def eta_tilde(theta: float, gamma: float, tau: float = 1.0) -> float:
    """Impact temporaire « corrigé » eta~ = theta - gamma*tau/2 (le permanent déjà payé réduit le net)."""
    et = theta - 0.5 * gamma * tau
    if et <= 0:
        raise ValueError("eta_tilde <= 0 : impact permanent trop fort devant le temporaire (modèle dégénéré).")
    return et


def kappa(lam: float, sigma: float, theta: float, gamma: float = 0.0, tau: float = 1.0) -> float:
    """Taux d'urgence kappa : cosh(kappa*tau) = 1 + 0.5 * kappa~^2 * tau^2, kappa~^2 = lam*sigma^2/eta~.

    En continu (tau -> 0) on retrouve kappa = sqrt(lam*sigma^2/eta). Plus lam est grand, plus kappa est
    grand, plus on exécute tôt.
    """
    if lam <= 0:
        return 0.0
    k2 = lam * sigma ** 2 / eta_tilde(theta, gamma, tau)
    return float(np.arccosh(1.0 + 0.5 * k2 * tau ** 2) / tau)


def lambda_pour_kappaT(kappa_T: float, N: int, sigma: float, theta: float, gamma: float = 0.0) -> float:
    """Inverse de `kappa` : le lam qui donne une urgence kappa*T voulue (pratique pour choisir 3 lam lisibles)."""
    k_tilde2 = 2.0 * (np.cosh(kappa_T / N) - 1.0)  # tau = 1, kappa = kappa_T / N
    return float(k_tilde2 * eta_tilde(theta, gamma) / sigma ** 2)


def detentions(N: int, lam: float, sigma: float, theta: float, gamma: float = 0.0) -> np.ndarray:
    """Quantité restante x_j (fraction de l'ordre), j = 0..N : x_0 = 1, x_N = 0.

    x_j = sinh(kappa (T - t_j)) / sinh(kappa T). Écrit avec des exponentielles décroissantes pour ne
    jamais déborder quand kappa*T est grand. lam = 0 (ou kappa*T ~ 0) -> TWAP : x_j = 1 - j/N.
    """
    j = np.arange(N + 1, dtype=float)
    k = kappa(lam, sigma, theta, gamma)
    kT = k * N
    if kT < 1e-9:
        return 1.0 - j / N
    return (np.exp(-k * j) - np.exp(-k * (2 * N - j))) / (1.0 - np.exp(-2.0 * kT))


def trajectoire_optimale(N: int, lam: float, sigma: float, theta: float, gamma: float = 0.0) -> np.ndarray:
    """Quantités à négocier par tranche n_k = x_{k-1} - x_k (somme = 1, toutes >= 0)."""
    return -np.diff(detentions(N, lam, sigma, theta, gamma))


def esperance_cout(n: np.ndarray, theta, gamma: float = 0.0, eps: float = 0.0) -> float:
    """E[coût] en bps pour un planning n quelconque ; `theta` scalaire ou tableau (un par tranche)."""
    n = np.asarray(n, dtype=float)
    cum_avant = np.cumsum(n) - n
    return float(eps * n.sum() + np.sum(np.asarray(theta) * n ** 2) + gamma * np.sum(n * cum_avant))


def variance_cout(n: np.ndarray, sigma) -> float:
    """Var[coût] en bps^2 : le prix marche au hasard tant qu'il reste du stock : sum_j sigma_j^2 x_j^2.

    `sigma` scalaire (cas Almgren-Chriss) ou tableau de N-1 volatilités (profil par minute).
    """
    x = 1.0 - np.cumsum(np.asarray(n, dtype=float))  # x_j = reste après la tranche j (x_N = 0)
    return float(np.sum(np.asarray(sigma, dtype=float) ** 2 * x[:-1] ** 2))


def frontiere(lams: np.ndarray, N: int, sigma: float, theta: float, gamma: float = 0.0, eps: float = 0.0) -> dict:
    """Frontière efficiente (E, écart-type) paramétrée par lam ; lam = 0 donne le point TWAP."""
    E, S, KT = [], [], []
    for lam in lams:
        n = trajectoire_optimale(N, lam, sigma, theta, gamma)
        E.append(esperance_cout(n, theta, gamma, eps))
        S.append(np.sqrt(variance_cout(n, sigma)))
        KT.append(kappa(lam, sigma, theta, gamma) * N)
    return {"lam": np.asarray(lams, float), "E_bps": np.array(E), "std_bps": np.array(S), "kappa_T": np.array(KT)}
