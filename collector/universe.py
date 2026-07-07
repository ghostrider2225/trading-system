"""Stock universes: Nifty 50 (hardcoded) and S&P 500 (fetched from Wikipedia, cached)."""
import json
import os
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SP500_CACHE = os.path.join(DATA_DIR, "sp500_tickers.json")
CACHE_MAX_AGE_DAYS = 30

NIFTY50 = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "HINDUNILVR", "ITC",
    "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "BAJFINANCE", "HCLTECH",
    "ASIANPAINT", "AXISBANK", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO",
    "WIPRO", "NESTLEIND", "NTPC", "POWERGRID", "M&M", "TATAMOTORS",
    "TATASTEEL", "JSWSTEEL", "ADANIENT", "ADANIPORTS", "COALINDIA", "ONGC",
    "BAJAJFINSV", "GRASIM", "TECHM", "HDFCLIFE", "SBILIFE", "BRITANNIA",
    "DRREDDY", "CIPLA", "DIVISLAB", "EICHERMOT", "HEROMOTOCO", "BAJAJ-AUTO",
    "APOLLOHOSP", "INDUSINDBK", "HINDALCO", "TATACONSUM", "BPCL",
    "SHRIRAMFIN", "TRENT",
]

# Fallback if Wikipedia is unreachable and no cache exists: S&P 500 heavyweights
SP500_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "LLY",
    "AVGO", "JPM", "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "COST",
    "ORCL", "MRK", "ABBV", "CVX", "CRM", "BAC", "AMD", "NFLX", "KO", "PEP",
    "TMO", "WMT", "ADBE", "DIS", "MCD", "CSCO", "ABT", "QCOM", "INTU",
    "CAT", "GE", "IBM", "TXN", "AMGN", "VZ", "PFE", "NOW", "UBER", "GS",
    "BKNG", "PLTR", "MS", "LOW", "HON", "UNP", "AXP", "BLK", "NKE", "T",
]


def india_tickers():
    return [t + ".NS" for t in NIFTY50]


def us_tickers():
    """S&P 500 constituents from Wikipedia, cached locally for a month."""
    if os.path.exists(SP500_CACHE):
        age_days = (time.time() - os.path.getmtime(SP500_CACHE)) / 86400
        if age_days < CACHE_MAX_AGE_DAYS:
            with open(SP500_CACHE) as f:
                return json.load(f)
    try:
        import urllib.request
        import pandas as pd
        req = urllib.request.Request(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8")
        from io import StringIO
        tables = pd.read_html(StringIO(html))
        tickers = [t.replace(".", "-") for t in tables[0]["Symbol"].tolist()]
        if len(tickers) > 400:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(SP500_CACHE, "w") as f:
                json.dump(tickers, f)
            return tickers
    except Exception as e:
        print(f"  [universe] S&P 500 fetch failed ({e}), using fallback list")
    if os.path.exists(SP500_CACHE):
        with open(SP500_CACHE) as f:
            return json.load(f)
    return SP500_FALLBACK


def get_universe(market):
    return india_tickers() if market == "india" else us_tickers()
