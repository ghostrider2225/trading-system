#!/usr/bin/env python3
"""Daily pipeline: screen -> history -> technicals -> deep-dive (fundamentals +
sentiment) -> score -> save -> alert.

Usage:
  python run_daily.py                  # both markets
  python run_daily.py --market india   # one market
  python run_daily.py --auto           # pick market by time of day (for scheduler)
  python run_daily.py --limit 10       # quick test on a small universe
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml
import yfinance as yf

from collector import universe, stage1_screener, stage2_history, stage3_fundamental
from collector import stage4_technical, stage5_sentiment, scorer
from database import db
from alerts import notifier
from portfolio import manager as portfolio

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "settings.yaml")


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run_market(market, cfg, limit=None):
    print(f"\n=== {market.upper()} — {cfg['markets'][market]['index']} ===")
    tickers = universe.get_universe(market)
    if limit:
        tickers = tickers[:limit]

    histories = stage1_screener.run(tickers, cfg["screening"]["min_history_days"])
    if not histories:
        print("  no data downloaded — check the internet connection")
        return []
    stats = stage2_history.run(histories)
    technicals = stage4_technical.run(histories)

    # Deep-dive: fundamentals + sentiment on the technically strongest stocks
    top_n = cfg["screening"]["deep_dive_top_n"]
    top = sorted(technicals, key=lambda t: technicals[t]["score"], reverse=True)[:top_n]
    ticker_objs = {t: yf.Ticker(t) for t in top}
    fundamentals = stage3_fundamental.run(ticker_objs)
    sentiments = stage5_sentiment.run(ticker_objs, fundamentals)

    rows = scorer.build_results(market, stats, technicals, fundamentals, sentiments, cfg)
    return rows


def push_to_cloud():
    """Push the fresh database to GitHub so the cloud dashboard updates."""
    root = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isdir(os.path.join(root, ".git")):
        return
    subprocess.run(["git", "add", "database/trading.db", "data"],
                   cwd=root, capture_output=True)
    commit = subprocess.run(
        ["git", "commit", "-m", f"data: {datetime.now():%Y-%m-%d %H:%M}"],
        cwd=root, capture_output=True)
    if commit.returncode != 0:
        return  # nothing new to commit
    push = subprocess.run(["git", "push"], cwd=root, capture_output=True, timeout=120)
    print("Cloud dashboard updated." if push.returncode == 0
          else f"Cloud push failed: {push.stderr.decode()[:200]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "us", "both"], default="both")
    ap.add_argument("--auto", action="store_true",
                    help="before 12:00 local run india, after run us (for the scheduler)")
    ap.add_argument("--limit", type=int, default=None, help="cap universe size (testing)")
    args = ap.parse_args()

    cfg = load_config()
    if args.auto:
        markets = ["india"] if datetime.now().hour < 12 else ["us"]
    elif args.market == "both":
        markets = ["india", "us"]
    else:
        markets = [args.market]
    markets = [m for m in markets if cfg["markets"][m]["enabled"]]

    print(f"Trading system run — {datetime.now().strftime('%Y-%m-%d %H:%M')} — markets: {markets}")
    all_rows = []
    for m in markets:
        all_rows += run_market(m, cfg, args.limit)

    if not all_rows:
        print("No results; nothing saved.")
        return

    all_rows.sort(key=lambda r: r["final_score"], reverse=True)
    run_date = db.save_scores(all_rows)
    notifier.process(all_rows, cfg)
    portfolio.process(all_rows, cfg)

    deep = [r for r in all_rows if r["deep_dive"]]
    print(f"\nSaved {len(all_rows)} stocks for {run_date} ({len(deep)} deep-dived).")
    print("\nTop 10 today:")
    for r in deep[:10]:
        print(f"  {r['final_score']:>3}%  {r['verdict']:<9} {r['ticker']:<14} {r['name'][:30]}")
    push_to_cloud()
    print("\nOpen the dashboard:  ./start_dashboard.sh")


if __name__ == "__main__":
    main()
