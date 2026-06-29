from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _value(item: Any, key: str) -> float:
    if isinstance(item, Mapping):
        return float(item[key])
    return float(getattr(item, key))


def _close_series(values: Iterable[Any]) -> list[float]:
    result = []
    for item in values:
        if isinstance(item, Mapping) and "close" in item:
            result.append(float(item["close"]))
        else:
            result.append(float(item))
    return result


def ema(values: Iterable[Any], period: int) -> float | None:
    closes = _close_series(values)
    if period <= 0 or len(closes) < period:
        return None
    multiplier = 2 / (period + 1)
    current = closes[0]
    for close in closes[1:]:
        current = (close - current) * multiplier + current
    return round(current, 4)


def rsi(values: Iterable[Any], period: int = 14) -> float | None:
    closes = _close_series(values)
    if period <= 0 or len(closes) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(closes[-period - 1 : -1], closes[-period:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 4)


def vwap(bars: Iterable[Any]) -> float | None:
    total_price_volume = 0.0
    total_volume = 0.0
    for bar in bars:
        high = _value(bar, "high")
        low = _value(bar, "low")
        close = _value(bar, "close")
        volume = _value(bar, "volume")
        typical = (high + low + close) / 3
        total_price_volume += typical * volume
        total_volume += volume
    if total_volume == 0:
        return None
    return round(total_price_volume / total_volume, 4)


def volume_profile(bars: Iterable[Any], lookback: int = 20) -> dict[str, float | str] | None:
    rows = list(bars)
    if lookback <= 0 or not rows:
        return None
    window = rows[-lookback:]
    volumes = [_value(row, "volume") for row in window]
    current = volumes[-1]
    avg = sum(volumes) / len(volumes)
    ratio = current / avg if avg else 0.0
    if ratio >= 1.5:
        trend = "above_average"
    elif ratio <= 0.7:
        trend = "below_average"
    else:
        trend = "normal"
    return {
        "current_volume": int(current) if current.is_integer() else round(current, 4),
        "avg_volume": round(avg, 4),
        "volume_ratio": round(ratio, 4),
        "trend": trend,
    }
