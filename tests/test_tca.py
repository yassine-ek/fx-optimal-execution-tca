import numpy as np
import pytest

from conftest import fenetre_aleatoire
from execfx import donnees, impact, profils, tca
from outils_donnees import besoin_donnees


def _strategies(ctx):
    return tca.strategies_standard(ctx, (0.01, 0.05, 0.3))


def test_toutes_les_strategies_terminent_l_ordre(ctx):
    prix = fenetre_aleatoire(np.random.default_rng(3), ctx)
    for s in _strategies(ctx):
        n = tca.decider(prix, s, ctx)
        assert n.sum() == pytest.approx(1.0, abs=1e-12) and np.all(n >= 0), s.nom


@pytest.mark.parametrize("k0", [0, 7, 30, 58])
def test_pas_de_look_ahead(ctx, k0):
    """Changer les prix FUTURS (après la minute k0) ne doit jamais changer les décisions jusqu'à k0 incluse."""
    rng = np.random.default_rng(4)
    prix = fenetre_aleatoire(rng, ctx)
    futur = prix.copy()
    reste = len(prix) - ctx.H - k0 - 1
    futur[ctx.H + k0 + 1:] *= np.exp(np.cumsum(rng.standard_normal(reste)) * 5e-4)  # un autre futur, très différent
    for s in _strategies(ctx):
        n1, n2 = tca.decider(prix, s, ctx), tca.decider(futur, s, ctx)
        assert np.array_equal(n1[: k0 + 1], n2[: k0 + 1]), f"{s.nom} regarde le futur"


def test_le_test_anti_look_ahead_a_du_pouvoir(ctx):
    """Garde-fou : POV DOIT réagir à un changement du PASSÉ (sinon le test précédent serait vide)."""
    rng = np.random.default_rng(5)
    prix = fenetre_aleatoire(rng, ctx)
    agite = prix.copy()
    agite[: ctx.H + 10] = prix[0] * np.exp(np.cumsum(rng.standard_normal(ctx.H + 10)) * 8e-4)
    agite[ctx.H + 10:] += agite[ctx.H + 9] - prix[ctx.H + 9]  # raccord : seul le passé change
    pov = _strategies(ctx)[-1]
    assert pov.nom == "POV-proxy"
    assert not np.array_equal(tca.decider(prix, pov, ctx)[:20], tca.decider(agite, pov, ctx)[:20])


def test_decision_ne_recoit_que_le_passe(ctx):
    """La tranche k reçoit exactement H+k+1 prix (clôtures jusqu'à la minute précédente)."""
    vus = []

    class Espion:
        nom, adaptative = "espion", True

        def quantite(self, k, reste, prix_visibles):
            vus.append(len(prix_visibles))
            return reste if k == ctx.N - 1 else 1.0 / ctx.N

    tca.decider(fenetre_aleatoire(np.random.default_rng(6), ctx), Espion(), ctx)
    assert vus == [ctx.H + k + 1 for k in range(ctx.N)]


def test_impact_croit_avec_l_urgence(ctx):
    """Plus on exécute tôt, plus le coût d'impact est élevé (c'est le prix de la réduction de risque)."""
    prix = fenetre_aleatoire(np.random.default_rng(7), ctx)
    s = {x.nom: x for x in _strategies(ctx)}
    imp = {k: tca.chiffrer(prix, tca.decider(prix, s[k], ctx), ctx)[1] for k in ("TWAP", "AC-lam1", "AC-lam2", "AC-lam3")}
    assert imp["TWAP"] < imp["AC-lam1"] < imp["AC-lam2"] < imp["AC-lam3"]


def test_impact_racine_calibre_sur_le_lineaire_au_point_de_reference(profil_synthetique):
    hyp = impact.Hypotheses()
    c_rac = tca.construire_contexte(profil_synthetique, hyp, "racine")
    rho_ref = hyp.notionnel_eur / impact.volume_minute_eur(hyp, c_rac.part).sum()
    sigma_moy = float(np.mean(c_rac.sigma))
    assert c_rac.modele.temporaire_bps(np.array(rho_ref), sigma_moy) == pytest.approx(hyp.eta_bps * rho_ref)


