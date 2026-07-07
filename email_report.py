#!/usr/bin/env python3
"""Morning email report: portfolio totals, every position with P&L, trades of the
last 26 hours, and today's top scored picks. Sent via Gmail SMTP; if no
GMAIL_APP_PASSWORD is set, writes a preview HTML instead."""
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
CUR = {"india": "₹", "us": "$"}
MARKET_NAME = {"india": "India — Nifty 50", "us": "US — S&P 500"}

TABLE_STYLE = ('style="border-collapse:collapse;width:100%;font-family:Arial,'
               'sans-serif;font-size:13px;margin-bottom:18px"')
TH = ('style="background:#1e293b;color:#fff;padding:7px 9px;text-align:left;'
      'font-size:12px"')
TD = 'style="padding:6px 9px;border-bottom:1px solid #e2e8f0"'


def color(v):
    return "#16a34a" if v > 0 else ("#dc2626" if v < 0 else "#334155")


def money(cur, v):
    return f"{cur}{v:,.0f}"


def build_html(conn):
    now = datetime.now()
    parts = [f"""
    <div style="font-family:Arial,sans-serif;max-width:720px;margin:auto">
    <h2 style="color:#1e293b">📈 Trading System — Morning Report</h2>
    <p style="color:#475569">{now.strftime('%A, %d %B %Y %H:%M')} ·
    <a href="{DASHBOARD_URL}">open the live dashboard</a><br>
    <span style="font-size:12px">Paper trading — virtual money, real market data.
    Scores are data-agreement measures, not guarantees or advice.</span></p>"""]

    for market in ("india", "us"):
        cur = CUR[market]
        row = conn.execute("SELECT cash FROM portfolio_cash WHERE market = ?",
                           [market]).fetchone()
        if not row:
            continue
        cash = row[0]
        pos = conn.execute(
            "SELECT ticker, name, qty, avg_price, last_price, last_score, opened_at "
            "FROM positions WHERE market = ? ORDER BY ticker", [market]).fetchall()
        value = sum(q * lp for _, _, q, _, lp, _, _ in pos)
        invested = sum(q * ap for _, _, q, ap, _, _, _ in pos)
        unreal = value - invested
        total = cash + value
        first = conn.execute(
            "SELECT total FROM portfolio_history WHERE market = ? "
            "ORDER BY snap_date LIMIT 1", [market]).fetchone()
        base = first[0] if first else total
        ret = (total / base - 1) * 100 if base else 0

        parts.append(f"""
        <h3 style="color:#1e293b;margin-bottom:4px">{MARKET_NAME[market]}</h3>
        <p style="margin-top:2px;font-size:14px">
        Total: <b>{money(cur, total)}</b>
        <span style="color:{color(ret)}"><b>({ret:+.2f}% all-time)</b></span> ·
        Invested: {money(cur, invested)} · Cash: {money(cur, cash)} ·
        Unrealized P&L: <span style="color:{color(unreal)}"><b>{money(cur, unreal)}</b></span></p>""")

        if pos:
            rows = ""
            for t, name, q, ap, lp, score, opened in pos:
                pnl = (lp - ap) * q
                pnl_pct = (lp / ap - 1) * 100
                rows += (f"<tr><td {TD}><b>{t}</b></td><td {TD}>{(name or '')[:24]}</td>"
                         f"<td {TD}>{q}</td><td {TD}>{ap:,.2f}</td><td {TD}>{lp:,.2f}</td>"
                         f"<td {TD}><span style='color:{color(pnl)}'>{money(cur, pnl)} "
                         f"({pnl_pct:+.1f}%)</span></td><td {TD}>{score}</td></tr>")
            parts.append(f"""<table {TABLE_STYLE}><tr><th {TH}>Stock</th><th {TH}>Name</th>
            <th {TH}>Qty</th><th {TH}>Bought</th><th {TH}>Now</th><th {TH}>P&L</th>
            <th {TH}>Score</th></tr>{rows}</table>""")
        else:
            parts.append("<p style='color:#64748b'>No open positions.</p>")

    since = (datetime.now() - timedelta(hours=26)).strftime("%Y-%m-%d %H:%M")
    trades = conn.execute(
        "SELECT executed_at, side, ticker, qty, price, value, reason, market "
        "FROM trades WHERE executed_at >= ? ORDER BY executed_at DESC", [since]).fetchall()
    parts.append("<h3 style='color:#1e293b'>Trades in the last 24 hours</h3>")
    if trades:
        rows = ""
        for at, side, t, q, p, v, reason, market in trades:
            c = "#16a34a" if side == "BUY" else "#dc2626"
            rows += (f"<tr><td {TD}>{at}</td><td {TD}><b style='color:{c}'>{side}</b></td>"
                     f"<td {TD}>{t}</td><td {TD}>{q} × {p:,.2f}</td>"
                     f"<td {TD}>{money(CUR[market], v)}</td><td {TD}>{reason}</td></tr>")
        parts.append(f"""<table {TABLE_STYLE}><tr><th {TH}>When</th><th {TH}>Side</th>
        <th {TH}>Stock</th><th {TH}>Deal</th><th {TH}>Value</th><th {TH}>Why</th></tr>
        {rows}</table>""")
    else:
        parts.append("<p style='color:#64748b'>No trades — nothing hit the buy or sell rules.</p>")

    latest = conn.execute("SELECT MAX(run_date) FROM scores").fetchone()[0]
    picks = conn.execute(
        "SELECT ticker, name, market, final_score, verdict, reasons FROM scores "
        "WHERE run_date = ? AND deep_dive = 1 ORDER BY final_score DESC LIMIT 10",
        [latest]).fetchall()
    if picks:
        rows = ""
        for t, name, market, score, verdict, reasons in picks:
            vc = {"STRONG": "#16a34a", "MODERATE": "#ca8a04"}.get(verdict, "#ea580c")
            rows += (f"<tr><td {TD}><b>{t}</b></td><td {TD}>{(name or '')[:22]}</td>"
                     f"<td {TD}><b>{score}%</b></td>"
                     f"<td {TD}><b style='color:{vc}'>{verdict}</b></td>"
                     f"<td {TD} title=''>{(reasons or '')[:110]}</td></tr>")
        parts.append(f"""<h3 style="color:#1e293b">Top 10 picks ({latest})</h3>
        <table {TABLE_STYLE}><tr><th {TH}>Stock</th><th {TH}>Name</th><th {TH}>Score</th>
        <th {TH}>Verdict</th><th {TH}>Why</th></tr>{rows}</table>""")

    parts.append(f"""<p style="font-size:12px;color:#94a3b8">Automatic report from your
    trading system · <a href="{DASHBOARD_URL}">{DASHBOARD_URL}</a></p></div>""")
    return "".join(parts)


def main():
    conn = sqlite3.connect(DB_PATH)
    html = build_html(conn)
    conn.close()

    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not password:
        preview = os.path.join(ROOT, "email_preview.html")
        with open(preview, "w") as f:
            f.write(html)
        print(f"GMAIL_APP_PASSWORD not set — preview written to {preview}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📈 Trading report {datetime.now():%d %b} — portfolio & picks"
    msg["From"] = EMAIL
    msg["To"] = EMAIL
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as s:
        s.starttls()
        s.login(EMAIL, password)
        s.sendmail(EMAIL, [EMAIL], msg.as_string())
    print(f"Report emailed to {EMAIL}.")


if __name__ == "__main__":
    main()
