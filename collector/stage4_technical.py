"""Stage 4 — Technical analysis: RSI, MACD, moving averages, volume trend, momentum.
Each indicator contributes points; the total is normalized to 0-100 with reasons."""
import pandas as pd


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def macd_histogram(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd - signal


def score(df):
    """Returns (score 0-100, reasons list, indicator dict)."""
    close, volume = df["Close"], df["Volume"]
    last = float(close.iloc[-1])
    pts, max_pts, reasons = 0, 0, []

    # RSI (0-20 pts): healthy 45-65 is best, oversold gets some credit, overbought none
    r = float(rsi(close).iloc[-1])
    max_pts += 20
    if 45 <= r <= 65:
        pts += 20; reasons.append(f"RSI healthy at {r:.0f}")
    elif 30 <= r < 45:
        pts += 12; reasons.append(f"RSI {r:.0f} — cooling off, room to run")
    elif r < 30:
        pts += 8; reasons.append(f"RSI {r:.0f} — oversold")
    elif 65 < r <= 75:
        pts += 8; reasons.append(f"RSI {r:.0f} — getting hot")
    else:
        reasons.append(f"RSI {r:.0f} — overbought")

    # Moving averages (0-25 pts)
    sma50 = float(close.rolling(50).mean().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1])
    max_pts += 25
    if last > sma50 > sma200:
        pts += 25; reasons.append("Uptrend: price > 50-DMA > 200-DMA")
    elif last > sma200:
        pts += 15; reasons.append("Above 200-DMA")
    elif last > sma50:
        pts += 8; reasons.append("Above 50-DMA but below 200-DMA")
    else:
        reasons.append("Below both 50-DMA and 200-DMA — downtrend")

    # MACD histogram (0-15 pts): positive and rising is bullish
    hist = macd_histogram(close)
    h_now, h_prev = float(hist.iloc[-1]), float(hist.iloc[-5])
    max_pts += 15
    if h_now > 0 and h_now > h_prev:
        pts += 15; reasons.append("MACD positive and strengthening")
    elif h_now > 0:
        pts += 10; reasons.append("MACD positive")
    elif h_now > h_prev:
        pts += 6; reasons.append("MACD negative but improving")
    else:
        reasons.append("MACD negative and weakening")

    # Momentum (0-25 pts): 1m and 3m returns
    ret_1m = float(close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 21 else 0
    ret_3m = float(close.iloc[-1] / close.iloc[-63] - 1) * 100 if len(close) > 63 else 0
    max_pts += 25
    mom = 0
    if ret_3m > 10: mom += 13
    elif ret_3m > 0: mom += 8
    if ret_1m > 5: mom += 12
    elif ret_1m > 0: mom += 7
    pts += mom
    if mom >= 20:
        reasons.append(f"Strong momentum: +{ret_1m:.0f}% (1m), +{ret_3m:.0f}% (3m)")
    elif mom == 0 and ret_3m < -10:
        reasons.append(f"Weak momentum: {ret_3m:.0f}% over 3 months")

    # Volume trend (0-15 pts): recent volume vs 3-month average
    vol_20 = float(volume.tail(20).mean())
    vol_60 = float(volume.tail(60).mean())
    max_pts += 15
    if vol_60 > 0:
        ratio = vol_20 / vol_60
        if ratio > 1.2 and ret_1m > 0:
            pts += 15; reasons.append("Rising volume backing the move")
        elif ratio > 0.9:
            pts += 9
        else:
            pts += 4; reasons.append("Volume drying up")

    final = round(pts / max_pts * 100)
    indicators = {"rsi": round(r, 1), "sma50": round(sma50, 2), "sma200": round(sma200, 2),
                  "macd_hist": round(h_now, 3)}
    return final, reasons, indicators


def run(histories):
    print(f"  [stage4] scoring technicals for {len(histories)} stocks")
    out = {}
    for t, df in histories.items():
        try:
            s, reasons, ind = score(df)
            out[t] = {"score": s, "reasons": reasons, "indicators": ind}
        except Exception as e:
            print(f"  [stage4] {t}: {e}")
    return out
