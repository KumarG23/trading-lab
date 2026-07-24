from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from trading_lab.fill_engine import simulate_position
from trading_lab.journal_store import JournalStore

ET = ZoneInfo("America/New_York")
_REQUIRED = ("planned_entry", "risk_dollars", "stop", "target")


def resolve_candidate_events(
    store: JournalStore,
    bars: list[dict[str, Any]],
    *,
    session_complete: bool,
    entry_slippage_bps: float = 0.0,
    exit_slippage_bps: float = 0.0,
    fee_per_share: float = 0.0,
) -> dict[str, int]:
    """Resolve every unresolved candidate event without regard to disposition."""
    events = store.list_unresolved_candidate_events()
    counts = {"examined": len(events), "resolved": 0, "still_open": 0, "data_invalid": 0}
    for event in events:
        candidate = dict(event.get("candidate") or {})
        missing = [field for field in _REQUIRED if candidate.get(field) is None]
        if not candidate.get("ticker"):
            missing.append("ticker")
        if candidate.get("direction") not in {"long", "short"}:
            missing.append("direction")
        if missing:
            store.log_candidate_outcome(int(event["id"]), _invalid_outcome(missing))
            counts["resolved"] += 1
            counts["data_invalid"] += 1
            continue
        distance = abs(float(candidate["planned_entry"]) - float(candidate["stop"]))
        if distance <= 0 or float(candidate["risk_dollars"]) <= 0:
            store.log_candidate_outcome(int(event["id"]), _invalid_outcome(["nonpositive_risk_or_stop_distance"]))
            counts["resolved"] += 1
            counts["data_invalid"] += 1
            continue
        session_bars = _candidate_session_bars(candidate, bars)
        if not session_bars:
            counts["still_open"] += 1
            continue
        outcome = simulate_position(
            candidate,
            session_bars,
            position_size=float(candidate["risk_dollars"]) / distance,
            entry_slippage_bps=entry_slippage_bps,
            exit_slippage_bps=exit_slippage_bps,
            fee_per_share=fee_per_share,
            flatten_unresolved=session_complete,
        )
        if not session_complete and outcome["status"] in {"open", "expired"}:
            counts["still_open"] += 1
            continue
        store.log_candidate_outcome(int(event["id"]), outcome)
        counts["resolved"] += 1
    return counts


def _candidate_session_bars(candidate: dict[str, Any], bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signal = str((candidate.get("market_context") or {}).get("signal_timestamp") or "")
    if not signal:
        return bars
    signal_session = _parse_timestamp(signal).astimezone(ET).date()
    return [
        bar for bar in bars
        if _parse_timestamp(str(bar["timestamp"])).astimezone(ET).date() == signal_session
    ]


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware: {value}")
    return parsed


def _invalid_outcome(reasons: list[str]) -> dict[str, Any]:
    detail = ",".join(reasons)
    return {
        "fill_status": "data_invalid",
        "entered_at": None,
        "closed_at": None,
        "actual_entry": None,
        "actual_exit": None,
        "exit_reason": "data_invalid",
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
        "data_quality_flags": [f"missing:{detail}" if reasons and all(reason != "nonpositive_risk_or_stop_distance" for reason in reasons) else detail],
    }
