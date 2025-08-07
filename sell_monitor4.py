import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from io import StringIO

# --- UI Setup ---
st.set_page_config(page_title="Sell Monitor", layout="wide")
st.title("📈 Live Sell Condition Monitor with CSV Upload")
st.caption("Upload your positions. Monitors every 60 seconds.")

# --- Auto-refresh every 60 seconds ---
st_autorefresh(interval=60 * 1000, key="refresh")

# --- Initialize Session State ---
if 'sell_log' not in st.session_state:
    st.session_state.sell_log = []

if 'max_return_tracker' not in st.session_state:
    st.session_state.max_return_tracker = {}

if 'max_price_tracker' not in st.session_state:
    st.session_state.max_price_tracker = {}

# --- Sidebar: Exit Criteria Controls ---
st.sidebar.header("Exit Strategy Criteria")
target_return = st.sidebar.slider("🎯 Target Return (%)", 1, 100, 20)
stop_loss = st.sidebar.slider("🛑 Stop Loss (%)", 1, 100, 10)
trailing_stop = st.sidebar.slider("📉 Trailing Stop (%)", 1, 100, 5)
max_hold_days = st.sidebar.slider("📆 Max Holding Period (days)", 1, 365, 180)

# --- Sidebar: Upload CSV ---
st.sidebar.header("📤 Upload Positions CSV")
uploaded_file = st.sidebar.file_uploader("Upload CSV", type=["csv"])

if uploaded_file:
    try:
        df_positions = pd.read_csv(uploaded_file)
        df_positions.columns = [col.strip() for col in df_positions.columns]

        try:
            df_positions['Buy Date'] = pd.to_datetime(df_positions['Buy Date'], format="%d-%b-%y")
        except:
            df_positions['Buy Date'] = pd.to_datetime(df_positions['Buy Date'])
    except Exception as e:
        st.error(f"❌ Error loading CSV: {e}")
        st.stop()
else:
    st.info("Using sample data. Upload your own CSV in the sidebar.")
    df_positions = pd.DataFrame({
        'Ticker': ['AAPL', 'MSFT', 'GOOGL'],
        'Buy Date': ['2024-12-01', '2025-01-15', '2025-02-20'],
        'Buy Price': [150.00, 280.00, 2700.00]
    })
    df_positions['Buy Date'] = pd.to_datetime(df_positions['Buy Date'])

# --- Price Fetcher ---
@st.cache_data(ttl=60)
def fetch_latest_data(ticker):
    try:
        df = yf.download(ticker, period="21d", interval="1d", progress=False, auto_adjust=True)
        if df.empty or 'Close' not in df.columns:
            return None

        current_price_raw = df['Close'].iloc[-1]
        ma20_raw = df['Close'].rolling(20).mean().iloc[-1]

        current_price = current_price_raw.item() if hasattr(current_price_raw, "item") else float(current_price_raw)
        ma20 = ma20_raw.item() if hasattr(ma20_raw, "item") else float(ma20_raw)
        return float(current_price), float(ma20)
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None

# --- Evaluation Logic ---
results = []
for _, row in df_positions.iterrows():
    ticker = row['Ticker']
    buy_price = row['Buy Price']
    buy_date = row['Buy Date']
    days_held = (datetime.now() - buy_date).days

    fetched = fetch_latest_data(ticker)
    if not fetched:
        continue

    current_price, ma20 = fetched
    if pd.isna(current_price) or pd.isna(ma20):
        continue

    return_pct = ((current_price - buy_price) / buy_price) * 100

    # --- Update Max Return Tracker ---
    if ticker not in st.session_state.max_return_tracker:
        st.session_state.max_return_tracker[ticker] = return_pct
    else:
        st.session_state.max_return_tracker[ticker] = max(
            return_pct, st.session_state.max_return_tracker[ticker]
        )

    # --- Update Max Price Tracker ---
    if ticker not in st.session_state.max_price_tracker:
        st.session_state.max_price_tracker[ticker] = current_price
    else:
        st.session_state.max_price_tracker[ticker] = max(
            current_price, st.session_state.max_price_tracker[ticker]
        )

    max_return_pct = st.session_state.max_return_tracker[ticker]
    max_price = st.session_state.max_price_tracker[ticker]

    trailing_high = max(current_price, buy_price)
    trailing_trigger = trailing_high * (1 - trailing_stop / 100)

    # --- Advice Logic with Float Guard ---
    advice = "Hold"
    if abs(return_pct) < 0.1:
        advice = "Hold"
    elif return_pct >= target_return:
        advice = "✅ Sell (Target Met)"
    elif return_pct <= -stop_loss:
        advice = "❌ Sell (Stop Loss)"
    elif current_price < trailing_trigger and return_pct > 0.1:
        advice = "⚠️ Sell (Trailing Stop)"
    elif current_price < ma20 and return_pct > 0.1:
        advice = "⚠️ Sell (Below 20MA)"
    elif days_held >= max_hold_days:
        advice = "⏰ Sell (Max Hold Period)"

    results.append({
        "Ticker": ticker,
        "Days Held": days_held,
        "Buy Price": round(buy_price, 2),
        "Current Price": round(current_price, 2),
        "Return (%)": round(return_pct, 2),
        "Max Return (%)": round(max_return_pct, 2),
        "Max Price ($)": round(max_price, 2),
        "20-Day MA": round(ma20, 2),
        "Advice": advice
    })

    if "Sell" in advice:
        st.session_state.sell_log.append({
            "Timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "Ticker": ticker,
            "Advice": advice,
            "Buy Price": round(buy_price, 2),
            "Current Price": round(current_price, 2),
            "Return (%)": round(return_pct, 2)
        })

# --- Display Results ---
st.markdown(f"### 🕒 Last Checked: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
st.markdown(f"Currently monitoring **{len(results)} positions**")

if results:
    df_results = pd.DataFrame(results)

    def color_code(val):
        if "Sell" in val:
            return "background-color: #ffdddd; color: #600000; font-weight: bold"
        return ""

    styled = df_results.style \
        .applymap(color_code, subset=["Advice"]) \
        .format({
            "Buy Price": "{:.2f}",
            "Current Price": "{:.2f}",
            "Return (%)": "{:.2f}",
            "Max Return (%)": "{:.2f}",
            "Max Price ($)": "{:.2f}",
            "20-Day MA": "{:.2f}"
        })
    st.dataframe(styled, use_container_width=True)
else:
    st.warning("No valid tickers found or data unavailable.")

# --- Sell Alerts Log ---
if st.session_state.sell_log:
    st.markdown("### 🧾 Sell Alerts Log (Historical)")
    df_log = pd.DataFrame(st.session_state.sell_log)
    st.dataframe(df_log, use_container_width=True)

    csv_buffer = StringIO()
    df_log.to_csv(csv_buffer, index=False)
    st.download_button(
        label="📥 Download Sell Alerts Log as CSV",
        data=csv_buffer.getvalue(),
        file_name="sell_alerts_log.csv",
        mime="text/csv"
    )
