"""
squeeze_detector.py
--------------------
Coeur logique de SqueezeRadar : detection d'un potentiel debut de squeeze.

Combine 3 signaux structurels (score /3) :
1. Concentration d'open interest isolee sur un strike proche du spot
2. Position du prix sous le Zero Gamma Level
3. Tendance de l'open interest en hausse sur ces strikes

Le score ne dit PAS si un squeeze va se produire : il compte combien
de conditions structurelles sont reunies. Il faut toujours un catalyseur
pour qu'un squeeze demarre reellement.

Le "runway" des vendeurs qualifie l'urgence : plus il est faible,
plus la meche est courte.
"""

import pandas as pd


def detect_isolated_oi(df: pd.DataFrame, spot_price: float,
                        oi_threshold_ratio: float = 3.0,
                        mirror_window_pct: float = 0.05) -> pd.DataFrame:
    """Detecte les strikes avec OI eleve et sans spread apparent."""
    results = []
    for opt_type in ["Call", "Put"]:
        sub = df[df["type"] == opt_type].sort_values("strike").reset_index(drop=True)
        if sub.empty:
            continue
        median_oi = sub["open_interest"].median()
        if median_oi <= 0:
            continue
        for _, row in sub.iterrows():
            if row["open_interest"] < oi_threshold_ratio * median_oi:
                continue
            window = spot_price * mirror_window_pct
            neighbors = sub[
                (sub["strike"] != row["strike"])
                & (sub["strike"].between(row["strike"] - window, row["strike"] + window))
            ]
            has_mirror = (neighbors["open_interest"] >= 0.5 * row["open_interest"]).any()
            results.append({
                "strike": row["strike"],
                "type": opt_type,
                "open_interest": row["open_interest"],
                "oi_vs_median": round(row["open_interest"] / median_oi, 1),
                "has_mirror_spread": has_mirror,
                "risk_flag": not has_mirror,
            })
    return pd.DataFrame(results)


def compute_oi_trend(oi_history: pd.DataFrame, strikes: list, lookback_days: int = 5) -> dict:
    """Direction de l'OI agrege sur ces strikes sur les derniers jours."""
    if oi_history is None or oi_history.empty or not strikes:
        return {"direction": "insuffisant", "change_pct": None}
    recent = oi_history[oi_history["strike"].isin(strikes)].sort_values("date")
    recent = recent.tail(lookback_days * max(len(strikes), 1))
    if recent["date"].nunique() < 2:
        return {"direction": "insuffisant", "change_pct": None}
    grouped = recent.groupby("date")["open_interest"].sum()
    if grouped.iloc[0] == 0:
        return {"direction": "insuffisant", "change_pct": None}
    change_pct = (grouped.iloc[-1] / grouped.iloc[0] - 1) * 100
    if change_pct > 15:
        direction = "up"
    elif change_pct < -15:
        direction = "down"
    else:
        direction = "flat"
    return {"direction": direction, "change_pct": round(float(change_pct), 1)}


def seller_runway(df: pd.DataFrame, spot_price: float) -> pd.DataFrame:
    """Distance en % entre le spot et le breakeven du vendeur."""
    df = df.copy()
    df["breakeven"] = df.apply(
        lambda r: r["strike"] + r["premium"] if r["type"] == "Call"
        else r["strike"] - r["premium"],
        axis=1,
    )
    df["runway_pts"] = (df["breakeven"] - spot_price).abs()
    df["runway_pct"] = (df["runway_pts"] / spot_price * 100).round(2)
    return df


def _classify_alert(score: int) -> str:
    labels = {3: "Setup fort", 2: "Setup modere", 1: "Signal faible", 0: "Neutre"}
    return labels.get(score, "Neutre")


def _classify_urgency(runway_pct):
    if runway_pct is None:
        return "N/A"
    if runway_pct < 2:
        return "haute"
    elif runway_pct < 5:
        return "moderee"
    return "faible"


def detect_squeeze_setup(df_options_today: pd.DataFrame, oi_history: pd.DataFrame,
                          spot_price: float, zero_gamma_level,
                          technical_levels: list = None, lookback_days: int = 5) -> dict:
    """Combine les 3 signaux en un score /3, qualifie l'urgence via le runway."""
    isolated = detect_isolated_oi(df_options_today, spot_price)
    near_spot = isolated[
        isolated["strike"].between(spot_price * 0.95, spot_price * 1.10)
        & isolated["risk_flag"]
    ] if not isolated.empty else isolated

    oi_concentration = not near_spot.empty
    below_zero_gamma = (
        zero_gamma_level is not None and spot_price < zero_gamma_level
    )

    oi_increasing = False
    oi_trend_status = "insuffisant"
    target_strikes = []

    if oi_concentration:
        target_strikes = near_spot["strike"].tolist()
        trend = compute_oi_trend(oi_history, target_strikes, lookback_days)
        oi_trend_status = trend["direction"]
        oi_increasing = trend["direction"] == "up"

    detection_score = sum([oi_concentration, below_zero_gamma, oi_increasing])

    urgency_pct = None
    if target_strikes and "premium" in df_options_today.columns:
        relevant = df_options_today[df_options_today["strike"].isin(target_strikes)]
        if not relevant.empty:
            relevant = seller_runway(relevant, spot_price)
            urgency_pct = round(float(relevant["runway_pct"].mean()), 2)

    near_technical = False
    if technical_levels:
        near_technical = any(
            abs(spot_price - lvl) / spot_price < 0.01 for lvl in technical_levels
        )

    return {
        "detection_score": detection_score,
        "alert_level": _classify_alert(detection_score),
        "urgency_pct": urgency_pct,
        "urgency_label": _classify_urgency(urgency_pct),
        "near_technical_level": near_technical,
        "oi_trend_status": oi_trend_status,
        "target_strikes": target_strikes,
        "signals_detail": {
            "oi_concentration": oi_concentration,
            "below_zero_gamma": below_zero_gamma,
            "oi_increasing": oi_increasing,
        },
    }
