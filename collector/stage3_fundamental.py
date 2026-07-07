"""Stage 3 — Fundamental analysis, Peter Lynch GARP edition.

Lynch's method (Fidelity Magellan, 29.2%/yr 1977-1990): buy companies whose
earnings grow 15-30% a year at a price that hasn't caught up — PEG ratio
(P/E divided by growth) below 1 — with low debt and healthy profitability.
Scored in points normalized to 0-100 with reasons."""


def score_from_info(info):
    pts, max_pts, reasons = 0, 0, []
    pe = info.get("trailingPE")
    eg = info.get("earningsGrowth")  # 0.25 = 25%

    # PEG ratio (0-35) — Lynch's core test: growth cheaper than its price tag
    max_pts += 35
    peg = None
    if pe and pe > 0 and eg and eg > 0:
        peg = pe / (eg * 100)
        if peg < 0.5:
            pts += 35; reasons.append(f"PEG {peg:.2f} — growth very cheap (Lynch's dream)")
        elif peg < 1:
            pts += 28; reasons.append(f"PEG {peg:.2f} < 1 — paying less than the growth")
        elif peg < 1.5:
            pts += 16; reasons.append(f"PEG {peg:.2f} — fairly priced")
        elif peg < 2:
            pts += 7
        else:
            reasons.append(f"PEG {peg:.2f} — price far ahead of growth")
    elif eg is not None and eg <= 0:
        reasons.append("Earnings shrinking — fails Lynch's growth test")
    else:
        reasons.append("PEG not computable (missing P/E or growth data)")

    # Earnings growth sweet spot (0-25): 15-30% ideal, >50% unsustainable
    max_pts += 25
    if eg is not None:
        g = eg * 100
        if 15 <= g <= 30:
            pts += 25; reasons.append(f"Earnings growing {g:.0f}%/yr — Lynch's sweet spot")
        elif 10 <= g < 15 or 30 < g <= 50:
            pts += 16; reasons.append(f"Earnings growing {g:.0f}%/yr")
        elif 0 < g < 10:
            pts += 8
        elif g > 50:
            pts += 10; reasons.append(f"Growth {g:.0f}% — too hot to last, Lynch would be wary")
    # revenue growth as supporting evidence
    rg = info.get("revenueGrowth")
    max_pts += 5
    if rg is not None and rg > 0.10:
        pts += 5

    # Balance sheet (0-20): Lynch avoided debt-heavy companies
    de = info.get("debtToEquity")  # Yahoo reports as percentage
    max_pts += 20
    if de is not None:
        if de < 35:
            pts += 20; reasons.append("Very low debt")
        elif de < 80:
            pts += 14
        elif de < 150:
            pts += 6
        else:
            reasons.append(f"Heavy debt (D/E {de:.0f}%) — Lynch avoided these")
    else:
        pts += 10  # banks/financials report no D/E; stay neutral

    # Profitability (0-15): margins + ROE keep the growth honest
    margins = info.get("profitMargins")
    roe = info.get("returnOnEquity")
    max_pts += 15
    if margins is not None:
        if margins > 0.12:
            pts += 8
        elif margins > 0.05:
            pts += 5
        elif margins <= 0:
            reasons.append("Loss-making")
    if roe is not None:
        if roe > 0.15:
            pts += 7; reasons.append(f"Strong ROE {roe*100:.0f}%")
        elif roe > 0.08:
            pts += 4

    return round(pts / max_pts * 100), reasons, peg


def run(ticker_objs):
    """ticker_objs: {ticker: yfinance.Ticker} for deep-dive candidates only."""
    print(f"  [stage3] Lynch GARP fundamentals for {len(ticker_objs)} stocks")
    out = {}
    for t, obj in ticker_objs.items():
        try:
            info = obj.info or {}
            s, reasons, peg = score_from_info(info)
            out[t] = {
                "score": s, "reasons": reasons, "peg": peg,
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
            out[t] = {"score": 50, "reasons": ["Fundamentals unavailable"], "peg": None,
                      "name": t, "sector": "", "pe": None, "market_cap": None,
                      "recommendation_mean": None, "target_mean_price": None,
                      "current_price": None}
    return out
