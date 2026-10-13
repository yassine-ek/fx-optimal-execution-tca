"""Sans les minutes HistData, les scripts disent quoi faire (lien, arborescence, variable) au lieu d'afficher une trace brute."""
import pytest

from execfx import donnees


def _sans_donnees(monkeypatch, tmp_path):
    monkeypatch.setattr(donnees, "_candidats", lambda: [tmp_path / "absent"])


def test_message_guide_quand_les_donnees_manquent(monkeypatch, tmp_path):
    _sans_donnees(monkeypatch, tmp_path)
    with pytest.raises(donnees.DonneesIntrouvables) as e:
        donnees._dossier_donnees()
    message = str(e.value)
    assert "histdata.com" in message and "HISTDATA_DIR" in message and "EURUSD_AAAA.zip" in message


def test_les_scripts_sortent_proprement_sans_trace_brute(monkeypatch, tmp_path, capsys):
    _sans_donnees(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as sortie:
        donnees.executer_avec_message_clair(lambda: donnees.charger_annees((2019,)))
    assert "histdata.com" in str(sortie.value) and "Traceback" not in str(sortie.value)


def test_une_annee_manquante_est_signalee_avec_le_dossier(monkeypatch, tmp_path):
    monkeypatch.setattr(donnees, "_candidats", lambda: [tmp_path])  # dossier existant mais vide
    with pytest.raises(donnees.DonneesIntrouvables, match="EURUSD_2019.zip"):
        donnees.charger_annee(2019)
