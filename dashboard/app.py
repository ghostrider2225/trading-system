"""Streamlit dashboard: Live Portfolio, Today's Picks, Stock Detail, Score History, Alerts."""
import os
import sqlite3
import sys
from datetime import datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st
import yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DB_PATH = os.path.join(ROOT, "database", "trading.db")

st.set_page_config(page_title="Trading System", page_icon="📈", layout="wide")

VERDICT_COLORS = {"STRONG": "#16a34a", "MODERATE": "#ca8a04", "WEAK": "#ea580c",
                  "AVOID": "#dc2626", "SCREENED-OUT": "#9ca3af"}
CUR = {"india": "₹", "us": "$"}
MARKET_LABEL = {"india": "🇮🇳 India (Nifty 50)", "us": "🇺🇸 US (S&P 500)"}


@st.cache_data(ttl=300)
def load(query, params=()):
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


@st.cache_resource
def live_price_store():
    """Shared dict of streamed prices; survives Streamlit reruns."""
    return {}


@st.cache_resource
def return_buffer():
    """Rolling buffer of live return points for the moving chart (~15 min at 1s)."""
    from collections import deque
    return deque(maxlen=900)


@st.cache_resource
def start_stream(tickers):
    """Background thread streaming real-time prices from Yahoo's websocket."""
    import threading

    store = live_price_store()

    def on_message(msg):
        try:
            tid, price = msg.get("id"), msg.get("price")
            if tid and price:
                store[tid] = float(price)
        except Exception:
            pass

    def run():
        while True:
            try:
                ws = yf.WebSocket()
                ws.subscribe(list(tickers))
                ws.listen(on_message)
            except Exception as e:
                print(f"[stream] reconnecting after: {e}")
                import time
                time.sleep(10)

    t = threading.Thread(target=run, daemon=True, name="yahoo-stream")
    t.start()
    return t


@st.cache_data(ttl=55)
def live_quotes(tickers):
    """Latest price + previous close per ticker, straight from Yahoo Finance."""
    if not tickers:
        return {}
    raw = yf.download(tickers, period="5d", interval="1d", group_by="ticker",
                      threads=True, progress=False, auto_adjust=True)
    out = {}
    for t in tickers:
        try:
            close = (raw[t] if len(tickers) > 1 else raw)["Close"].dropna()
            if len(close):
                out[t] = {"price": float(close.iloc[-1]),
                          "prev_close": float(close.iloc[-2]) if len(close) > 1
                          else float(close.iloc[-1])}
        except KeyError:
            continue
    return out


def pnl_color(v):
    if isinstance(v, (int, float)) and pd.notna(v):
        return "color: #16a34a" if v > 0 else ("color: #dc2626" if v < 0 else "")
    return ""


def color_verdict(v):
    return f"color: {VERDICT_COLORS.get(v, '#111')}; font-weight: 600"


st.sidebar.title("📈 Trading System")
page = st.sidebar.radio("Page", ["Live Portfolio", "Today's Picks", "Stock Detail",
                                 "Score History", "Alerts Log"])
st.sidebar.caption(
    "Paper trading — virtual money, live Yahoo Finance prices, no broker involved. "
    "Scores measure how strongly the data agrees; not guaranteed probabilities, "
    "not financial advice."
)

dates = load("SELECT DISTINCT run_date FROM scores ORDER BY run_date DESC")
if dates.empty:
    st.warning("No data yet. Run the collector first:  `python run_daily.py`")
    st.stop()
latest = dates["run_date"].iloc[0]


