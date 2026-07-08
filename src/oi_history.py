"""
oi_history.py
--------------
Lecture et ecriture de l'historique quotidien d'open interest, stocke
dans un CSV committe sur GitHub (data/oi_history.csv).

Pourquoi un CSV plutot que Google Sheets : pas de credentials a gerer,
pas de dependance externe, pas de quota API. Git garde l'historique
des versions gratuitement.

Format du CSV : date, asset, strike, type, open_interest
"""

import os
from datetime import datetime

import pandas as pd

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "oi_history.csv")
COLUMNS = ["date", "asset", "strike", "type", "open_interest"]


def load_oi_history(asset: str = None) -> pd.DataFrame:
    """
    Charge l'historique complet, ou filtre sur un actif donne (NQ, ES, GC).

    Retourne un DataFrame vide (avec les bonnes colonnes) si le fichier
    n'existe pas encore ou si l'actif n'a pas d'historique.
    """
    if not os.path.exists(HISTORY_PATH):
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(HISTORY_PATH, parse_dates=["date"])

    if asset is not None:
        df = df[df["asset"] == asset]

    return df


def append_daily_snapshot(asset: str, df_options: pd.DataFrame, snapshot_date=None) -> None:
    """
    Ajoute une ligne par strike/type pour la date donnee (aujourd'hui par
    defaut) dans le CSV historique. Ecrase les lignes existantes pour
    cette date+actif si le script est relance le meme jour (evite les
    doublons).

    df_options doit contenir au moins [strike, type, open_interest].
    """
    if snapshot_date is None:
        snapshot_date = datetime.now().date()

    new_rows = df_options[["strike", "type", "open_interest"]].copy()
    new_rows["date"] = pd.Timestamp(snapshot_date)
    new_rows["asset"] = asset
    new_rows = new_rows[COLUMNS]

    existing = load_oi_history()

    if not existing.empty:
        mask_same_day_asset = (
            (existing["date"].dt.date == snapshot_date) & (existing["asset"] == asset)
        )
        existing = existing[~mask_same_day_asset]

    combined = pd.concat([existing, new_rows], ignore_index=True)

    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    combined.to_csv(HISTORY_PATH, index=False)
