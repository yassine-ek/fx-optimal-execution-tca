import dataclasses
import json

import numpy as np

from execfx import agregation as ag


def aleas_calmes(n, sens=1.0, rejeter=False):
    """Marché immobile, cotes sans bruit : seul l'étalement propre de chaque LP compte."""
    forme = (n, ag.NB_TOURS, ag.NB_LP)
    return {"chemin": np.zeros((n, ag.NB_AR + 1 + ag.NB_AV)), "zq": np.zeros(forme),
            "u": np.zeros(forme) if rejeter else np.ones(forme), "sens": np.full(n, sens)}


def lp_sans_bruit():
    return dataclasses.replace(ag.lp_par_defaut(), bruit=np.zeros(ag.NB_LP))


def test_routeur_a_choisit_le_meilleur_prix_affiche():
    cotes = np.array([0.30, 0.12, 0.05, 0.20, 0.08, 0.15, 0.25, 0.10])
    alloc = ag.allouer_tour1(cotes, np.full(ag.NB_LP, 30.0), 20.0)
    assert alloc[2] == 20.0 and alloc.sum() == 20.0


def test_routeur_a_dans_le_simulateur_va_chez_le_moins_cher():
    lp = lp_sans_bruit()
    r = ag.simuler(aleas_calmes(5), lp, "a_meilleur_affiche", 0.5, taille_meur=5.0)
    assert np.all(r["premier_lp"] == np.argmin(lp.demi_spread))
    assert np.allclose(r["cout_pips"], lp.demi_spread.min()) and np.allclose(r["remplissage"], 1.0)
    assert np.all(r["rejets"] == 0)


def test_last_look_rejette_quand_le_marche_bouge_contre_le_lp():
    lp = lp_sans_bruit()
    al = aleas_calmes(5, rejeter=True)  # u = 0 : le LP rejette dès que le seuil est franchi
    al["chemin"][:, ag.NB_AR + 1:] = 1.0  # le mid monte de 1 pip juste après l'envoi : mouvement contre le LP (achat)
    r = ag.simuler(al, lp, "a_meilleur_affiche", 1.0, taille_meur=5.0)
    assert np.all(r["rejets"] >= 1)
    assert np.all(r["cout_pips"] > lp.demi_spread.min() + 0.5), "après rejet on paie le marché qui a monté"
    vente = ag.simuler({**al, "sens": -al["sens"]}, lp, "a_meilleur_affiche", 1.0, taille_meur=5.0)
    assert np.all(vente["rejets"] == 0), "une hausse du mid avantage le LP face à une VENTE : pas de rejet"


def test_routeur_b_evite_un_lp_tres_risque():
    lp = lp_sans_bruit()
    phat, cbar = np.zeros(ag.NB_LP), np.zeros(ag.NB_LP)
    meilleur = int(np.argmin(lp.demi_spread))
    phat[meilleur], cbar[meilleur] = 0.9, 0.5  # appris : ce LP rejette 90 % du temps, re-routage coûteux
    a = ag.simuler(aleas_calmes(3), lp, "a_meilleur_affiche", 0.5, 5.0, phat, cbar)
    b = ag.simuler(aleas_calmes(3), lp, "b_prix_effectif", 0.5, 5.0, phat, cbar)
    assert np.all(a["premier_lp"] == meilleur) and np.all(b["premier_lp"] != meilleur)


def test_remplissage_entre_0_et_1_et_split_remplit():
    rng = np.random.default_rng(9)
    al = ag.generer_aleas(rng, np.full(300, 1.4 / np.sqrt(60000)))
    for r in ag.ROUTEURS:
        out = ag.simuler(al, ag.lp_par_defaut(), r, 0.9, 20.0)
        assert np.all((out["remplissage"] >= 0) & (out["remplissage"] <= 1 + 1e-9))
    s = ag.simuler(aleas_calmes(2), lp_sans_bruit(), "c_split", 0.5, 12.0, np.zeros(ag.NB_LP), np.zeros(ag.NB_LP))
    assert np.all(s["remplissage"] == 1.0)


def test_reproductibilite():
    def tout(seed):
        rng = np.random.default_rng(seed)
        mat = 1.1 + np.cumsum(rng.standard_normal((20, 1440)) * 1e-4, axis=1)
        sig = ag.tirer_minutes(mat, 400, rng)
        al = ag.generer_aleas(rng, sig)
        return ag.comparer_routeurs(al, al, ag.lp_par_defaut(), 0.5, 20.0), sig, al["chemin"]

    (c1, s1, p1), (c2, s2, p2) = tout(42), tout(42)
    # json.dumps : égalité tolérante aux NaN (un sous-ensemble vide donne NaN, et NaN != NaN)
    assert json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True)
    assert np.array_equal(s1, s2) and np.array_equal(p1, p2)
    assert tout(43)[1].tolist() != s1.tolist()