# ───────────────────────────── LIVE PORTFOLIO ─────────────────────────────
@st.fragment(run_every="1s")
def live_portfolio():
    pos = load("SELECT * FROM positions ORDER BY market, ticker")
    cash_df = load("SELECT market, cash FROM portfolio_cash")
    if cash_df.empty:
        st.info("No portfolio yet — it is created on the next collector run.")
        return

    tickers = tuple(sorted(pos["ticker"])) if len(pos) else ()
    quotes = live_quotes(tickers) if tickers else {}
    streamed = live_price_store()
    if tickers:
        start_stream(tickers)
        # streamed ticks (real-time) override the 60s snapshot fallback
        for t in tickers:
            if t in streamed:
                quotes.setdefault(t, {})["price"] = streamed[t]
    st.caption(f"🔴 Live — P&L updates every second ({len(streamed)} tickers streaming"
               f" from Yahoo; markets currently closed just hold their last price) · "
               f"{datetime.now().strftime('%H:%M:%S')} (server time)")

    buy_reasons = load(
        "SELECT ticker, MAX(executed_at) AS at, reason FROM trades "
        "WHERE side = 'BUY' GROUP BY ticker")
    buy_map = dict(zip(buy_reasons["ticker"], buy_reasons["reason"])) if len(buy_reasons) else {}
    realized = load(
        "SELECT market, SUM(CASE WHEN side = 'SELL' THEN value ELSE -value END) AS pnl "
        "FROM trades WHERE ticker NOT IN (SELECT ticker FROM positions) GROUP BY market")
    realized_map = dict(zip(realized["market"], realized["pnl"])) if len(realized) else {}

    live_returns = {}
    for market in ["india", "us"]:
        cash_row = cash_df[cash_df["market"] == market]
        if cash_row.empty:
            continue
        cur, cash = CUR[market], float(cash_row["cash"].iloc[0])
        mpos = pos[pos["market"] == market].copy()

        # live valuation
        mpos["live"] = mpos.apply(
            lambda r: quotes.get(r["ticker"], {}).get("price", r["last_price"]), axis=1)
        mpos["prev"] = mpos.apply(
            lambda r: quotes.get(r["ticker"], {}).get("prev_close", r["last_price"]), axis=1)
        invested = float((mpos["qty"] * mpos["avg_price"]).sum()) if len(mpos) else 0.0
        value_now = float((mpos["qty"] * mpos["live"]).sum()) if len(mpos) else 0.0
        unrealized = value_now - invested
        day_change = float((mpos["qty"] * (mpos["live"] - mpos["prev"])).sum()) if len(mpos) else 0.0
        realized_pnl = float(realized_map.get(market, 0.0))
        total = cash + value_now

        hist = load("SELECT snap_date, total FROM portfolio_history WHERE market = ? "
                    "ORDER BY snap_date", (market,))
        base = float(hist["total"].iloc[0]) if len(hist) else total
        ret_pct = (total / base - 1) * 100 if base else 0.0
        month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        m_hist = hist[hist["snap_date"] >= month_ago]
        month_base = float(m_hist["total"].iloc[0]) if len(m_hist) else base
        month_pct = (total / month_base - 1) * 100 if month_base else 0.0
        live_returns["India" if market == "india" else "US"] = round(ret_pct, 4)

        st.subheader(MARKET_LABEL[market])
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Total value", f"{cur}{total:,.0f}", f"{ret_pct:+.2f}% all-time")
        c2.metric("Invested (at cost)", f"{cur}{invested:,.0f}")
        c3.metric("Cash left", f"{cur}{cash:,.0f}")
        c4.metric("Unrealized P&L", f"{cur}{unrealized:,.0f}",
                  f"{(unrealized / invested * 100) if invested else 0:+.2f}%")
        c5.metric("Today", f"{cur}{day_change:,.0f}",
                  f"{(day_change / value_now * 100) if value_now else 0:+.2f}%")
        c6.metric("Past month", f"{month_pct:+.2f}%",
                  help="Grows meaningful as daily snapshots accumulate")
        if realized_pnl:
            st.caption(f"Realized profit from closed trades: {cur}{realized_pnl:,.0f}")

        if len(mpos):
            mpos["Day %"] = ((mpos["live"] / mpos["prev"] - 1) * 100).round(2)
            mpos["P&L"] = ((mpos["live"] - mpos["avg_price"]) * mpos["qty"]).round(0)
            mpos["P&L %"] = ((mpos["live"] / mpos["avg_price"] - 1) * 100).round(2)
            mpos["Weight %"] = (mpos["qty"] * mpos["live"] / total * 100).round(1)
            mpos["Why bought"] = mpos["ticker"].map(buy_map).fillna("")
            view = mpos[["ticker", "name", "qty", "avg_price", "live", "Day %", "P&L",
                         "P&L %", "Weight %", "last_score", "opened_at", "Why bought"]]
            view = view.rename(columns={"avg_price": "Bought at", "live": "Live price",
                                        "last_score": "Score", "opened_at": "Opened"})
            st.dataframe(view.style.map(pnl_color, subset=["Day %", "P&L", "P&L %"]),
                         width="stretch", hide_index=True)

            g1, g2 = st.columns(2)
            alloc = mpos[["ticker", "qty", "live"]].copy()
            alloc["value"] = alloc["qty"] * alloc["live"]
            alloc = pd.concat([alloc[["ticker", "value"]],
                               pd.DataFrame([{"ticker": "CASH", "value": cash}])])
            donut = alt.Chart(alloc).mark_arc(innerRadius=55).encode(
                theta=alt.Theta("value:Q"),
                color=alt.Color("ticker:N", legend=alt.Legend(title=None)),
                tooltip=["ticker", alt.Tooltip("value:Q", format=",.0f")],
            ).properties(height=280, title="Where the money is")
            g1.altair_chart(donut, use_container_width=True)

            bars = alt.Chart(mpos).mark_bar().encode(
                x=alt.X("P&L:Q", title=f"Profit / loss ({cur})"),
                y=alt.Y("ticker:N", sort="-x", title=None),
                color=alt.condition(alt.datum["P&L"] > 0, alt.value("#16a34a"),
                                    alt.value("#dc2626")),
                tooltip=["ticker", "P&L", "P&L %"],
            ).properties(height=280, title="Profit / loss per position")
            g2.altair_chart(bars, use_container_width=True)
        st.divider()

    if live_returns:
        buf = return_buffer()
        buf.append({"time": datetime.now(), **live_returns})
        if len(buf) > 1:
            st.subheader("📈 Live return — moving with your profit")
            ldf = pd.DataFrame(list(buf)).melt("time", var_name="Market",
                                               value_name="Return %")
            line = alt.Chart(ldf).mark_line(interpolate="monotone").encode(
                x=alt.X("time:T", axis=alt.Axis(format="%H:%M:%S"), title=None),
                y=alt.Y("Return %:Q", scale=alt.Scale(zero=False)),
                color=alt.Color("Market:N",
                                scale=alt.Scale(domain=["India", "US"],
                                                range=["#f59e0b", "#3b82f6"]),
                                legend=alt.Legend(title=None, orient="top")),
                tooltip=["Market", alt.Tooltip("Return %:Q", format=".3f"),
                         alt.Tooltip("time:T", format="%H:%M:%S")],
            ).properties(height=260)
            st.altair_chart(line, use_container_width=True)
            st.caption("India in orange, US in blue — a new point every second while "
                       "this page is open; the line goes flat when both markets are closed.")

    hist_all = load("SELECT snap_date, market, total FROM portfolio_history ORDER BY snap_date")
    if hist_all["snap_date"].nunique() > 2:
        st.subheader("Portfolio value over time")
        st.line_chart(hist_all.pivot_table(index="snap_date", columns="market", values="total"))
    else:
        st.caption("📅 The portfolio-value chart appears after a few daily snapshots.")

    st.subheader("Trade log — every buy & sell with its reason")
    trades = load("SELECT executed_at AS 'When', side, ticker, name, qty, price, value, "
                  "reason AS 'Why' FROM trades ORDER BY executed_at DESC")
    if trades.empty:
        st.info("No trades yet.")
    else:
        st.dataframe(trades.style.map(
            lambda v: "color: #16a34a; font-weight: 600" if v == "BUY"
            else ("color: #dc2626; font-weight: 600" if v == "SELL" else ""),
            subset=["side"]), width="stretch", hide_index=True)


