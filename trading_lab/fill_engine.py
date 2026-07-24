from __future__ import annotations

from typing import Any


def apply_slippage(price: float, *, direction: str, kind: str, bps: float) -> float:
    """Apply adverse slippage to an entry or exit price."""
    if bps <= 0:
        return round(float(price), 4)
    rate = bps / 10_000.0
    if kind == "entry":
        filled = price * (1 + rate) if direction == "long" else price * (1 - rate)
        return round(filled, 4)
    if kind != "exit":
        raise ValueError(f"unknown fill kind: {kind}")
    filled = price * (1 - rate) if direction == "long" else price * (1 + rate)
    return round(filled, 4)


def entry_fill_price(
    *,
    planned_entry: float,
    direction: str,
    bar: dict[str, Any],
    slippage_bps: float = 0.0,
) -> float | None:
    """Return a gap-aware stop-entry fill, or None when the bar never triggers."""
    opening = float(bar["open"])
    high = float(bar["high"])
    low = float(bar["low"])
    if direction == "long":
        if high < planned_entry:
            return None
        base = max(planned_entry, opening)
    else:
        if low > planned_entry:
            return None
        base = min(planned_entry, opening)
    return apply_slippage(base, direction=direction, kind="entry", bps=slippage_bps)


def exit_fill(
    *,
    stop: float,
    target: float,
    direction: str,
    bar: dict[str, Any],
    slippage_bps: float = 0.0,
    allow_open_gap: bool = True,
) -> tuple[str, float] | None:
    """Return a conservative gap-aware exit; stop wins same-bar ambiguity."""
    opening = float(bar["open"])
    high = float(bar["high"])
    low = float(bar["low"])
    if direction == "long":
        if low <= stop:
            base = min(stop, opening) if allow_open_gap else stop
            return "stop", apply_slippage(base, direction=direction, kind="exit", bps=slippage_bps)
        if high >= target:
            base = max(target, opening)
            return "target", apply_slippage(base, direction=direction, kind="exit", bps=slippage_bps)
    else:
        if high >= stop:
            base = max(stop, opening) if allow_open_gap else stop
            return "stop", apply_slippage(base, direction=direction, kind="exit", bps=slippage_bps)
        if low <= target:
            base = min(target, opening)
            return "target", apply_slippage(base, direction=direction, kind="exit", bps=slippage_bps)
    return None


def round_trip_fees(position_size: float, *, fee_per_share: float) -> float:
    return round(max(0.0, float(position_size)) * max(0.0, fee_per_share) * 2, 4)
