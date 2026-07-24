from __future__ import annotations

from datetime import datetime, timezone
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
    *, planned_entry: float, direction: str, bar: dict[str, Any], slippage_bps: float = 0.0,
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


def simulate_position(
    candidate: dict[str, Any],
    bars: list[dict[str, Any]],
    *,
    position_size: float,
    entry_slippage_bps: float = 0.0,
    exit_slippage_bps: float = 0.0,
    fee_per_share: float = 0.0,
    flatten_unresolved: bool = True,
    initial_entry: float | None = None,
    initial_entered_at: str | None = None,
) -> dict[str, Any]:
    """Resolve one candidate with the shared, deterministic OHLC lifecycle."""
    symbol = str(candidate["ticker"]).upper()
    direction = str(candidate["direction"])
    signal_at = str((candidate.get("market_context") or {}).get("signal_timestamp") or "")
    signal_instant = _timestamp(signal_at) if signal_at else None
    planned_entry = float(candidate["planned_entry"])
    stop = float(candidate["stop"])
    target = float(candidate["target"])
    risk_dollars = float(candidate.get("risk_dollars") or 0.0)
    relevant = sorted(
        (
            bar for bar in bars
            if str(bar.get("symbol", symbol)).upper() == symbol
            and (signal_instant is None or _timestamp(str(bar["timestamp"])) > signal_instant)
        ),
        key=lambda bar: _timestamp(str(bar["timestamp"])),
    )
    entry = initial_entry
    entered_at = initial_entered_at
    entry_slippage_dollars = 0.0
    data_quality_flags: list[str] = []
    observed: list[dict[str, Any]] = []
    for bar in relevant:
        entered_this_bar = False
        if entry is None:
            clean_entry = entry_fill_price(
                planned_entry=planned_entry, direction=direction, bar=bar, slippage_bps=0.0,
            )
            entry = entry_fill_price(
                planned_entry=planned_entry,
                direction=direction,
                bar=bar,
                slippage_bps=entry_slippage_bps,
            )
            if entry is None or clean_entry is None:
                continue
            entered_at = str(bar["timestamp"])
            entered_this_bar = True
            data_quality_flags.append("entry_bar_path_unknown")
            entry_slippage_dollars = round(abs(entry - clean_entry) * position_size, 4)
        observed.append(bar)
        resolved = exit_fill(
            stop=stop,
            target=target,
            direction=direction,
            bar=bar,
            slippage_bps=exit_slippage_bps,
            allow_open_gap=not entered_this_bar,
        )
        if resolved is not None:
            reason, exit_price = resolved
            clean_exit = exit_fill(
                stop=stop,
                target=target,
                direction=direction,
                bar=bar,
                slippage_bps=0.0,
                allow_open_gap=not entered_this_bar,
            )
            assert clean_exit is not None
            return _outcome(
                entry=entry,
                exit_price=exit_price,
                direction=direction,
                position_size=position_size,
                risk_dollars=risk_dollars,
                entered_at=entered_at,
                closed_at=str(bar["timestamp"]),
                exit_reason=reason,
                fees=round_trip_fees(position_size, fee_per_share=fee_per_share),
                same_bar_ambiguity=_both_stop_and_target(bar, stop, target),
                entry_slippage_dollars=entry_slippage_dollars,
                exit_slippage_dollars=round(abs(exit_price - float(clean_exit[1])) * position_size, 4),
                observed_bars=observed,
                data_quality_flags=data_quality_flags,
            )
    if entry is not None and not flatten_unresolved:
        return {
            "status": "open",
            "fill_status": "filled",
            "entered_at": entered_at,
            "closed_at": None,
            "actual_entry": round(entry, 4),
            "actual_exit": None,
            "exit_reason": None,
            "fees": 0.0,
            "net_dollars": 0.0,
            "net_r": 0.0,
            "same_bar_ambiguity": False,
            "entry_slippage_dollars": entry_slippage_dollars,
            "exit_slippage_dollars": 0.0,
            **_analytics(entry, observed, direction, position_size, risk_dollars, entered_at, None),
            "data_quality_flags": data_quality_flags,
        }
    if entry is not None and relevant:
        last = relevant[-1]
        clean_exit = float(last["close"])
        exit_price = apply_slippage(clean_exit, direction=direction, kind="exit", bps=exit_slippage_bps)
        return _outcome(
            entry=entry,
            exit_price=exit_price,
            direction=direction,
            position_size=position_size,
            risk_dollars=risk_dollars,
            entered_at=entered_at,
            closed_at=str(last["timestamp"]),
            exit_reason="eod_flatten",
            fees=round_trip_fees(position_size, fee_per_share=fee_per_share),
            same_bar_ambiguity=False,
            entry_slippage_dollars=entry_slippage_dollars,
            exit_slippage_dollars=round(abs(exit_price - clean_exit) * position_size, 4),
            observed_bars=observed,
            data_quality_flags=data_quality_flags,
        )
    return {
        "status": "expired",
        "fill_status": "no_fill",
        "entered_at": None,
        "closed_at": str(relevant[-1]["timestamp"]) if relevant else signal_at or None,
        "actual_entry": None,
        "actual_exit": None,
        "exit_reason": "expired_without_entry",
        "fees": 0.0,
        "net_dollars": 0.0,
        "net_r": 0.0,
        "same_bar_ambiguity": False,
        "entry_slippage_dollars": 0.0,
        "exit_slippage_dollars": 0.0,
        "mfe_dollars": 0.0,
        "mae_dollars": 0.0,
        "mfe_r": 0.0,
        "mae_r": 0.0,
        "duration_seconds": 0,
        "data_quality_flags": [],
    }


