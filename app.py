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
st.caption(f"Last updated: {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
st.caption("Not investment advice. Data delayed and sourced from public options chains.")


with st.expander("ℹ️ How to read this dashboard", expanded=False):
    st.markdown("""
### Key Metrics

**Vol / OI (Volume ÷ Open Interest)**  
**Formula:**  
`Vol / OI = Contract Volume ÷ Open Interest`  

**What it means:**  
Measures how much *new trading* is occurring relative to existing positions.  
- **> 1.0** → Today’s activity exceeds the number of open contracts  
- Suggests new positioning; common first-pass filter for unusual activity

---

**Relative Volume**  
**Formula:**  
`Relative Volume = Contract Volume ÷ Median Volume of Option Chain`  

**What it means:**  
Normalizes volume across the option chain so strikes and expirations can be compared fairly.  
- **1.0×** → Typical activity  
- **> 1.0×** → Elevated interest relative to peers  
- Highlights contracts standing out within the same expiration

---

**% From Spot**  
**Formula:**  
`% From Spot = |Strike − Spot Price| ÷ Spot Price × 100`  

**What it means:**  
Shows how far a strike is from the current stock price.  
- Smaller values = **near-the-money (ATM)**  
- Institutions often concentrate activity **close to spot**  
- Large distances may reflect hedging or speculative positioning

---

**Moneyness**  
**Definition:**  
Describes whether an option would have intrinsic value if exercised now.

- **ITM (In the Money)**  
  - Calls: Strike < Spot  
  - Puts: Strike > Spot  

- **ATM (At the Money)**  
  - Strike ≈ Spot  

- **OTM (Out of the Money)**  
  - Calls: Strike > Spot  
  - Puts: Strike < Spot  

Moneyness helps contextualize intent (directional vs hedging).

---

**Call / Put Volume Ratio**  
**Formula:**  
`Call / Put Ratio = Total Call Volume ÷ Total Put Volume`  

**What it means:**  
High-level view of directional skew in options trading for a given expiration.  
- **> 1.3** → Call-heavy flow  
- **< 0.7** → Put-heavy flow  
- Best used as **context**, not a standalone signal

---

**Interpreting Flow**
                
Options flow reflects positioning, not intent. 
- Call-heavy ≠ bullish by default  
- Put-heavy ≠ bearish by default    
""")

# =========================
# Sidebar: Watchlist
# =========================
st.sidebar.markdown("### 📌 Watchlist")

watchlist_input = st.sidebar.text_area(
    "Tickers (comma-separated)",
    value="XLF, SPXL, TQQQ, B, BRK-B"
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
    step=0.1
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
    step=0.5
)

MIN_VOLUME = st.sidebar.number_input(
    "Minimum contract volume",
    min_value=1,
    value=100,
    step=10
)

AUTO_REFRESH = st.sidebar.checkbox("Auto-refresh every 60s", value=False)

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


@st.cache_data(ttl=60)
def get_spot_price(ticker):
    hist = yf.Ticker(ticker).history(period="1d")
    return hist["Close"].iloc[-1] if not hist.empty else None


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
    df["relative_volume"] = (
        df["volume"] / median_vol if median_vol and median_vol > 0 else pd.NA
    )
    return df


def style_activity(col):
    styles = {
        "Extreme": "background-color:#00ffff; color:black; font-weight:600",
        "High": "background-color:#8a2be2; color:white; font-weight:600",
        "Unusual": "background-color:#ffd700; color:black; font-weight:600",
    }
    return [styles.get(v, "") for v in col]


def find_unusual(df, option_type, symbol, expiration, spot):
    df = df.copy()

    df["volume"] = df["volume"].fillna(0).astype(int)
    df["openInterest"] = df["openInterest"].replace(0, pd.NA)

    df["Vol / OI"] = df["volume"] / df["openInterest"]
    df["Activity"] = df["Vol / OI"].apply(classify_activity)

    df = add_relative_volume(df)

    df["Spot"] = spot
    df["% From Spot"] = ((df["strike"] - spot) / spot).abs() * 100

    df["Moneyness"] = "ATM"
    if option_type == "CALL":
        df.loc[df["strike"] > spot, "Moneyness"] = "OTM"
        df.loc[df["strike"] < spot, "Moneyness"] = "ITM"
    else:
        df.loc[df["strike"] < spot, "Moneyness"] = "OTM"
        df.loc[df["strike"] > spot, "Moneyness"] = "ITM"

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
            "Spot",
            "% From Spot",
            "Moneyness",
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
contract_results = []
imbalance_rows = []

for symbol in watchlist:
    try:
        spot = get_spot_price(symbol)
        if spot is None:
            continue

        expirations = get_expirations(symbol)
        if not expirations:
            continue

        expiration = expirations[0]
        calls, puts = load_chain(symbol, expiration)

        # ---- Call vs Put Imbalance ----
        call_vol = calls["volume"].fillna(0).sum()
        put_vol = puts["volume"].fillna(0).sum()

        ratio = call_vol / put_vol if put_vol > 0 else None

        bias = "Neutral"
        if ratio is not None:
            if ratio > 1.3:
                bias = "Call-heavy"
            elif ratio < 0.7:
                bias = "Put-heavy"

        imbalance_rows.append({
            "Ticker": symbol,
            "Expiration": expiration,
            "Call Volume": int(call_vol),
            "Put Volume": int(put_vol),
            "Call / Put Ratio": ratio,
            "Flow Bias": bias
        })

        contract_results.append(find_unusual(calls, "CALL", symbol, expiration, spot))
        contract_results.append(find_unusual(puts, "PUT", symbol, expiration, spot))

    except Exception:
        st.warning(f"{symbol}: failed to load options data")


# ---- Call / Put Imbalance Table ----
if imbalance_rows:
    st.markdown("#### ⚖️ Call vs Put Volume Imbalance")
    st.caption("Directional skew — not standalone intent")

    imbalance_df = pd.DataFrame(imbalance_rows).sort_values(
        "Call / Put Ratio", ascending=False
    )

    st.dataframe(
        imbalance_df.style.format({
            "Call / Put Ratio": "{:.2f}",
            "Call Volume": "{:d}",
            "Put Volume": "{:d}",
        }),
        use_container_width=True,
        hide_index=True
    )

st.markdown("---")

# ---- Contract-Level Activity ----
valid = [df for df in contract_results if not df.empty]

st.markdown("#### 🚨 Contract-Level Unusual Options Activity")
st.caption("Sorted by Vol / OI — highest conviction signals first")

if not valid:
    st.info("No unusual activity detected with current settings.")
else:
    df = pd.concat(valid).reset_index(drop=True)
    df = df.sort_values("Vol / OI", ascending=False)

    styled = (
        df.style
        .format({
            "% From Spot": "{:.1f}%",
            "Relative Volume": "{:.1f}×",
            "Implied Volatility": "{:.2%}",
            "Volume": "{:d}",
            "Open Interest": "{:d}",
            "Spot": "${:,.2f}",
        })
        .apply(style_activity, subset=["Activity"])
    )

    st.dataframe(styled, use_container_width=True, hide_index=True)

# =========================
# Auto-refresh
# =========================
if AUTO_REFRESH:
    time.sleep(60)
    st.rerun()