def test_reproductibilite_du_resume_bootstrap(ctx):
    rng = np.random.default_rng(8)
    fen = np.array([fenetre_aleatoire(rng, ctx) for _ in range(40)])
    strats = _strategies(ctx)
    r1 = tca.resumer(tca.executer_jours(fen, strats, ctx), np.random.default_rng(11), B=200)
    r2 = tca.resumer(tca.executer_jours(fen, strats, ctx), np.random.default_rng(11), B=200)
    assert r1 == r2
    assert r1["TWAP"]["diff_moyen_vs_twap_bps"] == 0.0
    for v in r1.values():
        lo, hi = v["ic95_moyen_bps"]
        assert lo <= v["shortfall_moyen_bps"] <= hi


def test_achat_et_vente_font_disparaitre_la_derive_dans_la_moyenne(ctx):
    """Moyenne (achat + vente) = coût d'impact pur : la dérive du prix ne biaise pas la comparaison."""
    fen = np.array([fenetre_aleatoire(np.random.default_rng(i), ctx) for i in range(10)])
    res = tca.executer_jours(fen, _strategies(ctx)[:2], ctx)
    for r in res.values():
        assert np.allclose(r.echantillons().mean(axis=1), r.impact)


def test_test_2023_est_scelle():
    with pytest.raises(ValueError):
        donnees.charger_annee(2023)
    with pytest.raises(ValueError):
        donnees.charger_annees((2022, 2024))


@besoin_donnees
def test_profil_sur_donnees_reelles_2019():
    dates, mat = donnees.charger_annee(2019)
    assert mat.shape[1] == 1440 and 250 <= len(dates) <= 370
    p = profils.calibrer_profil(mat)
    assert p.part_jour.sum() == pytest.approx(1.0)
    assert np.all(p.sigma_min_bps > 0)


@besoin_donnees
def test_fuseau_les_annonces_us_de_8h30_sont_a_8h30_en_ete_comme_en_hiver():
    """Régression : les zips HistData sont déjà à l'heure LOCALE de New York (avec heure d'été), pas en EST fixe.

    Preuve : le NFP (8h30 ET) fait la plus grosse barre de la journée à 8h30 l'été (EDT) comme l'hiver (EST).
    Décaler les jours d'été de +60 min (l'ancienne `vers_heure_ny`) envoyait le pic à 9h30 : la fenêtre 8h-9h
    de l'été ne contenait plus aucune annonce américaine.
    """
    dates, mat = donnees.matrice_ny((2018, 2019))
    dates = np.asarray(dates).astype("datetime64[D]")
    nfp = {"2018-02-02": "hiver", "2018-12-07": "hiver", "2019-01-04": "hiver", "2019-12-06": "hiver",
           "2018-07-06": "ete", "2018-08-03": "ete", "2019-06-07": "ete", "2019-07-05": "ete"}
    for d, saison in nfp.items():
        ligne = np.abs(np.diff(mat[dates == np.datetime64(d)][0]))
        pic = int(np.nanargmax(ligne)) + 1  # minute de la barre qui bouge le plus
        assert 510 <= pic <= 512, f"{d} ({saison}) : pic à {pic // 60}h{pic % 60:02d}, attendu 8h30"
    # et en moyenne sur les jours d'été : le maximum d'activité entre 6h et 11h est bien à 8h30
    mois = dates.astype("datetime64[M]").astype(int) % 12 + 1
    ete = (mois >= 6) & (mois <= 8)
    activite = np.nanmean(np.abs(np.diff(mat[ete], axis=1)), axis=0)
    assert 360 + int(np.argmax(activite[359:659])) + 1 in range(510, 513)


@besoin_donnees
def test_fuseau_la_semaine_rouvre_le_dimanche_a_17h_aussi_en_juillet():
    """Régression : réouverture hebdomadaire EURUSD = dimanche 17h00 heure de New York, hiver comme été.

    En UTC-5 fixe elle serait à 16h00 en juillet (EDT = UTC-4) : c'est le second marqueur du fuseau, indépendant du NFP.
    """
    dates, mat = donnees.charger_annee(2019)
    dates = np.asarray(dates).astype("datetime64[D]")
    for d in ("2019-07-07", "2019-07-14", "2019-07-21", "2019-07-28", "2019-01-13", "2019-01-20"):
        ligne = mat[dates == np.datetime64(d)][0]
        assert int(np.argmax(~np.isnan(ligne))) == 17 * 60, d
