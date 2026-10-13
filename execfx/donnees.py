"""Lecture des minutes EURUSD HistData (lecture seule), déjà à l'heure de New York.

Format source : un zip par année, `DAT_MT_EURUSD_M1_AAAA.csv` sans en-tête,
`AAAA.MM.JJ,HH:MM,open,high,low,close,volume`. Prix BID, volume = 0 partout (le FX est OTC : pas de
volume centralisé). FUSEAU : malgré la documentation « EST sans heure d'été », les fichiers sont à l'heure
LOCALE de New York (heure d'été comprise). Preuve mesurée : le NFP (8h30 ET) fait le pic de la journée à
8h30 l'été comme l'hiver, la réouverture du dimanche est à 17h00 et la dernière barre du vendredi à 16h59
en toute saison (en UTC-5 fixe on aurait 7h30, 16h00 et 15h59 l'été). Test : `test_fuseau_...` (tests/test_tca.py).

Le TEST (2023+) est SCELLÉ par construction : `charger_annee` refuse toute année >= 2023.
"""
from __future__ import annotations

import datetime as dt
import os
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ANNEES_TRAIN = tuple(range(2010, 2019))  # calibration des profils et des paramètres
ANNEES_VAL = tuple(range(2019, 2023))    # évaluation
ANNEE_TEST_DEBUT = 2023                  # scellé : jamais lu ici


def _candidats() -> list[Path]:
    """Dossiers où chercher les zips `EURUSD_AAAA.zip`, par ordre de priorité. Aucun chemin absolu de machine."""
    cands: list[Path] = []
    if os.environ.get("HISTDATA_DIR"):  # convention commune du portfolio : <HISTDATA_DIR>/histdata_raw/EURUSD/
        cands.append(Path(os.environ["HISTDATA_DIR"]) / "histdata_raw" / "EURUSD")
    if os.environ.get("EXECFX_DONNEES"):  # ancienne variable, conservée : dossier des zips lui-même
        cands.append(Path(os.environ["EXECFX_DONNEES"]))
    here = Path(__file__).resolve()
    cands.append(here.parents[1] / "data" / "histdata" / "histdata_raw" / "EURUSD")  # défaut documenté, hors git
    # disposition du dépôt de travail : <racine>/data/histdata_raw/EURUSD, trouvée en remontant les parents
    cands.extend(p / "data" / "histdata_raw" / "EURUSD" for p in here.parents)
    return cands


def _dossier_donnees() -> Path:
    """Premier dossier candidat qui existe ; FileNotFoundError explicite sinon (les tests sont alors sautés)."""
    for cand in _candidats():
        if cand.is_dir():
            return cand
    raise FileNotFoundError("Minutes EURUSD HistData introuvables : définir HISTDATA_DIR (racine qui contient "
                            "histdata_raw/EURUSD/EURUSD_AAAA.zip), voir le README, section « Reproduire ».")


def donnees_disponibles(annees: tuple[int, ...] = (2018, 2019)) -> bool:
    """True si les zips des années demandées sont lisibles ; sert aux `skipif` des tests qui lisent le marché."""
    try:
        dossier = _dossier_donnees()
    except FileNotFoundError:
        return False
    return all((dossier / f"EURUSD_{a}.zip").is_file() for a in annees)


def _refuser_test(annee: int) -> None:
    if annee >= ANNEE_TEST_DEBUT:
        raise ValueError(f"{annee} appartient au TEST (>= {ANNEE_TEST_DEBUT}) : scellé, interdit.")


def charger_annee(annee: int) -> tuple[np.ndarray, np.ndarray]:
    """Retourne (dates[n_jours] datetime64[D], close[n_jours, 1440]) à l'heure locale de New York (voir l'en-tête), NaN si minute absente."""
    _refuser_test(annee)
    chemin = _dossier_donnees() / f"EURUSD_{annee}.zip"
    with zipfile.ZipFile(chemin) as z:
        nom = f"DAT_MT_EURUSD_M1_{annee}.csv"
        with z.open(nom) as f:
            df = pd.read_csv(f, header=None, usecols=[0, 1, 5], names=["d", "h", "c"],
                             dtype={"d": str, "h": str, "c": float})
    jours = pd.to_datetime(df["d"], format="%Y.%m.%d").to_numpy().astype("datetime64[D]")
    minute = df["h"].str.slice(0, 2).astype(int).to_numpy() * 60 + df["h"].str.slice(3, 5).astype(int).to_numpy()
    uniques, inv = np.unique(jours, return_inverse=True)
    mat = np.full((len(uniques), 1440), np.nan)
    mat[inv, minute] = df["c"].to_numpy()
    return uniques, mat


@lru_cache(maxsize=8)
def charger_annees(annees: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    """Concatène plusieurs années (dates, close[n_jours, 1440]) à l'heure locale de New York."""
    for a in annees:  # le sceau est vérifié AVANT toute lecture : même sans données, une année TEST est refusée
        _refuser_test(a)
    res = [charger_annee(a) for a in annees]
    return np.concatenate([r[0] for r in res]), np.concatenate([r[1] for r in res], axis=0)


def _dimanche_n(annee: int, mois: int, n: int) -> dt.date:
    """n-ième dimanche du mois."""
    d = dt.date(annee, mois, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)  # premier dimanche
    return d + dt.timedelta(weeks=n - 1)


def est_heure_ete_us(dates: np.ndarray) -> np.ndarray:
    """True si New York est en heure d'été (EDT) ce jour-là : 2e dimanche de mars -> 1er dimanche de novembre.

    Approximation au jour près (le basculement a lieu à 2h du matin), sans effet sur 8h-9h.
    """
    res = np.zeros(len(dates), dtype=bool)
    for i, d in enumerate(dates.astype("datetime64[D]").astype(object)):
        res[i] = _dimanche_n(d.year, 3, 2) <= d < _dimanche_n(d.year, 11, 1)
    return res


def vers_heure_ny(dates: np.ndarray, mat_est: np.ndarray) -> np.ndarray:
    """Matrice (jours, 1440) en heure locale de New York : AUCUN décalage à appliquer, les données le sont déjà.

    Historique : une version précédente décalait de +60 min les jours d'été en supposant l'EST fixe. C'était
    faux (voir l'en-tête du module) : le pic des annonces de 8h30 partait à 9h30 et la fenêtre 8h-9h des jours
    d'été ne contenait plus d'annonce. La fonction est conservée pour garder l'API, elle renvoie une copie.
    """
    return mat_est.copy()


@lru_cache(maxsize=8)
def matrice_ny(annees: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    """(dates, close[n_jours, 1440]) en heure locale de New York, jours ouvrés (lun-ven) uniquement."""
    dates, mat = charger_annees(annees)
    mat = vers_heure_ny(dates, mat)
    ouvre = pd.DatetimeIndex(dates).dayofweek < 5
    return dates[ouvre], mat[ouvre]
