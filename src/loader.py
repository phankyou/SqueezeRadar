"""
loader.py
---------
Charge les chaines d'options via yfinance pour les proxies utilises par
SqueezeRadar : QQQ (proxy NQ), SPY (proxy ES), GLD (proxy GC).

Contrairement au loader de GammaDashboard, celui-ci recupere aussi le
volume et le dernier prix (premium) de chaque option, necessaires pour :
- le ratio Volume / Open Interest
- le calcul du runway des vendeurs (distance au breakeven)
"""

from datetime import datetime

import pandas as pd


def load_yf_options(symbol: str, min_open_interest: int = 1, max_iv: float = 3.0):
    """
    Charge la chaine d'options complete pour un ticker proxy (QQQ, SPY, GLD).

    Retourne
    -------
    spot : float
    df : DataFrame avec colonnes
         [strike, type, expiry, days, iv, open_interest, volume, premium]
    """
    import yfinance as yf

    ticker = yf.Ticker(symbol)

    hist = ticker.history(period="1d")
    if hist.empty:
        hist = ticker.history(period="5d")
    if hist.empty:
        raise ValueError(
            f"Impossible de recuperer le prix spot pour {symbol} via yfinance "
            f"(donnees vides meme en period='5d'). Reessaie dans quelques minutes."
        )
    spot = float(hist["Close"].iloc[-1])
    now = datetime.now()

    rows = []
    for expiry_str in ticker.options:
        chain = ticker.option_chain(expiry_str)
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d")
        days = max(1, (expiry - now).days)

        for opt_type, sub_df in (("Call", chain.calls), ("Put", chain.puts)):
            sub_df = sub_df.copy()
            sub_df["type"] = opt_type
            sub_df["expiry"] = expiry
            sub_df["days"] = days
            rows.append(sub_df)

    full = pd.concat(rows, ignore_index=True)
    full = full.rename(
        columns={
            "openInterest": "open_interest",
            "impliedVolatility": "iv",
            "lastPrice": "premium",
        }
    )
    full["open_interest"] = full["open_interest"].fillna(0)
    full["iv"] = full["iv"].fillna(0)
    full["volume"] = full["volume"].fillna(0)
    full["premium"] = full["premium"].fillna(0)

    full = full[
        (full["open_interest"] >= min_open_interest)
        & (full["iv"] > 0.001)
        & (full["iv"] < max_iv)
    ]

    return spot, full[
        ["strike", "type", "expiry", "days", "iv", "open_interest", "volume", "premium"]
    ]
