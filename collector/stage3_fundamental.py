"""Stage 3 — Fundamental analysis: valuation, profitability, growth, balance sheet.
Uses Yahoo Finance company info; scored in points normalized to 0-100 with reasons."""


def score_from_info(info):
    pts, max_pts, reasons = 0, 0, []

    # Valuation (0-20): trailing P/E
    pe = info.get("trailingPE")
    max_pts += 20
    if pe and pe > 0:
        if pe < 18: pts += 20; reasons.append(f"Attractive P/E of {pe:.0f}")
        elif pe < 30: pts += 14; reasons.append(f"Reasonable P/E of {pe:.0f}")
        elif pe < 50: pts += 7
        else: reasons.append(f"Expensive: P/E {pe:.0f}")
    else:
        reasons.append("No earnings (negative or missing P/E)")

    # Profitability (0-25): ROE and margins
    roe = info.get("returnOnEquity")
    margins = info.get("profitMargins")
    max_pts += 25
    if roe is not None:
        if roe > 0.20: pts += 15; reasons.append(f"Strong ROE {roe*100:.0f}%")
        elif roe > 0.10: pts += 10
        elif roe > 0: pts += 4
        else: reasons.append("Negative return on equity")
    if margins is not None:
        if margins > 0.15: pts += 10; reasons.append(f"Healthy profit margin {margins*100:.0f}%")
        elif margins > 0.05: pts += 6
        elif margins <= 0: reasons.append("Loss-making")

    # Growth (0-30): earnings and revenue growth
    eg = info.get("earningsGrowth")
    rg = info.get("revenueGrowth")
    max_pts += 30
    if eg is not None:
        if eg > 0.20: pts += 17; reasons.append(f"Earnings growing {eg*100:.0f}%")
        elif eg > 0.05: pts += 11
        elif eg > 0: pts += 5
        else: reasons.append(f"Earnings shrinking {eg*100:.0f}%")
    if rg is not None:
        if rg > 0.15: pts += 13; reasons.append(f"Revenue growing {rg*100:.0f}%")
        elif rg > 0.05: pts += 8
        elif rg > 0: pts += 4
        else: reasons.append("Revenue declining")

    # Balance sheet (0-25): debt/equity and current ratio
    de = info.get("debtToEquity")  # Yahoo reports as percentage, e.g. 45.2
    cr = info.get("currentRatio")
    max_pts += 25
    if de is not None:
        if de < 50: pts += 15; reasons.append("Low debt")
        elif de < 120: pts += 9
        elif de < 250: pts += 4
        else: reasons.append(f"Heavy debt load (D/E {de:.0f}%)")
    else:
        pts += 8  # many banks/financials report no D/E; stay neutral
    if cr is not None:
        if cr > 1.5: pts += 10
        elif cr > 1.0: pts += 6
        else: reasons.append("Tight liquidity (current ratio < 1)")
    else:
        pts += 5

    return round(pts / max_pts * 100), reasons


def run(ticker_objs):
    """ticker_objs: {ticker: yfinance.Ticker} for deep-dive candidates only."""
    print(f"  [stage3] fetching fundamentals for {len(ticker_objs)} stocks")
    out = {}
    for t, obj in ticker_objs.items():
        try:
            info = obj.info or {}
            s, reasons = score_from_info(info)
            out[t] = {
                "score": s, "reasons": reasons,
                "name": info.get("shortName") or info.get("longName") or t,
                "sector": info.get("sector", ""),
                "pe": info.get("trailingPE"),
                "market_cap": info.get("marketCap"),
                "recommendation_mean": info.get("recommendationMean"),
                "target_mean_price": info.get("targetMeanPrice"),
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            }
        except Exception as e:
            print(f"  [stage3] {t}: {e}")
            out[t] = {"score": 50, "reasons": ["Fundamentals unavailable"], "name": t,
                      "sector": "", "pe": None, "market_cap": None,
                      "recommendation_mean": None, "target_mean_price": None,
                      "current_price": None}
    return out
