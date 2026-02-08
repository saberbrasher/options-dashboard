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

st.markdown("## 📊 Options Activity Tracker")

with st.expander("ℹ️ How to read this table", expanded=False):
    st.markdown("""
**Vol / OI (Volume ÷ Open Interest)**  
Measures how aggressively contracts are trading relative to existing positions.

**Relative Volume**  
Compares a contract’s volume to the *median volume* of the entire option chain.  
Values above **1.0×** indicate elevated interest.

**Activity Levels**
- **Unusual** → Elevated but common
- **High** → Often institutional
- **Extreme** → Rare, aggressive positioning (no upper cap)

Large funds often build positions over time — repeated or clustered appearances matter.
""")

# =========================
# Sidebar: Watchlist
# =========================
st.sidebar.markdown("### 📌 Watchlist")

watchlist_input = st.sidebar.text_area(
    "Tickers (comma-separated)",
    value="XLF, SPXL, TQQQ, B, BRK.B"
)

watchlist = [s.strip().upper() for s in watchlist_input.split(",") if s.strip()]

# =========================
# Sidebar: Activity thresholds
# =========================
st.sidebar.markdown("### ⚙️ Activity Interpretation")

UNUSUAL_MIN = st.sidebar.number_input(
    "Unusual (Vol / OI ≥)",
    min_value=0.1,
    value=1.0,
    step=0.1,
    help="Volume divided by Open Interest"
)

HIGH_MIN = st.sidebar.number_input(
    "High activity ≥",
    min_value=UNUSUAL_MIN,
    value=max(UNUSUAL_MIN * 1.5, UNUSUAL_MIN + 0.5),
    step=0.1
)

EXTREME_MIN = st.sidebar.number_input(
    "Extreme activity ≥",
    min_value=HIGH_MIN,
    value=max(HIGH_MIN * 2, HIGH_MIN + 1),
    step=0.5,
    help="No upper bound — extreme activity scales naturally"
)

MIN_VOLUME = st.sidebar.number_input(
    "Minimum contract volume",
    min_value=1,
    value=100,
    step=10
)

# =========================
# Sidebar: Refresh
# =========================
AUTO_REFRESH = st.sidebar.checkbox("Auto-refresh every 60s", value=True)

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


def add_relative_volume(df):
    median_vol = df["volume"].median()
    if pd.isna(median_vol) or median_vol == 0:
        df["relative_volume"] = pd.NA
    else:
        df["relative_volume"] = df["volume"] / median_vol
    return df


def style_activity(col):
    styles = {
        "Extreme": "background-color:#00ffff; color:black; font-weight:600",
        "High": "background-color:#8a2be2; color:white; font-weight:600",
        "Unusual": "background-color:#ffd700; color:black; font-weight:600",
    }
    return [styles.get(v, "") for v in col]


def find_unusual(df, option_type, symbol, expiration):
    df = df.copy()

    df["volume"] = df["volume"].fillna(0).astype(int)
    df["openInterest"] = df["openInterest"].replace(0, pd.NA)

    df["Vol / OI"] = df["volume"] / df["openInterest"]
    df["Activity"] = df["Vol / OI"].apply(classify_activity)

    df = add_relative_volume(df)

    filtered = df[
        (df["volume"] >= MIN_VOLUME) &
        (df["Activity"] != "Normal")
    ]

    if filtered.empty:
        return filtered

    filtered["Ticker"] = symbol
    filtered["Expiration"] = expiration
    filtered["Type"] = option_type
    filtered["Strike"] = filtered["strike"].map(lambda x: f"${x:,.2f}")

    return filtered[
        [
            "Ticker",
            "Type",
            "Expiration",
            "Strike",
            "volume",
            "relative_volume",
            "openInterest",
            "Vol / OI",
            "Activity",
            "impliedVolatility",
        ]
    ].rename(columns={
        "volume": "Volume",
        "relative_volume": "Relative Volume",
        "openInterest": "Open Interest",
        "impliedVolatility": "Implied Volatility",
    })


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


valid = [df for df in results if not df.empty]

if not valid:
    st.info("No unusual activity detected with current settings.")
else:
    df = pd.concat(valid).reset_index(drop=True)
    df = df.sort_values("Vol / OI", ascending=False)

    styled = (
        df.style
        .format({
            "Vol / OI": "{:.2f}",
            "Relative Volume": "{:.1f}×",
            "Implied Volatility": "{:.2%}",
            "Volume": "{:d}",
            "Open Interest": "{:d}",
        })
        .apply(style_activity, subset=["Activity"])
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
