import numpy as np
import pytest

from execfx import almgren_chriss as ac
from execfx.impact import Hypotheses, cout_impact_bps, modele_lineaire, theta_par_tranche

N, SIGMA, THETA, GAMMA, EPS = 60, 2.0, 100.0, 0.5, 0.1
LAMS = [0.0, 1e-4, 0.01, 0.05, 0.3, 3.0]


@pytest.mark.parametrize("lam", LAMS)
def test_trajectoire_somme_X_et_monotone(lam):
    x = ac.detentions(N, lam, SIGMA, THETA, GAMMA)
    n = ac.trajectoire_optimale(N, lam, SIGMA, THETA, GAMMA)
    assert x[0] == pytest.approx(1.0) and x[-1] == pytest.approx(0.0, abs=1e-12)
    assert np.all(np.diff(x) <= 1e-15), "le stock restant doit décroître"
    assert np.all(n >= -1e-15) and n.sum() == pytest.approx(1.0, abs=1e-12)


def test_formule_sinh_explicite():
    lam = 0.05
    k = ac.kappa(lam, SIGMA, THETA, GAMMA)
    j = np.arange(N + 1)
    attendu = np.sinh(k * (N - j)) / np.sinh(k * N)
    assert np.allclose(ac.detentions(N, lam, SIGMA, THETA, GAMMA), attendu, atol=1e-12)


def test_lambda_vers_zero_donne_twap():
    twap = np.full(N, 1.0 / N)
    assert np.allclose(ac.trajectoire_optimale(N, 0.0, SIGMA, THETA, GAMMA), twap)
    assert np.allclose(ac.trajectoire_optimale(N, 1e-12, SIGMA, THETA, GAMMA), twap, atol=1e-6)


def test_variance_decroit_et_cout_croit_avec_lambda():
    f = ac.frontiere(np.array([0.0] + list(np.logspace(-3, 1, 30))), N, SIGMA, THETA, GAMMA, EPS)
    assert np.all(np.diff(f["std_bps"]) < 0), "plus lam est grand, moins de risque"
    assert np.all(np.diff(f["E_bps"]) > 0), "...mais plus d'impact : c'est la frontière efficiente"


def test_trajectoire_minimise_E_plus_lambda_V():
    """La formule fermée est bien l'optimum de E + lam*Var : aucune perturbation admissible ne fait mieux."""
    lam = 0.05
    n0 = ac.trajectoire_optimale(N, lam, SIGMA, THETA, GAMMA)

    def J(n):
        return ac.esperance_cout(n, THETA, GAMMA, EPS) + lam * ac.variance_cout(n, SIGMA)

    rng = np.random.default_rng(1)
    for _ in range(200):
        d = rng.standard_normal(N) * 1e-3
        d -= d.mean()  # la somme reste 1
        assert J(n0 + d) >= J(n0) - 1e-9


def test_variance_formule_vs_monte_carlo():
    rng = np.random.default_rng(2)
    n = ac.trajectoire_optimale(N, 0.05, SIGMA, THETA, GAMMA)
    W = np.concatenate([np.zeros((200_000, 1)), np.cumsum(rng.standard_normal((200_000, N - 1)) * SIGMA, axis=1)], axis=1)
    bruit = W @ n  # le prix de la tranche k est W_{k-1}
    assert bruit.var() == pytest.approx(ac.variance_cout(n, SIGMA), rel=0.02)


def test_esperance_ac_egale_au_cout_du_simulateur():
    """Le modèle d'impact linéaire du TCA et la formule fermée d'AC donnent le même coût (volume constant)."""
    hyp = Hypotheses()
    part = np.full(N, 1.0 / 1440 * 1.7)
    theta_k = theta_par_tranche(hyp, part)
    n = ac.trajectoire_optimale(N, 0.05, SIGMA, float(theta_k[0]), hyp.gamma_bps)
    vol = hyp.volume_jour_eur * part
    sim = cout_impact_bps(n, vol, np.full(N, SIGMA), hyp, modele_lineaire(hyp))
    assert sim == pytest.approx(ac.esperance_cout(n, theta_k, hyp.gamma_bps, hyp.demi_spread_bps), rel=1e-12)


def test_lambda_pour_kappaT_est_inverse_de_kappa():
    lam = ac.lambda_pour_kappaT(3.0, N, SIGMA, THETA, GAMMA)
    assert ac.kappa(lam, SIGMA, THETA, GAMMA) * N == pytest.approx(3.0)
