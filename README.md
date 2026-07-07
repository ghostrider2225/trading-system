# Trading System

Daily stock analysis for **Nifty 50** and **S&P 500**: screens every stock in both
indexes, scores them through five stages, records everything in a database, shows a
dashboard, and fires a desktop notification when a stock crosses the alert threshold.

> The score measures how strongly the data agrees (technicals + fundamentals +
> sentiment). It is **not** a guaranteed probability and not financial advice —
> every score comes with its reasons so you can judge for yourself.

## Daily flow

Runs automatically twice a day (macOS launchd):

| Time (UK) | Run |
|---|---|
| 08:00 | Indian market (Nifty 50) |
| 13:45 | US market (S&P 500), before the 14:30 US open |

Each run: **Stage 1** screen the index → **Stage 2** 1-year history stats →
**Stage 4** technical score for every stock → top 40 get a deep dive:
**Stage 3** fundamentals + **Stage 5** sentiment → weighted final score
(40% technical, 35% fundamental, 25% sentiment) → saved to SQLite →
alerts for scores ≥ 75.

Verdicts: **STRONG** ≥ 75 · **MODERATE** ≥ 60 · **WEAK** ≥ 45 · **AVOID** < 45.

## Commands

```bash
cd ~/trading-system   # note: lives in the home folder (Desktop is blocked for
                      # background services); the Desktop icon is a shortcut

# dashboard + public share link run automatically as background services
open http://localhost:8501    # open the dashboard
grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' reports/tunnel.log | head -1  # share link

.venv/bin/python run_daily.py     # run the full analysis now (both markets)
.venv/bin/python run_daily.py --market us      # one market only
.venv/bin/python run_daily.py --limit 10       # quick test
```

## Configuration — `config/settings.yaml`

- `alerts.threshold` — notification trigger score (default 75)
- `weights` — how much each stage counts in the final score
- `screening.deep_dive_top_n` — how many stocks per market get the full analysis

## Files

- `collector/` — the five analysis stages + scoring engine
- `database/trading.db` — every day's scores and alerts (builds score history over time)
- `dashboard/app.py` — Streamlit dashboard (Today's Picks, Stock Detail, Score History, Alerts Log)
- `reports/scheduler.log` — output of the automatic runs
- `reports/tunnel.log` — contains the current public share URL (changes if the
  tunnel restarts, e.g. after a reboot)
- Background services in `~/Library/LaunchAgents/` (disable with `launchctl unload <path>`):
  `com.hardeep.trading-system` (daily analysis), `com.hardeep.trading-dashboard`
  (dashboard on :8501), `com.hardeep.trading-tunnel` (public link)
