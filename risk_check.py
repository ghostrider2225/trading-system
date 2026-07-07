#!/usr/bin/env python3
"""Hourly risk check: fetch live prices for open paper positions and apply the
price rules (stop-loss / take-profit) between the main daily runs.
Sells only — new buys happen in the daily scored runs."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml
import yfinance as yf

from database import db
from portfolio.manager import record_trade, get_cash, set_cash

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "settings.yaml")


def main():
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    pt = cfg["paper_trading"]
    if not pt["enabled"]:
        return

    conn = db.connect()
    positions = conn.execute(
        "SELECT ticker, market, name, qty, avg_price FROM positions").fetchall()
    if not positions:
        print("No open positions.")
        return

    tickers = [p[0] for p in positions]
    raw = yf.download(tickers, period="5d", interval="1d", group_by="ticker",
                      threads=True, progress=False, auto_adjust=True)
    sold = 0
    for ticker, market, name, qty, avg_price in positions:
        try:
            close = (raw[ticker] if len(tickers) > 1 else raw)["Close"].dropna()
            price = float(close.iloc[-1])
        except Exception:
            continue
        pnl_pct = (price / avg_price - 1) * 100
        reason = None
        if pnl_pct <= -pt["stop_loss_pct"]:
            reason = f"stop-loss hit ({pnl_pct:.1f}%)"
        elif pnl_pct >= pt["take_profit_pct"]:
            reason = f"take-profit hit (+{pnl_pct:.1f}%)"
        if reason:
            cash = get_cash(conn, market, cfg) + qty * price
            conn.execute("DELETE FROM positions WHERE ticker = ?", [ticker])
            set_cash(conn, market, cash)
            record_trade(conn, "SELL",
                         {"ticker": ticker, "market": market, "name": name},
                         qty, price, reason + " [hourly check]")
            sold += 1
        else:
            conn.execute("UPDATE positions SET last_price = ? WHERE ticker = ?",
                         [price, ticker])

    # refresh today's equity snapshot with the new prices
    for market in ("india", "us"):
        cash = get_cash(conn, market, cfg)
        value = conn.execute(
            "SELECT COALESCE(SUM(qty * last_price), 0) FROM positions WHERE market = ?",
            [market]).fetchone()[0]
        conn.execute("INSERT OR REPLACE INTO portfolio_history VALUES (?, ?, ?, ?, ?)",
                     [datetime.now().strftime("%Y-%m-%d"), market, round(cash, 2),
                      round(value, 2), round(cash + value, 2)])
    conn.commit()
    conn.close()
    print(f"Risk check done — {len(positions)} positions checked, {sold} sold.")


if __name__ == "__main__":
    main()
