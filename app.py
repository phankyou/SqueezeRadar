"""
app.py - SqueezeRadar (version coloree)
Dashboard de detection de gamma squeeze sur NQ, ES, GC.
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

SCORE_COLORS = {3: "#ff4b4b", 2: "#ffa500", 1: "#4b9fff", 0: "#6c6c6c"}
SCORE_BG = {
    3: "rgba(255,75,75,0.12)",
    2: "rgba(255,165,0,0.12)",
    1: "rgba(75,159,255,0.10)",
    0: "rgba(108,108,108,0.10)",
}
SCORE_ICON = {3: "🔥", 2: "⚠️", 1: "🔵", 0: "⚪"}

st.markdown("""
<style>
.stApp { background-color: #0d1117; }
.metric-box {
    background: rgba(255,255,255,0.03);
    border-radius: 10px;
    padding: 12px 16px;
    text-align: center;
}
.metric-label {
    font-size: 12px;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}
.metric-value {
    font-size: 26px;
    font-weight: 700;
    color: #ffffff;
}
</style>
""", unsafe_allow_html=True)


def render_header():
    st.title("🎯 SqueezeRadar")
    st.caption("NQ · ES · GC — mis a jour quotidiennement")
    with st.expander("Comment lire ce dashboard"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🔥 Score**")
            st.caption("Combien de feux sont au vert sur 3. Rouge = fort, orange = modere, bleu = faible, gris = neutre.")
        with col2:
            st.markdown("**📈 Tendance OI**")
            st.caption("Le mur grossit ou retrecit.")
        with col3:
            st.markdown("**⏱️ Urgence**")
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
    color = SCORE_COLORS.get(score, "#6c6c6c")
    bg = SCORE_BG.get(score, "rgba(108,108,108,0.10)")
    icon = SCORE_ICON.get(score, "⚪")

    zg_display = f"{zero_gamma:.2f}" if zero_gamma else "N/A"
    urgency_text = URGENCY_LABELS.get(result["urgency_label"], "N/A")
    trend_text = TREND_LABELS.get(result["oi_trend_status"], "N/A")

    st.markdown(f"""
    <div style="border-left: 5px solid {color}; background: {bg};
                border-radius: 12px; padding: 20px 24px; margin-bottom: 20px;">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
            <span style="font-size:20px; font-weight:700; color:#ffffff;">
                {icon} {config['label']}
            </span>
            <span style="background:{color}; color:#0d1117; font-weight:700;
                         padding:4px 14px; border-radius:20px; font-size:13px;">
                {result['alert_level']} ({score}/3)
            </span>
        </div>
        <div style="display:flex; gap:16px; margin-bottom:12px;">
            <div class="metric-box" style="flex:1;">
                <div class="metric-label">Spot</div>
                <div class="metric-value">{spot:.2f}</div>
            </div>
            <div class="metric-box" style="flex:1;">
                <div class="metric-label">Zero Gamma</div>
                <div class="metric-value">{zg_display}</div>
            </div>
            <div class="metric-box" style="flex:1;">
                <div class="metric-label">Urgence</div>
                <div class="metric-value" style="font-size:16px;">{urgency_text}</div>
            </div>
        </div>
        <div style="color:#9ca3af; font-size:13px;">
            Tendance OI : {trend_text}
        </div>
    </div>
    """, unsafe_allow_html=True)


render_header()

for asset_key, config in ASSET_CONFIG.items():
    data = render_asset(asset_key, config)
    if data:
        spot, zero_gamma, result = data
        display_asset_card(asset_key, config, spot, zero_gamma, result)

st.markdown("<br>", unsafe_allow_html=True)
st.divider()

# =============================================
# OBI + VPIN CONFLUENCE (SqueezeRadar)
# =============================================
st.subheader("🌊 Confluence OBI + VPIN — Flux informé")
st.caption("Déséquilibre directionnel 1h · Probabilité flux institutionnel · NQ · ES · GC")

import numpy as _np_sr
import scipy.stats as _scipy_sr

_SR_TICKERS  = {"NQ": "NQ=F", "ES": "ES=F", "GC": "GC=F"}
_SR_OBI_WIN  = 5
_SR_OBI_THR  = 0.05
_SR_VPIN_WIN = 20
_SR_VPIN_THR = 0.60

@st.cache_data(ttl=900, show_spinner=False)
def _load_sr_flow(ticker):
    try:
        import yfinance as _yf
        from datetime import datetime as _dt, timedelta as _td
        start = (_dt.today() - _td(days=720)).strftime("%Y-%m-%d")
        df = _yf.download(ticker, start=start, interval="1h",
                          progress=False, auto_adjust=True)
        if df.empty or len(df) < 30:
            return None
        if isinstance(df.columns, __import__('pandas').MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[['Open','High','Low','Close','Volume']].dropna()
        hl   = (df['High'] - df['Low']).replace(0, _np_sr.nan)
        bp   = ((df['Close'] - df['Open']) / hl).fillna(0)
        obi  = float(bp.rolling(_SR_OBI_WIN, min_periods=2).mean().iloc[-1])
        v_buy  = df['Volume'] * (df['Close'] > df['Open']).astype(float)
        v_sell = df['Volume'] * (df['Close'] < df['Open']).astype(float)
        vtot   = df['Volume'].replace(0, _np_sr.nan)
        vpin   = float(((v_buy - v_sell).abs() / vtot)
                       .rolling(_SR_VPIN_WIN, min_periods=5).mean().iloc[-1])
        return {"obi": obi, "vpin": vpin}
    except Exception:
        return None

_sr_cols = st.columns(3)
_sr_instruments = list(_SR_TICKERS.items())

with st.spinner("Chargement flux OBI+VPIN…"):
    for _ci, (instr, ticker) in enumerate(_sr_instruments):
        r = _load_sr_flow(ticker)
        with _sr_cols[_ci]:
            if r is None:
                st.warning(f"{instr} — données indisponibles")
                continue
            obi_v  = r["obi"]
            vpin_v = r["vpin"]
            bull = obi_v >  _SR_OBI_THR and vpin_v >= _SR_VPIN_THR
            bear = obi_v < -_SR_OBI_THR and vpin_v >= _SR_VPIN_THR
            if bull:
                sig, color, emoji = "HAUSSIER", "#3FB950", "🟢"
            elif bear:
                sig, color, emoji = "BAISSIER", "#F85149", "🔴"
            else:
                sig, color, emoji = "NEUTRE", "#8B949E", "⚪"
            obi_str  = f"+{obi_v:.3f}" if obi_v >= 0 else f"{obi_v:.3f}"
            vpin_str = f"{vpin_v:.2f}"
            st.markdown(f"""
<div style="background:#161B22;border:1px solid {color};border-radius:10px;padding:16px;text-align:center">
  <div style="font-size:1.4rem;font-weight:700;color:{color}">{emoji} {instr}</div>
  <div style="font-size:1.05rem;color:{color};margin:6px 0">{sig}</div>
  <div style="color:#8B949E;font-size:0.85rem;margin-top:8px">
    OBI&nbsp;<span style="color:#E6EDF3;font-weight:600">{obi_str}</span>
    &nbsp;|&nbsp;
    VPIN&nbsp;<span style="color:#BC8CFF;font-weight:600">{vpin_str}</span>
  </div>
</div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

with st.expander("📖 Comment lire OBI + VPIN", expanded=False):
    st.markdown("""
**OBI — Order Book Imbalance (5 barres 1h)**  
`OBI = moyenne( (Close − Open) / (High − Low) )`  
• `> +0.05` → pression acheteuse dominante 🟢  
• `< −0.05` → pression vendeuse dominante 🔴  

**VPIN proxy — Flux informé (20 barres 1h)**  
`VPIN = moyenne( |V_buy − V_sell| / V_total )`  
• `≥ 0.60` → flux institutionnel actif  
• `< 0.60` → flux retail / bruit  

**Signal** = OBI directionnel **ET** VPIN ≥ 0.60 → confluence flux + direction
""")
