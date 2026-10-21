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


def _load_cboe(symbol, min_open_interest=1, max_iv=3.0):
    """Chaine d'options via CBOE (gratuit, fonctionne sur Streamlit Cloud)."""
    import re
    import requests
    url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cboe.com/"})
    r.raise_for_status()
    data = r.json()["data"]
    spot = float(data["current_price"])
    now = datetime.now()
    pat = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")
    rows = []
    for o in data["options"]:
        m = pat.match(o.get("option", ""))
        if not m:
            continue
        expiry = datetime.strptime(m.group(2), "%y%m%d")
        bid = float(o.get("bid") or 0)
        ask = float(o.get("ask") or 0)
        last = float(o.get("last_trade_price") or 0)
        rows.append({
            "strike": int(m.group(4)) / 1000,
            "type": "Call" if m.group(3) == "C" else "Put",
            "expiry": expiry,
            "days": max(1, (expiry - now).days),
            "iv": float(o.get("iv") or 0),
            "open_interest": float(o.get("open_interest") or 0),
            "volume": float(o.get("volume") or 0),
            "premium": last if last > 0 else (bid + ask) / 2,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError(f"CBOE vide pour {symbol}")
    df = df[(df["open_interest"] >= min_open_interest) & (df["iv"] > 0.001) & (df["iv"] < max_iv)]
    if df.empty:
        raise ValueError(f"CBOE : aucune option valide pour {symbol}")
    cols = ["strike", "type", "expiry", "days", "iv", "open_interest", "volume", "premium"]
    return spot, df[cols].reset_index(drop=True)


def load_yf_options(symbol: str, min_open_interest: int = 1, max_iv: float = 3.0):
    """
    Charge la chaine d'options complete pour un ticker proxy (QQQ, SPY, GLD).

    Retourne
    -------
    spot : float
    df : DataFrame avec colonnes
         [strike, type, expiry, days, iv, open_interest, volume, premium]
    """
    try:
        return _load_cboe(symbol, min_open_interest, max_iv)
    except Exception:
        pass

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

    if not rows:
        raise ValueError(f"Aucune option pour {symbol} (CBOE et Yahoo vides). Reessaie dans quelques minutes.")
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
