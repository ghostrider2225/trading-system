"""Profit-target circuit breaker.

Computes the combined India+US portfolio return in a common currency (GBP), and
when it reaches the configured target, freezes ALL trading and fires a one-time
milestone email. FX converts both the starting cash and the current value at the
same live rate, so currency drift cancels out and the number is pure strategy return.
"""
from datetime import datetime

FALLBACK_FX = {"india": 126.85, "us": 1.336}  # GBPINR, GBPUSD (2026-07-07)


def live_fx_rates():
    """{'india': GBPINR, 'us': GBPUSD}; falls back to constants if offline."""
    rates = dict(FALLBACK_FX)
    try:
        import yfinance as yf
        raw = yf.download(["GBPINR=X", "GBPUSD=X"], period="5d", interval="1d",
                          progress=False, auto_adjust=True)["Close"].dropna()
        if len(raw):
            last = raw.iloc[-1]
            rates["india"] = float(last["GBPINR=X"])
            rates["us"] = float(last["GBPUSD=X"])
    except Exception as e:
        print(f"  [guard] FX fetch failed ({e}); using fallback rates")
    return rates


def is_halted(conn):
    r = conn.execute("SELECT value FROM system_state WHERE key = 'trading_halted'").fetchone()
    return bool(r and r[0] == "1")


def set_halted(conn, pct, start_gbp, current_gbp):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for k, v in [("trading_halted", "1"),
                 ("halted_at", now),
                 ("halt_return_pct", f"{pct:.2f}"),
                 ("halt_start_gbp", f"{start_gbp:.2f}"),
                 ("halt_current_gbp", f"{current_gbp:.2f}")]:
        conn.execute("INSERT OR REPLACE INTO system_state VALUES (?, ?)", [k, v])
    conn.commit()


def overall_return(conn, cfg):
    """Return (pct, start_gbp, current_gbp, per_market) or None if no portfolio yet."""
    starting = cfg["paper_trading"]["starting_cash"]
    rates = live_fx_rates()
    start_gbp = current_gbp = 0.0
    per_market = {}
    have_data = False
    for market in ("india", "us"):
        row = conn.execute("SELECT cash FROM portfolio_cash WHERE market = ?",
                           [market]).fetchone()
        if not row:
            continue
        have_data = True
        cash = float(row[0])
        value = conn.execute(
            "SELECT COALESCE(SUM(qty * last_price), 0) FROM positions WHERE market = ?",
            [market]).fetchone()[0]
        rate = rates[market]
        s_gbp = float(starting[market]) / rate
        c_gbp = (cash + value) / rate
        start_gbp += s_gbp
        current_gbp += c_gbp
        per_market[market] = {"cash": cash, "value": value, "total": cash + value,
                              "rate": rate, "start_gbp": s_gbp, "current_gbp": c_gbp}
    if not have_data or start_gbp == 0:
        return None
    pct = (current_gbp / start_gbp - 1) * 100
    return pct, start_gbp, current_gbp, per_market


def check_profit_target(conn, cfg):
    """If the combined return has hit the target, halt trading and email once.
    Returns True if it just triggered (so callers can stop trading this run)."""
    target = cfg["paper_trading"].get("profit_target_pct")
    if not target or is_halted(conn):
        return is_halted(conn)
    res = overall_return(conn, cfg)
    if res is None:
        return False
    pct, start_gbp, current_gbp, per_market = res
    if pct < target:
        return False
    print(f"  [guard] 🎯 PROFIT TARGET HIT: overall {pct:+.2f}% — halting all trading")
    set_halted(conn, pct, start_gbp, current_gbp)
    try:
        import email_report
        email_report.send_milestone(conn, pct, start_gbp, current_gbp, per_market, target)
    except Exception as e:
        print(f"  [guard] milestone email failed: {e}")
    return True
