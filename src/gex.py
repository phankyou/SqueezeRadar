"""
gex.py
------
Le coeur du calcul : Gamma Exposure (GEX), Gamma Notional, Zero Gamma Level,
Call Wall / Put Wall, et niveaux GEX max/min.

Méthodologie suivie : article de Perfiliev
(https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/)

Convention de signe utilisée (standard dans l'industrie des GEX trackers) :
- Calls -> GEX positif (les dealers sont supposés long gamma sur les calls qu'ils ont vendus)
- Puts  -> GEX négatif
- GEX par contrat = gamma * open_interest * 100 (multiplicateur contrat) * spot^2 * 0.01
  (le "* 0.01" traduit l'exposition pour un mouvement de 1% du sous-jacent)
"""

import numpy as np
import pandas as pd
from datetime import datetime

from .black_scholes import bs_gamma

CONTRACT_MULTIPLIER = 100


def compute_gex_per_contract(df: pd.DataFrame, spot: float, use_provided_gamma: bool = True) -> pd.DataFrame:
    """
    Ajoute les colonnes 'gamma' (si besoin) et 'gex' au DataFrame.

    use_provided_gamma=True -> utilise la colonne 'gamma' déjà présente (cas CBOE: SPX, NDX)
    use_provided_gamma=False -> calcule le gamma via Black-Scholes (cas yfinance: QQQ, GLD)

    Sécurité : on filtre ici les lignes avec des valeurs manquantes/invalides (NaN) sur les
    colonnes essentielles. Sans ça, une seule ligne corrompue (donnée de marché incomplète
    ce jour-là, IV manquante, etc.) peut faire planter TOUT le pipeline plus loin avec une
    erreur "Out of range float values are not JSON compliant: nan" lors de l'envoi vers
    Google Sheets (qui n'accepte pas le NaN).
    """
    df = df.copy()

    required_cols = ["strike", "iv", "days", "open_interest"]
    df = df.dropna(subset=[c for c in required_cols if c in df.columns])

    if not use_provided_gamma or "gamma" not in df.columns:
        T = df["days"].values / 365.0
        df["gamma"] = bs_gamma(spot, df["strike"].values, df["iv"].values, T)

    # On retire aussi les lignes où le gamma calculé/fourni serait lui-même invalide
    df = df[np.isfinite(df["gamma"])]

    exposure = df["gamma"] * df["open_interest"] * CONTRACT_MULTIPLIER * (spot ** 2) * 0.01
    is_put = df["type"].str.lower().str.startswith("p")
    df["gex"] = np.where(is_put, -exposure, exposure)
    return df


def net_gamma_exposure(df: pd.DataFrame) -> float:
    """Gamma net = somme de tous les GEX (calls + puts). En $ par mouvement de 1%."""
    return float(df["gex"].sum())


def gamma_notional(df: pd.DataFrame) -> dict:
    """Détail du gamma notional : calls, puts, net. (Perfiliev appelle ça 'Gamma Notional')."""
    is_call = df["type"].str.lower().str.startswith("c")
    is_put = df["type"].str.lower().str.startswith("p")
    calls = float(df.loc[is_call, "gex"].sum())
    puts = float(df.loc[is_put, "gex"].sum())
    return {
        "call_gamma_notional": calls,
        "put_gamma_notional": puts,
        "net_gamma_notional": calls + puts,
    }


def gex_by_strike_0dte(df: pd.DataFrame) -> pd.Series:
    """
    Agrège le GEX par strike uniquement pour les options 0DTE (expirant aujourd'hui).
    Utile pour le day trading et le scalping sur NQ/ES.
    """
    today = datetime.now().date()
    if "expiry" in df.columns:
        mask = df["expiry"].apply(lambda x: x.date() == today if hasattr(x, 'date') else False)
    elif "days" in df.columns:
        mask = df["days"] <= 1
    else:
        return pd.Series(dtype=float)
    sub = df[mask]
    if sub.empty:
        return pd.Series(dtype=float)
    return sub.groupby("strike")["gex"].sum().sort_index()


def gex_by_strike(df: pd.DataFrame) -> pd.Series:
    """Agrège le GEX par strike -> utilisé pour le graphique 'GEX by strike'."""
    return df.groupby("strike")["gex"].sum().sort_index()


