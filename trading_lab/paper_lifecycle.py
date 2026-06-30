from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from trading_lab.journal_store import JournalStore

ET = ZoneInfo("America/New_York")


def update_paper_positions(
    store: JournalStore,
    bars: list[dict[str, Any]],
    *,
    expire_after_minutes: int = 120,
    now: datetime | None = None,
    no_new_entries_after: str | None = None,
    flatten_at: str | None = None,
) -> dict[str, Any]:
    """Advance simulated paper positions using OHLCV bars.

    This never places broker orders. It is a deterministic paper fill/exit engine:
    - pending long enters if high >= entry; short enters if low <= entry
    - open long exits at stop/target; short exits at stop/target
    - if both stop and target occur in the same bar, stop wins. Conservative goblin.
    """
    by_symbol = _bars_by_symbol(bars)
    events: list[dict[str, Any]] = []
    active = store.list_active_paper_positions()
    now = now or datetime.now(ET)
    cutoff_time = _parse_clock(no_new_entries_after)
    flatten_time = _parse_clock(flatten_at)

    for pos in active:
        symbol_bars = by_symbol.get(str(pos["ticker"]).upper(), [])
        if not symbol_bars:
            continue
        status = pos["status"]
        position_id = int(pos["id"])
        direction = str(pos["direction"])
        entry = float(pos["entry"])
        stop = float(pos["stop"])
        target = float(pos["target"])
        created_at = _parse_dt(str(pos["created_at"]))

        entered_at = _parse_dt(str(pos["entered_at"])) if pos.get("entered_at") else None
        if status == "pending_entry" and cutoff_time is not None and now.time() >= cutoff_time:
            store.expire_position(position_id, closed_at=now.isoformat(timespec="seconds"), reason="no_new_entries_after_cutoff")
            events.append({"type": "expired_cutoff", "position_id": position_id, "ticker": pos["ticker"]})
            continue
        for bar in symbol_bars:
            ts = str(bar["timestamp"])
            bar_dt = _parse_dt(ts)
            if created_at is not None and bar_dt is not None and bar_dt < created_at:
                continue
            if entered_at is not None and bar_dt is not None and bar_dt < entered_at:
                continue
            high = float(bar["high"])
            low = float(bar["low"])
            close = float(bar["close"])

            if status == "pending_entry":
                entered = (direction == "long" and high >= entry) or (direction == "short" and low <= entry)
                if not entered:
                    continue
                store.mark_position_open(position_id, entered_at=ts)
                status = "open"
                events.append({"type": "entered", "position_id": position_id, "ticker": pos["ticker"], "price": entry, "timestamp": ts})

            if status == "open":
                exit_reason = None
                exit_price = None
                if direction == "long":
                    if low <= stop:
                        exit_reason = "stop"
                        exit_price = stop
                    elif high >= target:
                        exit_reason = "target"
                        exit_price = target
                else:
                    if high >= stop:
                        exit_reason = "stop"
                        exit_price = stop
                    elif low <= target:
                        exit_reason = "target"
                        exit_price = target
                if exit_reason and exit_price is not None:
                    trade_id = store.close_position(position_id, closed_at=ts, exit_price=exit_price, exit_reason=exit_reason)
                    events.append({
                        "type": "closed",
                        "position_id": position_id,
                        "trade_id": trade_id,
                        "ticker": pos["ticker"],
                        "price": exit_price,
                        "reason": exit_reason,
                        "timestamp": ts,
                    })
                    break

        if status == "pending_entry" and created_at is not None and (now - created_at).total_seconds() >= expire_after_minutes * 60:
            store.expire_position(position_id, closed_at=now.isoformat(timespec="seconds"), reason="expired_without_entry")
            events.append({"type": "expired", "position_id": position_id, "ticker": pos["ticker"]})
        elif status == "open" and flatten_time is not None and now.time() >= flatten_time:
            last_bar = symbol_bars[-1]
            trade_id = store.close_position(
                position_id,
                closed_at=now.isoformat(timespec="seconds"),
                exit_price=float(last_bar["close"]),
                exit_reason="eod_flatten",
            )
            events.append({
                "type": "flattened_eod",
                "position_id": position_id,
                "trade_id": trade_id,
                "ticker": pos["ticker"],
                "price": float(last_bar["close"]),
            })

    return {"events": events, "event_count": len(events), "active_positions": len(store.list_active_paper_positions())}


def market_is_open(now: datetime | None = None) -> bool:
    now = now or datetime.now(ET)
    if now.weekday() >= 5:
        return False
    current = now.time()
    return time(9, 35) <= current <= time(15, 55)


def _bars_by_symbol(bars: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bar in bars:
        grouped[str(bar["symbol"]).upper()].append(bar)
    return {symbol: sorted(items, key=lambda item: item["timestamp"]) for symbol, items in grouped.items()}


def _parse_dt(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ET)
    return parsed.astimezone(ET)


def _parse_clock(value: str | None) -> time | None:
    if not value:
        return None
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))
