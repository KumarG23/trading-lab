from trading_lab.counterfactual import resolve_candidate_events
from trading_lab.journal_store import JournalStore


def _candidate(ticker="AAPL"):
    return {
        "ticker": ticker,
        "strategy_id": "orb",
        "direction": "long",
        "planned_entry": 101.0,
        "stop": 100.0,
        "target": 103.0,
        "risk_dollars": 1.0,
        "market_context": {"signal_timestamp": "2026-07-20T13:35:00Z"},
    }


def test_resolves_every_disposition_with_one_shared_counterfactual(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    for disposition in ("admitted_portfolio", "slot_blocked", "duplicate", "policy_rejected"):
        store.log_candidate_event(_candidate(), disposition=disposition)
    bars = [
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:36:00Z", "open": 101, "high": 101.5, "low": 100.5, "close": 101.2, "volume": 1000},
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:37:00Z", "open": 101.2, "high": 103.5, "low": 101.1, "close": 103.1, "volume": 1000},
    ]

    result = resolve_candidate_events(store, bars, session_complete=True)

    assert result == {"examined": 4, "resolved": 4, "still_open": 0, "data_invalid": 0}
    assert [row["fill_status"] for row in store.list_candidate_outcomes()] == ["filled"] * 4
    assert {row["net_r"] for row in store.list_candidate_outcomes()} == {2.0}


def test_invalid_candidate_gets_auditable_data_quality_outcome(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    store.log_candidate_event(
        {"ticker": "BAD", "strategy_id": "orb", "direction": "long"},
        disposition="policy_rejected",
    )

    result = resolve_candidate_events(store, [], session_complete=True)

    assert result["data_invalid"] == 1
    outcome = store.list_candidate_outcomes()[0]
    assert outcome["fill_status"] == "data_invalid"
    assert outcome["data_quality_flags"] == ["missing:planned_entry,risk_dollars,stop,target"]


def test_intraday_unresolved_candidate_is_not_prematurely_flattened(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    store.log_candidate_event(_candidate(), disposition="slot_blocked")
    bars = [
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:36:00Z", "open": 101, "high": 101.5, "low": 100.5, "close": 101.2, "volume": 1000},
    ]

    result = resolve_candidate_events(store, bars, session_complete=False)

    assert result["still_open"] == 1
    assert store.list_candidate_outcomes() == []


def test_completed_live_session_does_not_expire_candidates_from_an_absent_session(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    store.log_candidate_event(_candidate(), disposition="slot_blocked")
    later_bars = [
        {"symbol": "AAPL", "timestamp": "2026-07-21T19:44:00Z", "open": 101, "high": 102, "low": 100, "close": 101, "volume": 1000},
    ]

    result = resolve_candidate_events(store, later_bars, session_complete=True)

    assert result["resolved"] == 0
    assert result["still_open"] == 1
    assert store.list_candidate_outcomes() == []