def _both_stop_and_target(bar: dict[str, Any], stop: float, target: float) -> bool:
    return float(bar["low"]) <= min(stop, target) and float(bar["high"]) >= max(stop, target)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"market timestamp must be timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def _outcome(
    *,
    entry: float,
    exit_price: float,
    direction: str,
    position_size: float,
    risk_dollars: float,
    entered_at: str | None,
    closed_at: str,
    exit_reason: str,
    fees: float,
    same_bar_ambiguity: bool,
    entry_slippage_dollars: float,
    exit_slippage_dollars: float,
    observed_bars: list[dict[str, Any]],
    data_quality_flags: list[str],
) -> dict[str, Any]:
    gross = (exit_price - entry) * position_size if direction == "long" else (entry - exit_price) * position_size
    net = round(gross - fees, 4)
    return {
        "status": "closed",
        "fill_status": "filled",
        "entered_at": entered_at,
        "closed_at": closed_at,
        "actual_entry": round(entry, 4),
        "actual_exit": round(exit_price, 4),
        "exit_reason": exit_reason,
        "fees": round(fees, 4),
        "net_dollars": net,
        "net_r": round(net / risk_dollars, 4) if risk_dollars else 0.0,
        "same_bar_ambiguity": same_bar_ambiguity,
        "entry_slippage_dollars": entry_slippage_dollars,
        "exit_slippage_dollars": exit_slippage_dollars,
        **_analytics(entry, observed_bars, direction, position_size, risk_dollars, entered_at, closed_at),
        "data_quality_flags": sorted(set(
            data_quality_flags + (["same_bar_stop_target"] if same_bar_ambiguity else [])
        )),
    }


def _analytics(
    entry: float,
    bars: list[dict[str, Any]],
    direction: str,
    position_size: float,
    risk_dollars: float,
    entered_at: str | None,
    closed_at: str | None,
) -> dict[str, Any]:
    if not bars:
        mfe = mae = 0.0
    elif direction == "long":
        mfe = (max(float(bar["high"]) for bar in bars) - entry) * position_size
        mae = (min(float(bar["low"]) for bar in bars) - entry) * position_size
    else:
        mfe = (entry - min(float(bar["low"]) for bar in bars)) * position_size
        mae = (entry - max(float(bar["high"]) for bar in bars)) * position_size
    duration = 0
    if entered_at and closed_at:
        duration = max(0, int((_timestamp(closed_at) - _timestamp(entered_at)).total_seconds()))
    return {
        "mfe_dollars": round(max(0.0, mfe), 4),
        "mae_dollars": round(min(0.0, mae), 4),
        "mfe_r": round(max(0.0, mfe) / risk_dollars, 4) if risk_dollars else 0.0,
        "mae_r": round(min(0.0, mae) / risk_dollars, 4) if risk_dollars else 0.0,
        "duration_seconds": duration,
    }
