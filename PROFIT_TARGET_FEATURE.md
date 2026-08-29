# Profit-Target Circuit Breaker Feature

**Status:** ✅ Implemented & deployed to GitHub

When your combined India + US portfolio reaches **+10% profit in GBP**, the entire trading system automatically:
1. **Halts all trading** — no new buys, no new sells
2. **Sends a milestone email** with complete investment journey details
3. **Persists halt state** in SQLite so trading stays frozen even if system restarts

## How It Works

### 1. Guard Module (`portfolio/guard.py`)
Monitors the portfolio's combined P&L across both markets:

- **`live_fx_rates()`**: Fetches live GBPINR and GBPUSD rates from yfinance, with fallback to constants if offline
- **`overall_return(conn, cfg)`**: Computes combined GBP return
  - Converts India starting cash (₹12,684) to GBP using live rate
  - Converts US starting cash ($133.60) to GBP using live rate
  - Same FX rate used for start and current, so currency drift cancels out
  - Returns: `(pct_return, start_gbp, current_gbp, per_market_breakdown)`
  
- **`check_profit_target(conn, cfg)`**: Called after every trading run
  - If P&L < target: does nothing
  - If P&L ≥ target AND already halted: skips silently
  - If P&L ≥ target AND NOT halted: calls `set_halted()`, triggers `send_milestone()`

- **`set_halted(conn, ...)`**: Persists halt state to database
  - Stores `trading_halted=1` in system_state table
  - Also records: halted timestamp, return %, starting GBP, current GBP

### 2. Portfolio Manager Integration (`portfolio/manager.py`)
Modified `process()` function:

```python
def process(rows, cfg):
    ...
    if guard.is_halted(conn):
        print("  [portfolio] trading is HALTED — no trades")
        conn.close()
        return
    
    # ... normal trading logic ...
    
    conn.commit()
    guard.check_profit_target(conn, cfg)  # detect & email if target hit
    conn.close()
```

### 3. Milestone Email (`email_report.send_milestone()`)
Fires once when profit target is reached:

**Subject:** `🎯 MILESTONE: Profit Target Reached (+X.XX%)`

**Content:**
- **Investment Summary** table: Started £200, Now £X, +Y%, elapsed days, # trades
- **Per-Market Breakdown** (GBP): India started/now/return%, US started/now/return%
- **Complete Trade History**: Every buy/sell with timestamp, ticker, qty, price, value, reason

**Sent to:** hardeepsingh783888@gmail.com

### 4. Configuration (`config/settings.yaml`)
```yaml
paper_trading:
  profit_target_pct: 10  # set to null to disable
```

Change this value to adjust the circuit-breaker threshold (e.g., `5` for +5%, `20` for +20%).

### 5. Database Persistence (`database/db.py`)
System state is stored in a `system_state` table:
```sql
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

When profit target is hit:
- `trading_halted` → `"1"`
- `halted_at` → `"2026-08-29 14:32"` (timestamp)
- `halt_return_pct` → `"10.50"` (actual return when halt triggered)
- `halt_start_gbp` → `"200.00"` (starting investment in GBP)
- `halt_current_gbp` → `"220.50"` (current value in GBP)

## User Workflow

1. **Normal operation** (8 AM India run, 1:45 PM US run):
   - Scores new stocks, buys/sells based on Lynch strategy
   - Portfolio grows (or shrinks)
   
2. **Profit target reached** (e.g., after 3 weeks, P&L = +10.50%):
   - Guard detects: `current_gbp / start_gbp = 1.105` → 10.5% return
   - Sets `trading_halted=1` in database
   - Calls `send_milestone()` with full trade history
   - **Email arrives** with complete investment summary
   
3. **Subsequent runs** (next day's 8 AM, 1:45 PM):
   - Manager checks `is_halted()` at run start
   - Returns early, skips all trading
   - Dashboard continues to show historical positions + trade log
   
4. **To resume trading**:
   - Edit database: `DELETE FROM system_state WHERE key = 'trading_halted'`
   - Or set `profit_target_pct: null` in settings.yaml and restart

## Key Features

✅ **FX rate handling**: Uses same rate for start and end, so currency swings don't distort the return %

✅ **One-time email**: Milestone fires exactly once (checked by already-halted state)

✅ **Persistent halt**: Survives system restarts (stored in SQLite)

✅ **Complete audit trail**: Email includes every trade from portfolio start to halt

✅ **No forced selling**: Positions are kept as-is when halted; only new trades blocked

✅ **Configurable threshold**: Change `profit_target_pct` in settings.yaml

## Testing

To manually test the feature without waiting 3+ weeks:

```bash
# Temporarily set target to a low value (e.g., -5 for early test)
sed -i '' 's/profit_target_pct: 10/profit_target_pct: -5/' config/settings.yaml

# Run the trading system (will detect target immediately if P&L < -5%)
python3 run_daily.py --auto

# Check system_state table
python3 << 'EOF'
from database import db
conn = db.connect()
state = conn.execute("SELECT * FROM system_state").fetchall()
print(state)
conn.close()
EOF

# Restore original setting
sed -i '' 's/profit_target_pct: -5/profit_target_pct: 10/' config/settings.yaml
```

## Troubleshooting

**Q: Why didn't the milestone email send?**
- `GMAIL_APP_PASSWORD` not set as GitHub Actions secret
- Check server logs in GitHub Actions → `daily-email.yml` run output

**Q: How do I know my trading is halted?**
- Dashboard will show no new trades in trade log
- Query the database: `SELECT value FROM system_state WHERE key = 'trading_halted'`

**Q: Can I change the target after trading starts?**
- Yes, edit `profit_target_pct` in settings.yaml
- Guard checks against the config value every run
- To prevent accidental halt, set to a very high value (e.g., `1000`) to disable

**Q: The P&L shows different values — which is the real one?**
- **Dashboard & email both use the same GBP-converted value** (handles FX)
- The portfolio history table stores per-market values (₹ and $)
- Email milestone uses GBP-converted sums for the global return %

---

**Deployed:** GitHub main branch, commit `f2bd8ee`  
**Next run:** India 8 AM UTC, US 1:45 PM UTC (GitHub Actions schedule)  
**Milestone threshold:** +10% (configurable)
