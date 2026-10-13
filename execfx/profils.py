"""Profil intrajournalier d'activité et de volatilité par minute de la journée (heure de New York).

ATTENTION : le FX est un marché OTC, il n'existe PAS de volume centralisé (la colonne volume
HistData vaut 0). On utilise donc l'activité de prix comme PROXY de volume : le |rendement| moyen
d'une minute est corrélé aux nombres de ticks et de transactions (relation volume-volatilité).
C'est une approximation, pas une mesure de volume. Calibré sur le TRAIN uniquement.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Profil:
    """Tableaux de taille 1440 indexés par minute locale de New York.

    `activite_bps[m]`  : |rendement| moyen de la barre m (bps), avec rendement = close[m]/close[m-1].
    `sigma_min_bps[m]` : écart-type (racine du moment d'ordre 2) du rendement de la barre m (bps).
    `part_jour[m]`     : part de l'activité quotidienne portée par la minute m ; somme = 1.
                         C'est ce qui sert de « courbe de volume » (VWAP-proxy, volume du simulateur).
    """
    activite_bps: np.ndarray
    sigma_min_bps: np.ndarray
    part_jour: np.ndarray
    n_jours: int


def rendements_bps(mat: np.ndarray) -> np.ndarray:
    """Rendements log en bps, r[:, m] = rendement de la barre m (NaN si une des deux clôtures manque)."""
    r = np.full(mat.shape, np.nan)
    r[:, 1:] = 1e4 * np.log(mat[:, 1:] / mat[:, :-1])
    return r


def _lisser(x: np.ndarray, largeur: int) -> np.ndarray:
    if largeur <= 1:
        return x
    noyau = np.ones(largeur) / largeur
    etendu = np.concatenate([x[-largeur:], x, x[:largeur]])  # bords circulaires (une journée se referme)
    return np.convolve(etendu, noyau, mode="same")[largeur:-largeur]


def calibrer_profil(mat_train: np.ndarray, lissage: int = 1) -> Profil:
    """Profil moyen sur les jours TRAIN. `lissage` = largeur (impaire) de moyenne mobile, 1 = aucun.

    Pas de lissage par défaut : le pic de 8h30 (annonces US) est net et ne doit pas être étalé.
    """
    r = rendements_bps(mat_train)
    activite = _lisser(np.nanmean(np.abs(r), axis=0), lissage)
    sigma = np.sqrt(_lisser(np.nanmean(r ** 2, axis=0), lissage))
    activite = np.nan_to_num(activite, nan=np.nanmean(activite))  # minute 0 : jamais de rendement
    sigma = np.nan_to_num(sigma, nan=np.nanmean(sigma))
    return Profil(activite, sigma, activite / activite.sum(), len(mat_train))


def fenetre(profil: Profil, debut_min: int, duree_min: int) -> tuple[np.ndarray, np.ndarray]:
    """(part_jour, sigma_bps) sur les `duree_min` minutes qui démarrent à `debut_min`."""
    s = slice(debut_min, debut_min + duree_min)
    return profil.part_jour[s], profil.sigma_min_bps[s]
