import streamlit as st
import yfinance as yf
import pandas as pd
import time

# =========================
# Page config
# =========================
st.set_page_config(
    page_title="Options Activity Tracker",
    layout="wide"
)

st.title("📊 Options Activity Tracker")

# =========================
# Sidebar: Watchlist
# =========================
st.sidebar.header("Watchlist")

watchlist_input = st.sidebar.text_area(
    "Tickers (comma-separated)",
    value="XLF, SPXL, TQQQ, B, BRK.B"
)

watchlist = [s.strip().upper() for s in watchlist_input.split(",") if s.strip()]

# =========================
# Sidebar: Activity thresholds
# =========================
st.sidebar.header("Activity Interpretation")

UNUSUAL_MIN = st.sidebar.number_input(
    "Unusual threshold (Vol / OI ≥)",
    min_value=0.1,
    value=1.0,
    step=0.1,
    help="Volume divided by Open Interest"
)

HIGH_MIN = st.sidebar.number_input(
    "High activity threshold",
    min_value=UNUSUAL_MIN,
    value=max(UNUSUAL_MIN * 1.5, UNUSUAL_MIN + 0.5),
    step=0.1
)

EXTREME_MIN = st.sidebar.number_input(
    "Extreme activity threshold",
    min_value=HIGH_MIN,
    value=max(HIGH_MIN * 2, HIGH_MIN + 1),
    step=0.5,
    help="No upper bound — anything above this is extreme"
)

MIN_VOLUME = st.sidebar.number_input(
    "Minimum option volume",
    min_value=1,
    value=100,
    step=10
)

# =========================
# Sidebar: Refresh
# =========================
st.sidebar.header("Refresh")
AUTO_REFRESH = st.sidebar.checkbox("Auto-refresh (60s)", value=True)

# =========================
# Data helpers
# =========================
@st.cache_data(ttl=60)
def get_expirations(ticker):
    return yf.Ticker(ticker).options


@st.cache_data(ttl=60)
def load_chain(ticker, expiration):
    chain = yf.Ticker(ticker).option_chain(expiration)
    return chain.calls, chain.puts


def classify_activity(ratio):
    if pd.isna(ratio):
        return "Unknown"
    if ratio >= EXTREME_MIN:
        return "Extreme"
    if ratio >= HIGH_MIN:
        return "High"
    if ratio >= UNUSUAL_MIN:
        return "Unusual"
    return "Normal"


def style_activity(col):
    colors = {
        "Extreme": "background-color:#00ffff; color:black; font-weight:600",  # cyan
        "High": "background-color:#8a2be2; color:white; font-weight:600",    # violet
        "Unusual": "background-color:#ffd700; color:black; font-weight:600", # yellow
    }
    return [colors.get(v, "") for v in col]


def find_unusual(df, option_type, symbol, expiration):
    df = df.copy()

    # Ensure clean numeric types
    df["volume"] = df["volume"].fillna(0).astype(int)
    df["openInterest"] = df["openInterest"].replace(0, pd.NA)
    df["unusual_score"] = df["volume"] / df["openInterest"]

    df["activity_level"] = df["unusual_score"].apply(classify_activity)

    filtered = df[
        (df["volume"] >= MIN_VOLUME) &
        (df["activity_level"] != "Normal")
    ]

    if filtered.empty:
        return filtered

    filtered["symbol"] = symbol
    filtered["expiration"] = expiration
    filtered["type"] = option_type
    filtered["strike"] = filtered["strike"].map(lambda x: f"${x:,.2f}")

    return filtered[
        [
            "symbol",
            "type",
            "expiration",
            "strike",
            "volume",
            "openInterest",
            "unusual_score",
            "activity_level",
            "impliedVolatility",
        ]
    ]


# =========================
# Main processing
# =========================
results = []

for symbol in watchlist:
    try:
        expirations = get_expirations(symbol)
        if not expirations:
            continue

        expiration = expirations[0]
        calls, puts = load_chain(symbol, expiration)

        results.append(find_unusual(calls, "CALL", symbol, expiration))
        results.append(find_unusual(puts, "PUT", symbol, expiration))

    except Exception:
        st.warning(f"{symbol}: failed to load options data")

# =========================
# Display
# =========================
st.subheader("🚨 Unusual & Extreme Options Activity")

st.caption(
    "🛈 **Vol / OI** = Option Volume ÷ Open Interest. "
    "Values > 1 indicate trading activity exceeding existing positions. "
    "There is no upper cap — extreme values rise naturally."
)

valid = [df for df in results if not df.empty]

if not valid:
    st.info("No unusual activity detected with current settings.")
else:
    df = pd.concat(valid).reset_index(drop=True)
    df = df.sort_values("unusual_score", ascending=False)

    styled = (
        df.style
        .format({
            "unusual_score": "{:.2f}",
            "impliedVolatility": "{:.2%}",
            "volume": "{:d}",
            "openInterest": "{:d}",
        })
        .apply(style_activity, subset=["activity_level"])
    )

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True
    )

# =========================
# Auto-refresh
# =========================
if AUTO_REFRESH:
    time.sleep(60)
    st.rerun()
