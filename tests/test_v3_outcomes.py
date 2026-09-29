"""V3 offline resolver: no-fill, gaps, chronology, and costs before any paper orders."""
from datetime import datetime, timedelta, timezone

import pytest

from trading_lab.v3_outcomes import resolve_outcome

UTC = timezone.utc
START = datetime(2026, 9, 29, 16, 56, tzinfo=UTC)


def candidate():
    return {"event_id": "event-1", "symbol": "CCL", "decision_at": "2026-09-29T16:55:01Z",
            "entry_deadline_at": "2026-09-29T16:57:00Z", "planned_entry": 25.0,
            "stop": 24.8, "target": 25.4, "shares": 7}


def bar(n, *, opening=24.9, high=24.95, low=24.85, close=24.9):
    return {"symbol": "CCL", "feed": "iex", "timestamp": (START + timedelta(minutes=n)).isoformat(),
            "open": opening, "high": high, "low": low, "close": close, "volume": 100}


def resolve(bars, *, at="2026-09-29T17:00:00Z", plan=None):
    return resolve_outcome(plan or candidate(), bars, as_of=at)


def test_no_fill_at_deadline_is_not_loss():
    result = resolve([bar(0), bar(1)])
    assert result["status"] == "no_fill"
    assert result["net_dollars"] == 0
    assert result["execution_eligible"] is False


def test_gap_entry_and_gap_stop_are_adverse_and_after_cost():
    plan = candidate() | {"shares": 6}
    result = resolve([bar(0, opening=25.1, high=25.2, low=25.02, close=25.1),
                      bar(1, opening=24.7, high=24.75, low=24.6, close=24.7)], plan=plan)
    assert result["status"] == "resolved"
    assert result["exit_reason"] == "stop"
    assert result["actual_entry"] > 25.1  # adverse entry slippage
    assert result["actual_exit"] < 24.7  # adverse exit slippage
    assert result["net_dollars"] < 0
    assert result["fees"] > 0


def test_same_bar_stop_wins_and_never_uses_signal_bar():
    result = resolve([bar(-1, opening=25.0, high=26, low=24, close=25),
                      bar(0, opening=24.9, high=25.5, low=24.7, close=25)])
    assert result["status"] == "resolved" and result["exit_reason"] == "stop"
    assert result["entered_at"] == START.isoformat()


def test_favorable_target_gap_is_capped_to_target_after_slippage():
    result = resolve([bar(0, opening=25, high=25.1, low=24.9, close=25),
                      bar(1, opening=25.6, high=25.7, low=25.55, close=25.6)])
    assert result["status"] == "resolved" and result["exit_reason"] == "target"
    assert result["actual_exit"] < 25.4


def test_missing_minute_fails_closed_without_pnl():
    result = resolve([bar(0, opening=25, high=25.05, low=24.9), bar(2, low=24.7)])
    assert result["status"] == "data_gap"
    assert "net_dollars" not in result


def test_incomplete_day_stays_pending_and_future_bars_are_ignored():
    result = resolve([bar(0, opening=25, high=25.05, low=24.9),
                      bar(1, opening=24.9, high=24.95, low=24.85),
                      bar(2, opening=24.7, high=24.75, low=24.6)], at="2026-09-29T16:58:00Z")
    assert result["status"] == "pending" and "net_dollars" not in result


def test_rejects_unproven_feed_and_gap_through_target_cannot_fill():
    with pytest.raises(ValueError, match="provenance"):
        resolve([bar(0) | {"feed": "sip"}])
    result = resolve([bar(0, opening=25.5, high=25.6, low=25.45, close=25.5),
                      bar(1, opening=24.9, high=24.95, low=24.85, close=24.9)])
    assert result["status"] == "no_fill"


def test_invalid_risk_and_non_session_are_rejected():
    bad = candidate() | {"stop": 25.0}
    with pytest.raises(ValueError, match="plan"):
        resolve([], plan=bad)
    bad = candidate() | {"shares": 9}
    with pytest.raises(ValueError, match="plan"):
        resolve([], plan=bad)
    bad = candidate() | {"decision_at": "2026-09-26T16:55:01Z"}
    with pytest.raises(ValueError, match="session"):
        resolve([], plan=bad)
