"""Détection des données locales : les tests qui lisent le marché sont sautés proprement (skipif) si elles manquent.

Les minutes EURUSD HistData ne sont pas versionnées. Pour lancer la suite complète :
    export HISTDATA_DIR=/chemin/vers/les/donnees     # contient histdata_raw/EURUSD/EURUSD_AAAA.zip
Sans cela (cas de l'intégration continue), seuls les tests synthétiques et ceux qui lisent results/ tournent.
"""
import pytest

from execfx import donnees

MOTIF = "minutes EURUSD HistData absentes : définir HISTDATA_DIR (voir README, section Reproduire)"
besoin_donnees = pytest.mark.skipif(not donnees.donnees_disponibles(), reason=MOTIF)