if page == "Live Portfolio":
    st.title("Live Paper Portfolio")
    st.markdown(
        "> **Platform:** no broker — this is the system's built-in simulator. "
        "Prices are live from **Yahoo Finance**; the money is virtual, so nothing "
        "real is at risk while the strategy proves itself.")
    live_portfolio()

elif page == "Today's Picks":
    st.title(f"Today's Picks — {latest}")
    market = st.radio("Market", ["All", "India (Nifty 50)", "US (S&P 500)"], horizontal=True)
    show_all = st.checkbox("Include screened-out stocks (technical score only)")

    df = load("SELECT * FROM scores WHERE run_date = ? ORDER BY final_score DESC", (latest,))
    if market.startswith("India"):
        df = df[df["market"] == "india"]
    elif market.startswith("US"):
        df = df[df["market"] == "us"]
    if not show_all:
        df = df[df["deep_dive"] == 1]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stocks analyzed", len(df))
    c2.metric("STRONG", int((df["verdict"] == "STRONG").sum()))
    c3.metric("MODERATE", int((df["verdict"] == "MODERATE").sum()))
    c4.metric("Top score", f"{int(df['final_score'].max())}%" if len(df) else "—")

    view = df[["ticker", "name", "market", "verdict", "final_score", "tech_score",
               "fund_score", "sent_score", "price", "ret_1m_pct", "ret_1y_pct",
               "reasons"]].rename(columns={
        "final_score": "Score %", "tech_score": "Tech", "fund_score": "Fund",
        "sent_score": "Sent", "ret_1m_pct": "1M %", "ret_1y_pct": "1Y %",
    })
    st.dataframe(view.style.map(color_verdict, subset=["verdict"]),
                 width="stretch", height=600, hide_index=True)

