from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

STRATEGY_ID = "vwap-reclaim"


def generate_vwap_reclaim_candidates(
    bars: list[dict[str, Any]],
    *,
    symbols: list[str] | None = None,
    risk_dollars: float = 2.0,
    min_bars: int = 6,
    volume_lookback: int = 5,
    volume_confirmation_multiple: float = 1.2,
    target_r_multiple: float = 2.0,
) -> list[dict[str, Any]]:
    """Generate long-only VWAP reclaim candidates from the latest completed bar."""
    allowed = {symbol.upper() for symbol in symbols} if symbols is not None else None
    candidates: list[dict[str, Any]] = []
    for symbol, symbol_bars in _group_by_symbol(bars).items():
        if allowed is not None and symbol not in allowed:
            continue
        ordered = sorted(symbol_bars, key=lambda item: item["timestamp"])
        if len(ordered) < max(min_bars, volume_lookback + 1):
            continue
        vwaps = _vwap_series(ordered)
        previous = ordered[-2]
        current = ordered[-1]
        previous_close = float(previous["close"])
        current_close = float(current["close"])
        current_open = float(current["open"])
        previous_vwap = vwaps[-2]
        current_vwap = vwaps[-1]
        average_volume = mean(float(bar["volume"]) for bar in ordered[-volume_lookback - 1 : -1])
        current_volume = float(current["volume"])
        if average_volume <= 0:
            continue
        volume_ratio = current_volume / average_volume
        if previous_close > previous_vwap:
            continue
        if current_close <= current_vwap or current_close <= current_open:
            continue
        if volume_ratio < volume_confirmation_multiple:
            continue
        stop = min(float(previous["low"]), float(current["low"]))
        risk_per_share = current_close - stop
        if risk_per_share <= 0:
            continue
        target = current_close + risk_per_share * target_r_multiple
        candidates.append(
            {
                "ticker": symbol,
                "asset_class": "etf" if symbol in {"SPY", "QQQ"} else "stock",
                "direction": "long",
                "strategy_id": STRATEGY_ID,
                "trigger": f"Close {current_close:.2f} reclaimed VWAP {current_vwap:.2f} on {volume_ratio:.2f}x volume",
                "planned_entry": round(current_close, 4),
                "stop": round(stop, 4),
                "target": round(target, 4),
                "risk_dollars": risk_dollars,
                "data_sources": ["alpaca-market-data"],
                "rule_checklist": {
                    "vwap_reclaimed": True,
                    "bullish_close": True,
                    "volume_confirmed": True,
                    "long_only": True,
                    "paper_only": True,
                },
                "market_context": {
                    "signal_timestamp": current["timestamp"],
                    "previous_vwap": round(previous_vwap, 4),
                    "vwap": round(current_vwap, 4),
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
    price_volume = 0.0
    volume_total = 0.0
    values: list[float] = []
    for bar in bars:
        typical = (float(bar["high"]) + float(bar["low"]) + float(bar["close"])) / 3
        volume = float(bar["volume"])
        price_volume += typical * volume
        volume_total += volume
        values.append(price_volume / volume_total if volume_total else typical)
    return values
