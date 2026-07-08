"""
black_scholes.py
-----------------
Calcul du gamma Black-Scholes, vectorisé avec numpy/scipy.

Pourquoi ce module remplace mibian :
- mibian n'est plus maintenu et plante souvent avec les versions récentes de numpy.
- Cette implémentation est ~100% plus rapide (vectorisée) car on en a besoin
  des centaines de fois pour calculer le "gamma profile" (cf gex.py).

Utilisé uniquement pour QQQ / GLD (yfinance ne fournit pas le gamma directement).
Pour SPX / NDX, CBOE fournit déjà le gamma calculé -> pas besoin de ce module.
"""

import numpy as np
from scipy.stats import norm


def bs_gamma(S, K, iv, T, r: float = 0.0, q: float = 0.0):
    """
    Gamma Black-Scholes (identique pour call et put).

    Paramètres
    ----------
    S : float ou array - prix spot du sous-jacent
    K : float ou array - strike
    iv : float ou array - volatilité implicite annualisée, en décimal (0.20 = 20%)
    T : float ou array - temps jusqu'à expiration, en années
    r : taux sans risque (par défaut 0, négligeable pour le gamma sur du court terme)
    q : rendement de dividende (0 par défaut, ajustable si besoin)

    Retourne
    -------
    gamma : array numpy, même shape que les inputs broadcastés
    """
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    iv = np.asarray(iv, dtype=float)
    T = np.asarray(T, dtype=float)

    # Garde-fous numériques : évite division par zéro / log(0) / vol nulle
    T = np.maximum(T, 1.0 / 365.0)   # plancher à 1 jour
    iv = np.maximum(iv, 1e-4)        # plancher à 0.01% de vol
    S = np.maximum(S, 1e-6)
    K = np.maximum(K, 1e-6)

    d1 = (np.log(S / K) + (r - q + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * iv * np.sqrt(T))
    return gamma

def bs_delta(S, K, iv, T, opt_type, r: float = 0.0, q: float = 0.0):
    """
    Delta Black-Scholes.

    Paramètres identiques à bs_gamma, plus :
    opt_type : "Call" ou "Put"

    Retourne
    -------
    delta : array numpy, même shape que les inputs broadcastés
    """
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    iv = np.asarray(iv, dtype=float)
    T = np.asarray(T, dtype=float)

    T = np.maximum(T, 1.0 / 365.0)
    iv = np.maximum(iv, 1e-4)
    S = np.maximum(S, 1e-6)
    K = np.maximum(K, 1e-6)

    d1 = (np.log(S / K) + (r - q + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))

    if opt_type == "Call":
        delta = np.exp(-q * T) * norm.cdf(d1)
    else:
        delta = np.exp(-q * T) * (norm.cdf(d1) - 1)

    return delta
