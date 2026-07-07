"""Desktop notifications (macOS) for stocks crossing the alert threshold."""
import subprocess

from database import db


def notify_desktop(title, message):
    script = f'display notification "{message}" with title "{title}" sound name "Glass"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=10)
    except Exception as e:
        print(f"  [alerts] notification failed: {e}")


def process(rows, cfg):
    if not cfg["alerts"]["enabled"]:
        return []
    threshold = cfg["alerts"]["threshold"]
    fired = []
    for r in rows:
        if r["deep_dive"] and r["final_score"] >= threshold:
            if db.already_alerted_today(r["ticker"]):
                continue
            msg = (f"{r['name']} scored {r['final_score']}% "
                   f"(T{r['tech_score']}/F{r['fund_score']}/S{r['sent_score']}) — open the dashboard")
            notify_desktop(f"📈 {r['verdict']}: {r['ticker']}", msg)
            db.save_alert(r["ticker"], r["market"], r["name"], r["final_score"],
                          r["verdict"], msg)
            fired.append(r["ticker"])
    if fired:
        print(f"  [alerts] fired: {', '.join(fired)}")
    return fired
