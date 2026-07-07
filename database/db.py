"""SQLite persistence: every run's scores and every alert, kept forever so the
dashboard can show how a stock's score evolved."""
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS scores (
    run_date TEXT, run_time TEXT, ticker TEXT, market TEXT, name TEXT,
    sector TEXT, price REAL, tech_score INTEGER, fund_score INTEGER,
    sent_score INTEGER, final_score INTEGER, verdict TEXT, deep_dive INTEGER,
    reasons TEXT, pos_in_52w_range REAL, ret_1m_pct REAL, ret_3m_pct REAL,
    ret_1y_pct REAL, off_high_pct REAL, volatility_pct REAL,
    PRIMARY KEY (run_date, ticker)
);
CREATE TABLE IF NOT EXISTS alerts (
    sent_at TEXT, ticker TEXT, market TEXT, name TEXT,
    final_score INTEGER, verdict TEXT, message TEXT
);
CREATE TABLE IF NOT EXISTS portfolio_cash (
    market TEXT PRIMARY KEY, cash REAL
);
CREATE TABLE IF NOT EXISTS positions (
    ticker TEXT PRIMARY KEY, market TEXT, name TEXT, qty INTEGER,
    avg_price REAL, last_price REAL, last_score INTEGER, opened_at TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    executed_at TEXT, ticker TEXT, market TEXT, name TEXT, side TEXT,
    qty INTEGER, price REAL, value REAL, reason TEXT
);
CREATE TABLE IF NOT EXISTS portfolio_history (
    snap_date TEXT, market TEXT, cash REAL, holdings_value REAL, total REAL,
    PRIMARY KEY (snap_date, market)
);
"""


MIGRATIONS = [
    "ALTER TABLE scores ADD COLUMN peg REAL",
    "ALTER TABLE scores ADD COLUMN pe REAL",
    "ALTER TABLE scores ADD COLUMN eps_growth REAL",
    "ALTER TABLE scores ADD COLUMN debt_to_equity REAL",
    "ALTER TABLE scores ADD COLUMN lynch_category TEXT",
]


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    for m in MIGRATIONS:
        try:
            conn.execute(m)
        except sqlite3.OperationalError:
            pass  # column already exists
    return conn


def save_scores(rows):
    conn = connect()
    now = datetime.now()
    run_date, run_time = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    cols = ["ticker", "market", "name", "sector", "price", "tech_score", "fund_score",
            "sent_score", "final_score", "verdict", "deep_dive", "reasons",
            "pos_in_52w_range", "ret_1m_pct", "ret_3m_pct", "ret_1y_pct",
            "off_high_pct", "volatility_pct",
            "peg", "pe", "eps_growth", "debt_to_equity", "lynch_category"]
    for r in rows:
        conn.execute(
            f"INSERT OR REPLACE INTO scores (run_date, run_time, {', '.join(cols)}) "
            f"VALUES (?, ?, {', '.join('?' * len(cols))})",
            [run_date, run_time] + [r.get(c) for c in cols],
        )
    conn.commit()
    conn.close()
    return run_date


def save_alert(ticker, market, name, final_score, verdict, message):
    conn = connect()
    conn.execute(
        "INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?, ?)",
        [datetime.now().strftime("%Y-%m-%d %H:%M"), ticker, market, name,
         final_score, verdict, message],
    )
    conn.commit()
    conn.close()


def already_alerted_today(ticker):
    conn = connect()
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT 1 FROM alerts WHERE ticker = ? AND sent_at LIKE ?", [ticker, today + "%"]
    ).fetchone()
    conn.close()
    return row is not None
