"""Stage 5 — Sentiment: analyst consensus, price-target upside, and news headline tone."""

POSITIVE = ["beat", "beats", "surge", "record", "growth", "upgrade", "upgraded", "buy",
            "outperform", "strong", "rally", "profit", "jump", "gain", "expansion",
            "wins", "award", "launch", "partnership", "dividend", "buyback", "soar"]
NEGATIVE = ["miss", "misses", "fall", "falls", "drop", "downgrade", "downgraded", "sell",
            "underperform", "weak", "loss", "lawsuit", "probe", "investigation", "recall",
            "layoff", "layoffs", "decline", "warns", "warning", "cut", "fraud", "plunge"]


def headline_tone(headlines):
    """Net tone of recent headlines: fraction in [-1, 1]."""
    if not headlines:
        return None, 0
    net = 0
    for h in headlines:
        text = h.lower()
        net += sum(w in text for w in POSITIVE) - sum(w in text for w in NEGATIVE)
    return max(-1.0, min(1.0, net / max(len(headlines), 1) / 2)), len(headlines)


def extract_headlines(ticker_obj, limit=15):
    try:
        items = ticker_obj.news or []
    except Exception:
        return []
    heads = []
    for item in items[:limit]:
        # yfinance news format varies by version; title may be nested under 'content'
        title = item.get("title") or (item.get("content") or {}).get("title")
        if title:
            heads.append(title)
    return heads


def score(ticker_obj, fund_data):
    pts, max_pts, reasons = 0, 0, []

    # Analyst consensus (0-40): Yahoo recommendationMean, 1 = strong buy .. 5 = sell
    rec = fund_data.get("recommendation_mean")
    max_pts += 40
    if rec:
        if rec <= 1.8: pts += 40; reasons.append("Analysts: strong buy consensus")
        elif rec <= 2.4: pts += 30; reasons.append("Analysts: buy consensus")
        elif rec <= 3.0: pts += 18; reasons.append("Analysts: hold")
        else: reasons.append("Analysts leaning negative")
    else:
        pts += 20  # no coverage — neutral

    # Price-target upside (0-30)
    target, price = fund_data.get("target_mean_price"), fund_data.get("current_price")
    max_pts += 30
    if target and price and price > 0:
        upside = (target / price - 1) * 100
        if upside > 20: pts += 30; reasons.append(f"Analyst target {upside:.0f}% above price")
        elif upside > 8: pts += 22; reasons.append(f"Analyst target {upside:.0f}% above price")
        elif upside > 0: pts += 12
        else: reasons.append(f"Price already above analyst target ({upside:.0f}%)")
    else:
        pts += 15

    # News tone (0-30)
    heads = extract_headlines(ticker_obj)
    tone, n = headline_tone(heads)
    max_pts += 30
    if tone is None:
        pts += 15  # no news — neutral
    elif tone > 0.15:
        pts += 30; reasons.append(f"Positive news flow ({n} recent headlines)")
    elif tone > -0.05:
        pts += 18
    else:
        pts += 5; reasons.append("Negative news flow")

    return round(pts / max_pts * 100), reasons


def run(ticker_objs, fundamentals):
    print(f"  [stage5] scoring sentiment for {len(ticker_objs)} stocks")
    out = {}
    for t, obj in ticker_objs.items():
        try:
            s, reasons = score(obj, fundamentals.get(t, {}))
            out[t] = {"score": s, "reasons": reasons}
        except Exception as e:
            print(f"  [stage5] {t}: {e}")
            out[t] = {"score": 50, "reasons": ["Sentiment unavailable"]}
    return out
