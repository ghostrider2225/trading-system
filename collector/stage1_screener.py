"""Stage 1 — Screener: batch-download a year of daily prices for the whole universe
and keep only stocks with enough clean history to analyze."""
import pandas as pd
import yfinance as yf


def download_history(tickers, min_history_days=200):
    """Returns {ticker: OHLCV DataFrame} for tickers passing the data-quality filter."""
    raw = yf.download(
        tickers, period="1y", interval="1d",
        group_by="ticker", threads=True, progress=False, auto_adjust=True,
    )
    histories = {}
    for t in tickers:
        try:
            df = raw[t].dropna(subset=["Close"]) if len(tickers) > 1 else raw.dropna(subset=["Close"])
        except KeyError:
            continue
        if len(df) < min_history_days:
            continue
        if df["Close"].iloc[-1] <= 0 or df["Volume"].tail(20).sum() == 0:
            continue
        histories[t] = df
    return histories


def run(tickers, min_history_days=200):
    print(f"  [stage1] downloading history for {len(tickers)} tickers...")
    histories = download_history(tickers, min_history_days)
    print(f"  [stage1] {len(histories)} passed the data-quality screen")
    return histories
