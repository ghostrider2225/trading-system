#!/usr/bin/env python3
"""Weekly report: all trades from past 7 days + combined return across both markets.
Very simple, visual format with emojis and clear numbers."""

import os
import smtplib
import sqlite3
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "database", "trading.db")
EMAIL = "hardeepsingh783888@gmail.com"
DASHBOARD_URL = "https://hardeep-trading.streamlit.app"


def send_weekly_report():
    """Send weekly report: all trades + combined return for past 7 days."""
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not password:
        print("[weekly] GMAIL_APP_PASSWORD not set; skipping weekly email")
        return

    conn = sqlite3.connect(DB_PATH)

    # week dates
    now = datetime.now()
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    week_end = now.strftime("%Y-%m-%d")

    # get portfolio history for the week (snapshots)
    week_history = conn.execute("""
        SELECT snap_date, market, cash, holdings_value, total
        FROM portfolio_history
        WHERE snap_date >= ? AND snap_date <= ?
        ORDER BY snap_date DESC
    """, [week_start, week_end]).fetchall()

    # get all trades in the past 7 days
    trades_7d = conn.execute("""
        SELECT executed_at, ticker, market, name, side, qty, price, value, reason
        FROM trades
        WHERE executed_at >= ?
        ORDER BY executed_at DESC
    """, [week_start]).fetchall()

    # calculate starting values (7 days ago)
    week_ago_history = conn.execute("""
        SELECT market, total FROM portfolio_history
        WHERE snap_date < ? ORDER BY snap_date DESC LIMIT 2
    """, [week_start]).fetchall()

    start_values = {m: v for m, v in week_ago_history}  # market -> total value
    if not start_values:
        # if no history yet, use current cash + holdings
        start_values = {}
        for market in ("india", "us"):
            cash_row = conn.execute("SELECT cash FROM portfolio_cash WHERE market = ?",
                                    [market]).fetchone()
            holdings_row = conn.execute(
                "SELECT COALESCE(SUM(qty * last_price), 0) FROM positions WHERE market = ?",
                [market]).fetchone()
            cash = float(cash_row[0]) if cash_row else 0
            holdings = float(holdings_row[0]) if holdings_row else 0
            start_values[market] = cash + holdings

    # current values
    current_values = {}
    for market in ("india", "us"):
        cash_row = conn.execute("SELECT cash FROM portfolio_cash WHERE market = ?",
                                [market]).fetchone()
        holdings_row = conn.execute(
            "SELECT COALESCE(SUM(qty * last_price), 0) FROM positions WHERE market = ?",
            [market]).fetchone()
        cash = float(cash_row[0]) if cash_row else 0
        holdings = float(holdings_row[0]) if holdings_row else 0
        current_values[market] = cash + holdings

    # calculate changes
    india_start = start_values.get("india", 0)
    us_start = start_values.get("us", 0)
    india_now = current_values.get("india", 0)
    us_now = current_values.get("us", 0)

    india_change = india_now - india_start
    us_change = us_now - us_start
    india_pct = (india_change / india_start * 100) if india_start > 0 else 0
    us_pct = (us_change / us_start * 100) if us_start > 0 else 0

    # combined return (in currency-agnostic terms)
    total_start = india_start + us_start
    total_now = india_now + us_now
    total_change = total_now - total_start
    total_pct = (total_change / total_start * 100) if total_start > 0 else 0

    # count buys/sells
    buys = [t for t in trades_7d if t[4] == "BUY"]
    sells = [t for t in trades_7d if t[4] == "SELL"]

    conn.close()

    # build HTML
    total_indicator = "📈" if total_pct >= 0 else "📉"
    india_indicator = "📈" if india_pct >= 0 else "📉"
    us_indicator = "📈" if us_pct >= 0 else "📉"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; color: #333;">
    <h2 style="text-align: center; color: #1e293b;">📊 Weekly Trading Report</h2>
    <p style="text-align: center; color: #64748b; font-size: 14px;">
    {week_start} to {week_end}</p>

    <div style="background: #f1f5f9; padding: 20px; border-radius: 8px; margin: 20px 0;">
    <h3 style="color: #1e293b; margin-top: 0;">🎯 Overall Performance</h3>
    <div style="font-size: 28px; font-weight: bold; color: #16a34a; text-align: center; margin: 15px 0;">
    {total_indicator} {total_pct:+.2f}%
    </div>
    <div style="text-align: center; font-size: 16px; color: #475569;">
    <strong>+₹{india_change:,.0f}</strong> (India) &nbsp; <strong>+${us_change:,.2f}</strong> (US)
    </div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0;">
    <div style="background: #e7f5ff; padding: 15px; border-radius: 6px; border-left: 4px solid #1971c2;">
    <h4 style="margin: 0 0 10px 0; color: #1e293b;">🇮🇳 India (Nifty)</h4>
    <div style="font-size: 24px; font-weight: bold; color: {'#16a34a' if india_pct >= 0 else '#dc2626'};">
    {india_indicator} {india_pct:+.2f}%
    </div>
    <div style="font-size: 13px; color: #64748b; margin-top: 5px;">
    ₹{india_start:,.0f} → ₹{india_now:,.0f}<br/>
    Change: ₹{india_change:+,.0f}
    </div>
    </div>

    <div style="background: #fff3cd; padding: 15px; border-radius: 6px; border-left: 4px solid #dc6412;">
    <h4 style="margin: 0 0 10px 0; color: #1e293b;">🇺🇸 USA (S&P 500)</h4>
    <div style="font-size: 24px; font-weight: bold; color: {'#16a34a' if us_pct >= 0 else '#dc2626'};">
    {us_indicator} {us_pct:+.2f}%
    </div>
    <div style="font-size: 13px; color: #64748b; margin-top: 5px;">
    ${us_start:,.2f} → ${us_now:,.2f}<br/>
    Change: ${us_change:+,.2f}
    </div>
    </div>
    </div>

    <div style="background: #f0f9ff; padding: 15px; border-radius: 6px; margin: 20px 0;">
    <h4 style="color: #1e293b; margin-top: 0;">📈 Trading Activity</h4>
    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; text-align: center;">
    <div>
    <div style="font-size: 20px; font-weight: bold; color: #16a34a;">🟢 {len(buys)}</div>
    <div style="font-size: 12px; color: #64748b;">Bought</div>
    </div>
    <div>
    <div style="font-size: 20px; font-weight: bold; color: #dc2626;">🔴 {len(sells)}</div>
    <div style="font-size: 12px; color: #64748b;">Sold</div>
    </div>
    <div>
    <div style="font-size: 20px; font-weight: bold; color: #1e293b;">{len(trades_7d)}</div>
    <div style="font-size: 12px; color: #64748b;">Total Trades</div>
    </div>
    </div>
    </div>
