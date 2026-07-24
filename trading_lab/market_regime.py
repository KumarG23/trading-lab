from __future__ import annotations

from typing import Any


def bullish_market_regime(bars: list[dict[str, Any]], *, symbol: str = "SPY", slope_lookback: int = 3) -> bool:
    market_bars = sorted(
        (bar for bar in bars if str(bar.get("symbol") or "").upper() == symbol.upper()),
        key=lambda bar: str(bar["timestamp"]),
    )
    if not market_bars:
        return True
    if len(market_bars) < slope_lookback:
        return True

    cumulative_value = 0.0
    cumulative_volume = 0.0
    vwaps: list[float] = []
    for bar in market_bars:
        volume = float(bar.get("volume") or 0)
        if volume <= 0:
            continue
        cumulative_value += float(bar["close"]) * volume
        cumulative_volume += volume
        vwaps.append(cumulative_value / cumulative_volume)
    if len(vwaps) < slope_lookback:
        return True

    latest_close = float(market_bars[-1]["close"])
    return latest_close > vwaps[-1] and vwaps[-1] > vwaps[-slope_lookback]


def market_regime_label(bars: list[dict[str, Any]], *, symbol: str = "SPY", slope_lookback: int = 3) -> str:
    market_bars = [bar for bar in bars if str(bar.get("symbol") or "").upper() == symbol.upper()]
    if len(market_bars) < slope_lookback:
        return "unknown"
    return "bullish" if bullish_market_regime(bars, symbol=symbol, slope_lookback=slope_lookback) else "not_bullish"
