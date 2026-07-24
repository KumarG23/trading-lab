from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from trading_lab.fill_engine import apply_slippage, round_trip_fees, simulate_position
from trading_lab.journal_store import JournalStore

ET = ZoneInfo("America/New_York")


def completed_bar_end(now: datetime) -> datetime:
    """Latest timestamp guaranteed not to include the current partial minute."""
    return now.replace(second=0, microsecond=0) - timedelta(seconds=1)


def update_paper_positions(
    store: JournalStore,
    bars: list[dict[str, Any]],
    *,
    expire_after_minutes: int = 120,
    now: datetime | None = None,
    no_new_entries_after: str | None = None,
    flatten_at: str | None = None,
    entry_slippage_bps: float = 0.0,
    exit_slippage_bps: float = 0.0,
    fee_per_share: float = 0.0,
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
        signal_at = str(pos.get("entered_at") or pos["created_at"])
        candidate = {
            "ticker": pos["ticker"], "direction": direction, "planned_entry": entry,
            "stop": stop, "target": target, "risk_dollars": pos["risk_dollars"],
            "market_context": {"signal_timestamp": signal_at},
        }
        outcome = simulate_position(
            candidate,
            symbol_bars,
            position_size=float(pos["position_size"]),
            entry_slippage_bps=entry_slippage_bps if status == "pending_entry" else 0.0,
            exit_slippage_bps=exit_slippage_bps,
            fee_per_share=fee_per_share,
            flatten_unresolved=False,
            initial_entry=entry if status == "open" else None,
            initial_entered_at=str(pos.get("entered_at") or pos["created_at"]) if status == "open" else None,
        )
        if status == "pending_entry" and outcome["fill_status"] == "filled":
            entry = float(outcome["actual_entry"])
            entered_at = str(outcome["entered_at"])
            store.mark_position_open(position_id, entered_at=entered_at, entry_price=entry)
            status = "open"
            events.append({"type": "entered", "position_id": position_id, "ticker": pos["ticker"], "price": entry, "timestamp": entered_at})
        if status == "open" and outcome["status"] == "closed":
            trade_id = store.close_position(
                position_id,
                closed_at=str(outcome["closed_at"]),
                exit_price=float(outcome["actual_exit"]),
                exit_reason=str(outcome["exit_reason"]),
                fees=float(outcome["fees"]),
            )
            events.append({
                "type": "closed", "position_id": position_id, "trade_id": trade_id,
                "ticker": pos["ticker"], "price": outcome["actual_exit"],
                "reason": outcome["exit_reason"], "timestamp": outcome["closed_at"],
            })
            status = "closed"

        if status == "pending_entry" and created_at is not None and (now - created_at).total_seconds() >= expire_after_minutes * 60:
            store.expire_position(position_id, closed_at=now.isoformat(timespec="seconds"), reason="expired_without_entry")
            events.append({"type": "expired", "position_id": position_id, "ticker": pos["ticker"]})
        elif status == "open" and flatten_time is not None and now.time() >= flatten_time:
            flatten_price = apply_slippage(
                float(symbol_bars[-1]["close"]), direction=direction, kind="exit",
                bps=exit_slippage_bps,
            )
            trade_id = store.close_position(
                position_id,
                closed_at=now.isoformat(timespec="seconds"),
                exit_price=flatten_price,
                exit_reason="eod_flatten",
                fees=round_trip_fees(float(pos["position_size"]), fee_per_share=fee_per_share),
            )
            events.append({
                "type": "flattened_eod",
                "position_id": position_id,
                "trade_id": trade_id,
                "ticker": pos["ticker"],
                "price": round(flatten_price, 4),
            })

    return {"events": events, "event_count": len(events), "active_positions": len(store.list_active_paper_positions())}


def entry_window_open(now: datetime, no_new_entries_after: str | None) -> bool:
    cutoff = _parse_clock(no_new_entries_after)
    return cutoff is None or now.astimezone(ET).time() < cutoff


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