elif page == "Stock Detail":
    st.title("Stock Detail")
    df = load("SELECT * FROM scores WHERE run_date = ? AND deep_dive = 1 "
              "ORDER BY final_score DESC", (latest,))
    if df.empty:
        st.info("No deep-dived stocks for the latest run.")
        st.stop()
    labels = {f"{r['ticker']} — {r['name']}": r["ticker"] for _, r in df.iterrows()}
    choice = st.selectbox("Stock", list(labels))
    t = labels[choice]
    row = df[df["ticker"] == t].iloc[0]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Final score", f"{int(row['final_score'])}%")
    c2.metric("Verdict", row["verdict"])
    c3.metric("Technical", f"{int(row['tech_score'])}")
    c4.metric("Fundamental", f"{int(row['fund_score'])}" if pd.notna(row["fund_score"]) else "—")
    c5.metric("Sentiment", f"{int(row['sent_score'])}" if pd.notna(row["sent_score"]) else "—")

    st.subheader("Why")
    for reason in str(row["reasons"]).split(" | "):
        st.markdown(f"- {reason}")

    st.subheader("Snapshot")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", f"{row['price']:,.2f}" if pd.notna(row["price"]) else "—")
    c2.metric("1-month return", f"{row['ret_1m_pct']:.1f}%")
    c3.metric("1-year return", f"{row['ret_1y_pct']:.1f}%")
    c4.metric("Off 52-week high", f"{row['off_high_pct']:.1f}%")

    hist = load("SELECT run_date, final_score, tech_score, fund_score, sent_score "
                "FROM scores WHERE ticker = ? ORDER BY run_date", (t,))
    if len(hist) > 1:
        st.subheader("Score history")
        st.line_chart(hist.set_index("run_date")[["final_score", "tech_score",
                                                  "fund_score", "sent_score"]])
    else:
        st.caption("Score history builds up as the daily runs accumulate.")

elif page == "Score History":
    st.title("Score History")
    st.caption("How each stock's final score moved across daily runs.")
    hist = load("SELECT run_date, ticker, final_score FROM scores WHERE deep_dive = 1")
    if hist.empty:
        st.info("No history yet.")
        st.stop()
    top = load("SELECT ticker FROM scores WHERE run_date = ? AND deep_dive = 1 "
               "ORDER BY final_score DESC LIMIT 10", (latest,))["ticker"].tolist()
    picks = st.multiselect("Stocks", sorted(hist["ticker"].unique()), default=top[:5])
    if picks:
        pivot = hist[hist["ticker"].isin(picks)].pivot_table(
            index="run_date", columns="ticker", values="final_score")
        st.line_chart(pivot)

else:  # Alerts Log
    st.title("Alerts Log")
    alerts = load("SELECT sent_at, ticker, market, name, final_score, verdict, message "
                  "FROM alerts ORDER BY sent_at DESC")
    if alerts.empty:
        st.info("No alerts yet. Alerts fire when a stock's final score crosses the "
                "threshold in config/settings.yaml (currently 75).")
    else:
        st.dataframe(alerts, width="stretch", hide_index=True)
