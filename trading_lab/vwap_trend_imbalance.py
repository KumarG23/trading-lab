from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

STRATEGY_ID = "vwap-trend-imbalance"


def generate_vwap_trend_candidates(
    bars: list[dict[str, Any]],
    *,
    symbols: list[str] | None = None,
    risk_dollars: float = 2.0,
    min_bars: int = 30,
    slope_lookback: int = 5,
    volume_lookback: int = 20,
    volume_confirmation_multiple: float = 1.5,
    min_distance_from_vwap_pct: float = 0.001,
    target_r_multiple: float = 2.0,
) -> list[dict[str, Any]]:
    """Generate long-only VWAP trend/imbalance candidates.

    This is intentionally narrow: SPY/QQQ-style ETF trend continuation in
    proposal mode. Shorts and leveraged ETFs can wait until the boring math has
    earned a chair at the table.
    """
    allowed = {symbol.upper() for symbol in (symbols or ["SPY", "QQQ"])}
    candidates: list[dict[str, Any]] = []

    for symbol, symbol_bars in _group_by_symbol(bars).items():
        if symbol not in allowed:
            continue
        ordered = sorted(symbol_bars, key=lambda item: item["timestamp"])
        if len(ordered) < max(min_bars, slope_lookback + 1, volume_lookback + 1):
            continue

        vwap_series = _vwap_series(ordered)
        current_bar = ordered[-1]
        current_vwap = vwap_series[-1]
        previous_vwap = vwap_series[-1 - slope_lookback]
        close = float(current_bar["close"])
        low = float(current_bar["low"])
        volume = float(current_bar["volume"])
        avg_volume = mean(float(bar["volume"]) for bar in ordered[-volume_lookback - 1 : -1])
        if avg_volume <= 0:
            continue
        volume_ratio = volume / avg_volume
        distance_from_vwap_pct = (close - current_vwap) / close if close else 0.0

        if current_vwap <= previous_vwap:
            continue
        if close <= current_vwap:
            continue
        if distance_from_vwap_pct < min_distance_from_vwap_pct:
            continue
        if volume_ratio < volume_confirmation_multiple:
            continue

        recent_lows = [float(bar["low"]) for bar in ordered[-slope_lookback:]]
        stop = min(current_vwap, min(recent_lows), low)
        risk_per_share = close - stop
        if risk_per_share <= 0:
            continue
        target = close + (risk_per_share * target_r_multiple)
        candidates.append(
            {
                "ticker": symbol,
                "asset_class": "etf" if symbol in {"SPY", "QQQ"} else "stock",
                "direction": "long",
                "strategy_id": STRATEGY_ID,
                "trigger": f"Close {close:.2f} held above rising VWAP {current_vwap:.2f} on {volume_ratio:.2f}x volume",
                "planned_entry": round(close, 4),
                "stop": round(stop, 4),
                "target": round(target, 4),
                "risk_dollars": risk_dollars,
                "data_sources": ["alpaca-market-data"],
                "rule_checklist": {
                    "vwap_trend_confirmed": True,
                    "vwap_slope_positive": True,
                    "volume_confirmed": True,
                    "paper_only": True,
                    "long_only_initial_variant": True,
                },
                "market_context": {
                    "signal_timestamp": current_bar["timestamp"],
                    "vwap": round(current_vwap, 4),
                    "previous_vwap": round(previous_vwap, 4),
                    "distance_from_vwap_pct": round(distance_from_vwap_pct, 6),
                    "volume_ratio": round(volume_ratio, 4),
                },
            }
        )
    return candidates


def _group_by_symbol(bars: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bar in bars:
        grouped[str(bar["symbol"]).upper()].append(bar)
    return grouped


def _vwap_series(bars: list[dict[str, Any]]) -> list[float]:
    total_price_volume = 0.0
    total_volume = 0.0
    values: list[float] = []
    for bar in bars:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        volume = float(bar["volume"])
        typical = (high + low + close) / 3
        total_price_volume += typical * volume
        total_volume += volume
        values.append(total_price_volume / total_volume if total_volume else typical)
    return values
