import streamlit as st
import yfinance as yf
import pandas as pd
import time
import smtplib
from email.message import EmailMessage

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

# =========================
# Help / Definitions
# =========================
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
# Sidebar
# =========================
st.sidebar.markdown("### 📌 Watchlist")

watchlist_input = st.sidebar.text_area(
    "Tickers (comma-separated)",
    value="XLF, SPXL, TQQQ, B, BRK-B"
)

watchlist = [s.strip().upper() for s in watchlist_input.split(",") if s.strip()]


# =========================
# Expiration selection (per ticker)
# =========================
st.sidebar.markdown("### 🗓️ Expiration Selection")

@st.cache_data(ttl=300)
def safe_get_expirations(ticker):
    try:
        exps = yf.Ticker(ticker).options
        return list(exps) if exps else []
    except Exception:
        return []

expiration_map = {}

for symbol in watchlist:
    expirations = safe_get_expirations(symbol)

    if not expirations:
        expiration_map[symbol] = None
        continue

    # Default to nearest expiration (Yahoo behavior)
    expiration_map[symbol] = st.sidebar.selectbox(
        f"{symbol} expiration",
        options=expirations,
        index=0,
        key=f"exp_{symbol}"
    )

st.sidebar.markdown("### ⚙️ Activity Interpretation")

UNUSUAL_MIN = st.sidebar.number_input("Unusual (Vol / OI ≥)", 0.1, value=1.0, step=0.1)
HIGH_MIN = st.sidebar.number_input("High activity ≥", UNUSUAL_MIN, value=1.5, step=0.1)
EXTREME_MIN = st.sidebar.number_input("Extreme activity ≥", HIGH_MIN, value=3.0, step=0.5)
MIN_VOLUME = st.sidebar.number_input("Minimum contract volume", 1, value=100, step=10)

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

        expiration = expiration_map.get(symbol)
        if not expiration:
            continue

        calls, puts = load_chain(symbol, expiration)

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

# =========================
# Tables
# =========================
if imbalance_rows:
    st.markdown("#### ⚖️ Call vs Put Volume Imbalance")
    imbalance_df = pd.DataFrame(imbalance_rows)
    st.dataframe(imbalance_df, use_container_width=True, hide_index=True)

st.markdown("---")

valid = [df for df in contract_results if not df.empty]

st.markdown("#### 🚨 Contract-Level Unusual Options Activity")

if valid:
    df = pd.concat(valid).sort_values("Vol / OI", ascending=False)

    # Ensure numeric columns are clean
    numeric_cols = [
        "% From Spot",
        "Relative Volume",
        "Vol / OI",
        "Implied Volatility",
        "Volume",
        "Open Interest",
        "Spot",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Activity visual encoding (NO Styler)
    activity_display = {
        "Extreme": "🟨 Extreme",
        "High": "🟪 High",
        "Unusual": "🟦 Unusual",
    }

    df["Activity"] = df["Activity"].map(activity_display).fillna("Normal")

    # Formatting for display
    df["% From Spot"] = df["% From Spot"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
    df["Relative Volume"] = df["Relative Volume"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
    df["Vol / OI"] = df["Vol / OI"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
    df["Implied Volatility"] = df["Implied Volatility"].map(lambda x: f"{x:.2%}" if pd.notna(x) else "—")
    df["Spot"] = df["Spot"].map(lambda x: f"${x:,.2f}" if pd.notna(x) else "—")

    st.dataframe(df, use_container_width=True, hide_index=True)

else:
    st.info("No unusual activity detected.")


# =========================
# Feedback (EMAIL)
# =========================
import smtplib
from email.message import EmailMessage

st.markdown("---")
st.markdown("### 💬 Feedback & Bug Reports 🐞")

with st.expander("Let the dev know how to make this better!", expanded=False):
    st.markdown(
        "Prefer GitHub? "
        "[Open an issue here](https://github.com/saberbrasher/options-dashboard/issues)"
    )

    # ---- Live UI (outside form) ----
    allow_followup = st.checkbox("I'm okay being contacted")

    contact_info = ""
    if allow_followup:
        contact_info = st.text_input(
            "Email address (optional)",
            placeholder="you@email.com"
        )

    # ---- Form (submission only) ----
    with st.form("feedback_form"):
        feedback_type = st.selectbox(
            "Feedback type",
            ["Bug / Error", "Data looks wrong", "Feature request", "General feedback"]
        )

        feedback_text = st.text_area(
            "Your message",
            placeholder="What were you doing? What did you expect?",
            height=120
        )

        submitted = st.form_submit_button("Send feedback")

    if submitted:
        if not feedback_text.strip():
            st.warning("Please enter feedback before submitting.")
        else:
            try:
                msg = EmailMessage()
                msg["Subject"] = f"🐞 Options Dashboard Feedback — {feedback_type}"
                msg["From"] = st.secrets["EMAIL_USER"]
                msg["To"] = st.secrets["EMAIL_TO"]

                body = f"""
Feedback type:
{feedback_type}

Message:
{feedback_text}
"""

                if allow_followup and contact_info:
                    body += f"\nContact:\n{contact_info}"
                else:
                    body += "\nContact:\nAnonymous"

                msg.set_content(body)

                with smtplib.SMTP(
                    st.secrets["EMAIL_HOST"],
                    st.secrets["EMAIL_PORT"]
                ) as server:
                    server.starttls()
                    server.login(
                        st.secrets["EMAIL_USER"],
                        st.secrets["EMAIL_PASSWORD"]
                    )
                    server.send_message(msg)

                st.success("Thanks! Your feedback was sent 💌")

            except Exception as e:
                st.error("Failed to send feedback email.")
                st.exception(e)

# =========================
# Auto-refresh
# =========================
if AUTO_REFRESH:
    time.sleep(60)
    st.rerun()