def gex_max_min_levels(df: pd.DataFrame) -> dict:
    """Strikes où le GEX est maximal (résistance la plus forte) et minimal (support le plus fort)."""
    by_strike = gex_by_strike(df)
    if by_strike.empty:
        return {"gex_max_strike": None, "gex_max_value": None, "gex_min_strike": None, "gex_min_value": None}
    max_strike = by_strike.idxmax()
    min_strike = by_strike.idxmin()
    return {
        "gex_max_strike": float(max_strike),
        "gex_max_value": float(by_strike.loc[max_strike]),
        "gex_min_strike": float(min_strike),
        "gex_min_value": float(by_strike.loc[min_strike]),
    }


def call_wall(df: pd.DataFrame):
    """Strike avec le plus de GEX positif côté calls -> résistance probable."""
    calls = df[df["type"].str.lower().str.startswith("c")]
    if calls.empty:
        return None
    by_strike = calls.groupby("strike")["gex"].sum()
    return float(by_strike.idxmax())


def put_wall(df: pd.DataFrame):
    """Strike avec le plus de GEX négatif côté puts (en valeur absolue) -> support probable."""
    puts = df[df["type"].str.lower().str.startswith("p")]
    if puts.empty:
        return None
    by_strike = puts.groupby("strike")["gex"].sum()
    return float(by_strike.idxmin())


def top_gamma_concentrations(df: pd.DataFrame, spot: float, side: str, n: int = 3) -> list:
    """
    Retourne les n strikes avec la plus forte concentration de GEX (en valeur absolue)
    pour un côté donné ('Call' ou 'Put'), avec leur distance en % au spot.

    Sert à donner une vraie "carte" des zones de friction, pas juste le mur n°1.
    (Recommandation SpotGamma : regarder où se situent les concentrations clés
    par rapport au prix actuel, pas seulement le signe du gamma net.)
    """
    side_prefix = side[0].lower()  # "c" ou "p"
    sub = df[df["type"].str.lower().str.startswith(side_prefix)]
    if sub.empty:
        return []

    by_strike = sub.groupby("strike")["gex"].sum()
    top_strikes = by_strike.abs().sort_values(ascending=False).head(n).index

    results = []
    for strike in top_strikes:
        gex_value = float(by_strike.loc[strike])
        distance_pct = float((strike - spot) / spot * 100)
        results.append({"strike": float(strike), "gex": gex_value, "distance_pct": distance_pct})

    # Trié par magnitude de GEX décroissante (déjà fait via head(n) sur l'abs, on réordonne pour affichage clair)
    results.sort(key=lambda r: abs(r["gex"]), reverse=True)
    return results


def find_zero_crossing(x: np.ndarray, y: np.ndarray):
    """Interpolation linéaire pour trouver le x où y croise 0. None si pas de croisement."""
    sign_changes = np.where(np.diff(np.sign(y)) != 0)[0]
    if len(sign_changes) == 0:
        return None
    i = sign_changes[0]
    x0, x1 = x[i], x[i + 1]
    y0, y1 = y[i], y[i + 1]
    if y1 == y0:
        return float(x0)
    return float(x0 + (0 - y0) * (x1 - x0) / (y1 - y0))


def gamma_profile(df: pd.DataFrame, spot: float, pct_range: float = 0.15, n_points: int = 121):
    """
    Recalcule le GEX net pour une plage de prix spot hypothétiques (+/- pct_range autour du spot actuel).
    C'est ÇA qui donne le "Zero Gamma Level" (le niveau où le marché bascule de gamma négatif à positif).

    Important : on recalcule TOUJOURS le gamma via Black-Scholes ici (même pour SPX/NDX où CBOE
    fournit le gamma au spot actuel), car on a besoin du gamma comme fonction du spot, pas juste
    sa valeur au prix courant.

    Retourne
    -------
    spot_range : array des prix spot testés
    profile : array du GEX net pour chaque prix
    zero_gamma_level : float ou None
    """
    spot_range = np.linspace(spot * (1 - pct_range), spot * (1 + pct_range), n_points)

    T = df["days"].values / 365.0
    K = df["strike"].values
    iv = df["iv"].values
    oi = df["open_interest"].values
    is_put = df["type"].str.lower().str.startswith("p").values

    profile = np.empty(len(spot_range))
    for idx, s in enumerate(spot_range):
        g = bs_gamma(s, K, iv, T)
        exposure = g * oi * CONTRACT_MULTIPLIER * (s ** 2) * 0.01
        exposure = np.where(is_put, -exposure, exposure)
        profile[idx] = exposure.sum()

    zero_gamma_level = find_zero_crossing(spot_range, profile)
    return spot_range, profile, zero_gamma_level
