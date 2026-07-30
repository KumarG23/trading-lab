from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any


STRATEGY_ID = "opening-range-breakout"


def generate_orb_candidates(
    bars: list[dict[str, Any]],
    *,
    opening_range_minutes: int = 5,
    risk_dollars: float = 10.0,
    volume_confirmation_multiple: float = 1.5,
    max_candidates_per_symbol: int = 1,
    latest_only: bool = False,
) -> list[dict[str, Any]]:
    """Generate first valid ORB candidate per symbol from intraday 1-minute bars.

    The old version only inspected the first bar after the opening range. That was
    too brittle for a loop that runs every few minutes. This scans the post-range
    session and emits the first confirmed break only. Duplicate suppression is
    handled at the journal layer.
    """
    candidates: list[dict[str, Any]] = []
    for symbol, symbol_bars in _group_by_symbol(bars).items():
        emitted = 0
        ordered = sorted(symbol_bars, key=lambda item: item["timestamp"])
        if len(ordered) <= opening_range_minutes:
            continue
        opening_range = ordered[:opening_range_minutes]
        range_high = max(float(bar["high"]) for bar in opening_range)
        range_low = min(float(bar["low"]) for bar in opening_range)
        avg_volume = mean(float(bar["volume"]) for bar in opening_range)
        if avg_volume <= 0:
            continue
        breakout_bars = ordered[-1:] if latest_only else ordered[opening_range_minutes:]
        for breakout_bar in breakout_bars:
            close = float(breakout_bar["close"])
            volume = float(breakout_bar["volume"])
            if volume < avg_volume * volume_confirmation_multiple:
                continue
            if close > range_high:
                risk_per_share = close - range_high
                if risk_per_share <= 0:
                    continue
                candidates.append(
                    _candidate(
                        symbol=symbol,
                        direction="long",
                        entry=close,
                        stop=range_high,
                        target=close + (2 * risk_per_share),
                        risk_dollars=risk_dollars,
                        trigger=f"Close {close:.2f} broke {opening_range_minutes}m opening range high {range_high:.2f} on {volume / avg_volume:.2f}x volume",
                        timestamp=breakout_bar["timestamp"],
                        range_high=range_high,
                        range_low=range_low,
                        volume_ratio=volume / avg_volume,
                    )
                )
                emitted += 1
            elif close < range_low:
                risk_per_share = range_low - close
                if risk_per_share <= 0:
                    continue
                candidates.append(
                    _candidate(
                        symbol=symbol,
                        direction="short",
                        entry=close,
                        stop=range_low,
                        target=close - (2 * risk_per_share),
                        risk_dollars=risk_dollars,
                        trigger=f"Close {close:.2f} broke {opening_range_minutes}m opening range low {range_low:.2f} on {volume / avg_volume:.2f}x volume",
                        timestamp=breakout_bar["timestamp"],
                        range_high=range_high,
                        range_low=range_low,
                        volume_ratio=volume / avg_volume,
                    )
                )
                emitted += 1
            if emitted >= max_candidates_per_symbol:
                break
    return candidates


def _candidate(
    *,
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    target: float,
    risk_dollars: float,
    trigger: str,
    timestamp: str,
    range_high: float,
    range_low: float,
    volume_ratio: float,
) -> dict[str, Any]:
    return {
        "ticker": symbol,
        "asset_class": "stock",
        "direction": direction,
        "strategy_id": STRATEGY_ID,
        "trigger": trigger,
        "planned_entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "risk_dollars": risk_dollars,
        "data_sources": ["alpaca-market-data"],
        "rule_checklist": {
            "opening_range_break": True,
            "volume_confirmed": True,
            "paper_only": True,
        },
        "market_context": {
            "signal_timestamp": timestamp,
            "opening_range_high": round(range_high, 4),
            "opening_range_low": round(range_low, 4),
            "volume_ratio": round(volume_ratio, 4),
        },
    }


def _group_by_symbol(bars: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bar in bars:
        grouped[str(bar["symbol"]).upper()].append(bar)
    return grouped
