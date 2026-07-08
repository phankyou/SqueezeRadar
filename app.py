"""
app.py - SqueezeRadar
Dashboard de detection de gamma squeeze sur NQ, ES, GC.
Signal quotidien, preparation pre-marche.
"""

import streamlit as st

from src.loader import load_yf_options
from src.gex import gamma_profile
from src.squeeze_detector import detect_squeeze_setup
from src.technical_levels import compute_technical_levels
from src.oi_history import load_oi_history, append_daily_snapshot

st.set_page_config(page_title="SqueezeRadar", page_icon="🎯", layout="wide")

ASSET_CONFIG = {
    "NQ": {"proxy_ticker": "QQQ", "label": "Nasdaq Futures (NQ)"},
    "ES": {"proxy_ticker": "SPY", "label": "S&P 500 Futures (ES)"},
    "GC": {"proxy_ticker": "GLD", "label": "Gold Futures (GC)"},
}

TREND_LABELS = {
    "up": "en hausse - le mur grossit",
    "down": "en baisse - les gens sortent",
    "flat": "stable",
    "insuffisant": "historique insuffisant",
}

URGENCY_LABELS = {
    "haute": "haute - tres peu de marge",
    "moderee": "moderee - encore un peu de marge",
    "faible": "marge confortable",
    "N/A": "non disponible",
}

def render_header():
    st.title("🎯 SqueezeRadar")
    st.caption("NQ · ES · GC — mis a jour quotidiennement")
    with st.expander("Comment lire ce dashboard"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Score**")
            st.caption("Combien de feux sont au vert sur 3.")
        with col2:
            st.markdown("**Tendance OI**")
            st.caption("Le mur grossit ou retrecit.")
        with col3:
            st.markdown("**Urgence**")
            st.caption("La marge qu'il reste aux vendeurs.")

@st.cache_data(ttl=3600, show_spinner=False)
def load_asset_data(proxy_ticker: str):
    return load_yf_options(proxy_ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def load_technical_levels_cached(proxy_ticker: str):
    return compute_technical_levels(proxy_ticker)

def render_asset(asset_key: str, config: dict):
    proxy = config["proxy_ticker"]
    try:
        spot, df_options = load_asset_data(proxy)
    except ValueError as e:
        st.error(f"{config['label']} : {e}")
        return

    _, _, zero_gamma = gamma_profile(df_options, spot)
    tech_levels = load_technical_levels_cached(proxy)
    oi_hist = load_oi_history(asset_key)
    result = detect_squeeze_setup(df_options, oi_hist, spot, zero_gamma, tech_levels)
    append_daily_snapshot(asset_key, df_options)
    return spot, zero_gamma, result

def display_asset_card(asset_key: str, config: dict, spot, zero_gamma, result):
    score = result["detection_score"]
    icon = "🔥" if score == 3 else "⚠️" if score == 2 else "⚪"
    st.subheader(f"{icon} {config['label']} — {result['alert_level']} ({score}/3)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Spot", f"{spot:.2f}")
    with col2:
        zg_display = f"{zero_gamma:.2f}" if zero_gamma else "N/A"
        st.metric("Zero Gamma", zg_display)
    with col3:
        st.metric("Urgence", URGENCY_LABELS.get(result["urgency_label"], "N/A"))

    st.caption(f"Tendance OI : {TREND_LABELS.get(result['oi_trend_status'], 'N/A')}")
    st.divider()

render_header()

for asset_key, config in ASSET_CONFIG.items():
    data = render_asset(asset_key, config)
    if data:
        spot, zero_gamma, result = data
        display_asset_card(asset_key, config, spot, zero_gamma, result)
