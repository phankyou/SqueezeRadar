"""
technical_levels.py
--------------------
Calcul automatique de niveaux techniques (support/resistance) a partir
de l'historique de prix du sous-jacent, via detection de plus hauts et
plus bas locaux sur une fenetre glissante.

Ces niveaux servent de badge de confirmation optionnel dans le score
de squeeze : un prix proche d'un niveau technique renforce la lecture
du setup, sans faire partie du score structurel lui-meme.
"""

import pandas as pd


def compute_technical_levels(symbol: str, period: str = "3mo",
                              window: int = 5, max_levels: int = 6) -> list:
    """
    Detecte des niveaux de support/resistance a partir des plus hauts et
    plus bas locaux sur l'historique de prix.

    symbol : ticker yfinance (QQQ, SPY, GLD)
    period : profondeur d'historique (ex "3mo", "6mo")
    window : taille de la fenetre pour detecter un plus haut/bas local
             (un point est un maximum local si c'est le plus haut sur
             window jours avant ET apres)
    max_levels : nombre max de niveaux retournes (les plus significatifs)

    Retourne une liste de floats (prix), triee.
    """
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period)

    if hist.empty or len(hist) < window * 2 + 1:
        return []

    highs = hist["High"].values
    lows = hist["Low"].values
    levels = []

    for i in range(window, len(hist) - window):
        local_high = highs[i]
        if local_high == max(highs[i - window:i + window + 1]):
            levels.append(float(local_high))

        local_low = lows[i]
        if local_low == min(lows[i - window:i + window + 1]):
            levels.append(float(local_low))

    if not levels:
        return []

    levels = sorted(set(round(l, 2) for l in levels))

    if len(levels) > max_levels:
        current_price = float(hist["Close"].iloc[-1])
        levels.sort(key=lambda l: abs(l - current_price))
        levels = sorted(levels[:max_levels])

    return levels
