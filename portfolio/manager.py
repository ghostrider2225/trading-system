"""Paper-trading portfolio: invests virtual money according to the daily scores.

After each run: update holding prices -> apply sell rules (score decay, stop-loss,
take-profit) -> buy the highest-scoring STRONG stocks with the free cash.
All trades are virtual and recorded in the database."""
from datetime import datetime

from database import db
from alerts.notifier import notify_desktop

CURRENCY = {"india": "₹", "us": "$"}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def get_cash(conn, market, cfg):
    row = conn.execute("SELECT cash FROM portfolio_cash WHERE market = ?", [market]).fetchone()
    if row:
        return row[0]
    start = float(cfg["paper_trading"]["starting_cash"][market])
    conn.execute("INSERT INTO portfolio_cash VALUES (?, ?)", [market, start])
    return start


def set_cash(conn, market, cash):
    conn.execute("UPDATE portfolio_cash SET cash = ? WHERE market = ?", [cash, market])


def record_trade(conn, side, r, qty, price, reason):
    value = round(qty * price, 2)
    conn.execute(
        "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [_now(), r["ticker"], r["market"], r.get("name", r["ticker"]), side, qty, price,
         value, reason],
    )
    cur = CURRENCY[r["market"]]
    notify_desktop(
        f"{'🟢 BOUGHT' if side == 'BUY' else '🔴 SOLD'} (paper): {r['ticker']}",
        f"{qty} × {cur}{price:,.2f} = {cur}{value:,.2f} — {reason}",
    )
    print(f"  [portfolio] {side} {qty} {r['ticker']} @ {price:,.2f} — {reason}")


def process(rows, cfg):
    """Run the paper portfolio against today's scored rows."""
    pt = cfg["paper_trading"]
    if not pt["enabled"]:
        return
    by_ticker = {r["ticker"]: r for r in rows if r.get("price")}
    conn = db.connect()

    for market in ("india", "us"):
        market_rows = [r for r in rows if r["market"] == market and r.get("price")]
        if not market_rows:
            continue  # market not in this run; leave its holdings untouched
        cash = get_cash(conn, market, cfg)

        # --- update prices and apply sell rules on existing holdings ---
        holdings = conn.execute(
            "SELECT ticker, qty, avg_price FROM positions WHERE market = ?", [market]
        ).fetchall()
        for ticker, qty, avg_price in holdings:
            r = by_ticker.get(ticker)
            if not r:
                continue  # no fresh data today; hold
            price, score = float(r["price"]), r["final_score"]
            pnl_pct = (price / avg_price - 1) * 100
            reason = None
            if pnl_pct <= -pt["stop_loss_pct"]:
                reason = f"stop-loss hit ({pnl_pct:.1f}%)"
            elif pnl_pct >= pt["take_profit_pct"]:
                reason = f"take-profit hit (+{pnl_pct:.1f}%)"
            elif score < pt["exit_score"]:
                reason = f"score fell to {score}% ({pnl_pct:+.1f}%)"
            if reason:
                cash += qty * price
                conn.execute("DELETE FROM positions WHERE ticker = ?", [ticker])
                record_trade(conn, "SELL", r, qty, price, reason)
            else:
                conn.execute(
                    "UPDATE positions SET last_price = ?, last_score = ? WHERE ticker = ?",
                    [price, score, ticker],
                )

        # --- buy the best STRONG stocks not already held ---
        held = {t for (t,) in conn.execute(
            "SELECT ticker FROM positions WHERE market = ?", [market]).fetchall()}
        n_positions = len(held)
        budget = float(pt["starting_cash"][market]) * pt["position_size_pct"] / 100
        candidates = [r for r in market_rows
                      if r["deep_dive"] and r["final_score"] >= pt["buy_score"]
                      and r["ticker"] not in held]
        for r in sorted(candidates, key=lambda x: x["final_score"], reverse=True):
            if n_positions >= pt["max_positions"] or cash < budget:
                break
            price = float(r["price"])
            qty = int(budget // price)
            if qty < 1:
                continue
            cash -= qty * price
            conn.execute(
                "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [r["ticker"], market, r.get("name", r["ticker"]), qty, price,
                 price, r["final_score"], _now()],
            )
            record_trade(conn, "BUY", r, qty, price, f"scored {r['final_score']}% (STRONG)")
            n_positions += 1

        set_cash(conn, market, cash)

        # --- snapshot total equity for the performance chart ---
        value = conn.execute(
            "SELECT COALESCE(SUM(qty * last_price), 0) FROM positions WHERE market = ?",
            [market],
        ).fetchone()[0]
        conn.execute(
            "INSERT OR REPLACE INTO portfolio_history VALUES (?, ?, ?, ?, ?)",
            [datetime.now().strftime("%Y-%m-%d"), market, round(cash, 2),
             round(value, 2), round(cash + value, 2)],
        )
        cur = CURRENCY[market]
        print(f"  [portfolio] {market}: cash {cur}{cash:,.0f} + holdings {cur}{value:,.0f}"
              f" = {cur}{cash + value:,.0f}")

    conn.commit()
    conn.close()