"""

    # trades table if any
    if trades_7d:
        html += """
    <div style="margin: 20px 0;">
    <h4 style="color: #1e293b;">📜 All Trades This Week</h4>
    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
    <tr style="background: #1e293b; color: white;">
    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">When</th>
    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">Ticker</th>
    <th style="padding: 10px; text-align: center; border: 1px solid #e2e8f0;">Side</th>
    <th style="padding: 10px; text-align: right; border: 1px solid #e2e8f0;">Qty</th>
    <th style="padding: 10px; text-align: right; border: 1px solid #e2e8f0;">Price</th>
    <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">Reason</th>
    </tr>
"""
        for executed_at, ticker, market, name, side, qty, price, value, reason in trades_7d:
            side_icon = "🟢 BUY" if side == "BUY" else "🔴 SELL"
            side_color = "#16a34a" if side == "BUY" else "#dc2626"
            cur = "₹" if market == "india" else "$"
            html += f"""
    <tr style="background: {'#f1f5f9' if side == 'BUY' else '#fff5f5'}; border-bottom: 1px solid #e2e8f0;">
    <td style="padding: 8px; border: 1px solid #e2e8f0;">{executed_at}</td>
    <td style="padding: 8px; border: 1px solid #e2e8f0;"><b>{ticker}</b></td>
    <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center; color: {side_color};"><b>{side_icon}</b></td>
    <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">{qty:.4f}</td>
    <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">{cur}{price:,.2f}</td>
    <td style="padding: 8px; border: 1px solid #e2e8f0; font-size: 12px; color: #64748b;">{reason}</td>
    </tr>
"""
        html += """
    </table>
    </div>
"""
    else:
        html += """
    <div style="background: #f1f5f9; padding: 15px; border-radius: 6px; text-align: center; color: #64748b;">
    <p>No trades this week — portfolio held steady.</p>
    </div>
"""

    html += f"""
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
    <p style="text-align: center; font-size: 12px; color: #94a3b8;">
    Weekly automated report from your trading system<br/>
    <a href="{DASHBOARD_URL}">View full dashboard →</a>
    </p>
    </div>
    """

    # send email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Weekly Report: {total_pct:+.2f}% return"
    msg["From"] = EMAIL
    msg["To"] = EMAIL
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as s:
            s.starttls()
            s.login(EMAIL, password)
            s.sendmail(EMAIL, [EMAIL], msg.as_string())
        print(f"[weekly] ✓ Weekly report sent: {total_pct:+.2f}% return ({len(trades_7d)} trades)")
    except Exception as e:
        print(f"[weekly] ✗ Weekly report failed: {e}")


if __name__ == "__main__":
    send_weekly_report()
