"""Fixtures partagées : profil synthétique (les tests n'ont pas besoin des données réelles) et fenêtres de prix aléatoires."""
import numpy as np
import pytest

from execfx import tca
from execfx.impact import Hypotheses
from execfx.profils import Profil


@pytest.fixture(scope="session")
def profil_synthetique():
    rng = np.random.default_rng(0)
    act = 1.0 + 0.3 * rng.random(1440)
    act[510] = 3.0  # un pic type annonces 8h30
    sigma = act * 1.6
    return Profil(act, sigma, act / act.sum(), n_jours=100)


@pytest.fixture(scope="session")
def ctx(profil_synthetique):
    return tca.construire_contexte(profil_synthetique, Hypotheses(), "lineaire")


def fenetre_aleatoire(rng, ctx, vol_bps=1.8):
    """Prix de longueur H+N+1 : marche aléatoire log autour de 1.10."""
    n = ctx.H + ctx.N + 1
    return 1.10 * np.exp(np.cumsum(rng.standard_normal(n)) * vol_bps * 1e-4)
