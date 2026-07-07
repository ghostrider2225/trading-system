"""Scoring engine: weighted blend of technical, fundamental, and sentiment scores
into a final 0-100 score and a verdict."""


def verdict_for(score, cfg):
    v = cfg["verdicts"]
    if score >= v["strong"]:
        return "STRONG"
    if score >= v["moderate"]:
        return "MODERATE"
    if score >= v["weak"]:
        return "WEAK"
    return "AVOID"


def combine(tech, fund, sent, cfg):
    w = cfg["weights"]
    final = round(tech * w["technical"] + fund * w["fundamental"] + sent * w["sentiment"])
    return final, verdict_for(final, cfg)


def build_results(market, histories_stats, technicals, fundamentals, sentiments, cfg):
    """Merge all stage outputs into one row per stock. Stocks outside the deep-dive
    set get a technical-only score and are marked 'screened'."""
    rows = []
    for t, tech in technicals.items():
        stats = histories_stats.get(t, {})
        if t in fundamentals:
            fund, sent = fundamentals[t], sentiments.get(t, {"score": 50, "reasons": []})
            final, verdict = combine(tech["score"], fund["score"], sent["score"], cfg)
            reasons = tech["reasons"][:3] + fund["reasons"][:3] + sent["reasons"][:2]
            rows.append({
                "ticker": t, "market": market, "name": fund.get("name", t),
                "sector": fund.get("sector", ""), "price": stats.get("price"),
                "tech_score": tech["score"], "fund_score": fund["score"],
                "sent_score": sent["score"], "final_score": final, "verdict": verdict,
                "deep_dive": 1, "reasons": " | ".join(reasons),
                "peg": fund.get("peg"), "pe": fund.get("pe"),
                "eps_growth": fund.get("eps_growth"),
                "debt_to_equity": fund.get("debt_to_equity"),
                "lynch_category": fund.get("lynch_category"),
                "pos_in_52w_range": stats.get("pos_in_52w_range"),
                "ret_1m_pct": stats.get("ret_1m_pct"),
                "ret_3m_pct": stats.get("ret_3m_pct"),
                "ret_1y_pct": stats.get("ret_1y_pct"),
                "off_high_pct": stats.get("off_high_pct"),
                "volatility_pct": stats.get("volatility_pct"),
            })
        else:
            rows.append({
                "ticker": t, "market": market, "name": t.replace(".NS", ""),
                "sector": "", "price": stats.get("price"),
                "tech_score": tech["score"], "fund_score": None,
                "sent_score": None, "final_score": tech["score"],
                "verdict": "SCREENED-OUT", "deep_dive": 0,
                "reasons": " | ".join(tech["reasons"][:3]),
                "pos_in_52w_range": stats.get("pos_in_52w_range"),
                "ret_1m_pct": stats.get("ret_1m_pct"),
                "ret_3m_pct": stats.get("ret_3m_pct"),
                "ret_1y_pct": stats.get("ret_1y_pct"),
                "off_high_pct": stats.get("off_high_pct"),
                "volatility_pct": stats.get("volatility_pct"),
            })
    rows.sort(key=lambda r: r["final_score"], reverse=True)
    return rows
