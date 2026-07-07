"""Stage 2 — History & plans: derive where the stock sits in its yearly range,
its volatility and drawdown, and (for deep-dive stocks) the next earnings date."""
import pandas as pd
import yfinance as yf


def history_stats(df):
    close = df["Close"]
    last = float(close.iloc[-1])
    high_52w, low_52w = float(close.max()), float(close.min())
    pos_in_range = (last - low_52w) / (high_52w - low_52w) if high_52w > low_52w else 0.5
    daily_ret = close.pct_change().dropna()
    volatility = float(daily_ret.std() * (252 ** 0.5) * 100)  # annualized %
    drawdown = float((last / high_52w - 1) * 100)
    ret_1m = float(close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 21 else 0.0
    ret_3m = float(close.iloc[-1] / close.iloc[-63] - 1) * 100 if len(close) > 63 else 0.0
    ret_1y = float(close.iloc[-1] / close.iloc[0] - 1) * 100
    return {
        "price": round(last, 2),
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "pos_in_52w_range": round(pos_in_range * 100, 1),
        "volatility_pct": round(volatility, 1),
        "off_high_pct": round(drawdown, 1),
        "ret_1m_pct": round(ret_1m, 1),
        "ret_3m_pct": round(ret_3m, 1),
        "ret_1y_pct": round(ret_1y, 1),
    }


def next_earnings(ticker_obj):
    """Upcoming earnings date if Yahoo has one — the main 'future plan' signal."""
    try:
        cal = ticker_obj.calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if dates:
            return str(dates[0])
    except Exception:
        pass
    return None


def run(histories):
    print(f"  [stage2] computing history stats for {len(histories)} stocks")
    return {t: history_stats(df) for t, df in histories.items()}
