import sqlite3

import pytest

import trading_lab.journal_store as journal_store
from trading_lab.journal_store import JournalStore, init_db


def test_init_db_creates_proposal_trade_review_and_model_usage_tables(tmp_path):
    db_path = tmp_path / "lab.db"

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"candidate_events", "proposals", "paper_trades", "reviews", "model_usage"}.issubset(tables)


def test_journal_store_logs_proposal_and_paper_trade_round_trip(tmp_path):
    store = JournalStore(tmp_path / "lab.db")

    proposal_id = store.log_proposal(
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="breaks 5m high",
        planned_entry=101.0,
        stop=100.0,
        target=103.0,
        thesis="volume-confirmed breakout",
        rule_checklist={"liquid": True, "stop_defined": True},
    )
    store.log_paper_trade(
        proposal_id=proposal_id,
        actual_entry=101.0,
        actual_exit=103.0,
        position_size=10,
        pnl=20.0,
        actual_r_multiple=2.0,
        rule_adherent=True,
        exit_reason="target hit",
    )

    proposals = store.list_proposals()
    trades = store.list_paper_trades()

    assert proposals[0]["ticker"] == "AAPL"
    assert proposals[0]["status"] == "proposed"
    assert proposals[0]["rule_checklist"]["stop_defined"] is True
    assert trades[0]["proposal_id"] == proposal_id
    assert trades[0]["actual_r_multiple"] == 2.0


def test_candidate_event_key_is_stable_for_non_json_edge_values(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    candidate = {1: "numeric key", "1": "string key", "ticker": "EDGE", "values": {3, 1, 2}, "score": float("nan")}

    store.log_candidate_event(candidate, disposition="policy_rejected")
    store.log_candidate_event(dict(reversed(list(candidate.items()))), disposition="policy_rejected")

    events = store.list_candidate_events()
    assert events[0]["candidate_key"] == events[1]["candidate_key"]
    assert events[0]["candidate"]["score"] == "<non-finite:nan>"


def test_atomic_proposal_candidate_event_insert_rolls_back_together(tmp_path, monkeypatch):
    store = JournalStore(tmp_path / "lab.db")

    def fail_event(*args, **kwargs):
        raise RuntimeError("simulated event write failure")

    monkeypatch.setattr(journal_store, "_insert_candidate_event", fail_event)
    with pytest.raises(RuntimeError, match="simulated event write failure"):
        store.log_proposal(
            ticker="AAPL",
            strategy_id="opening-range-breakout",
            direction="long",
            trigger="break",
            planned_entry=101,
            stop=100,
            target=103,
            thesis="atomic",
            candidate_event={"ticker": "AAPL"},
            candidate_disposition="admitted_portfolio",
        )

    assert store.list_proposals() == []
    assert store.list_candidate_events() == []


def test_journal_store_excludes_quarantined_rows_from_default_lists(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    good_id = store.log_proposal(
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="break",
        planned_entry=101.0,
        stop=100.0,
        target=103.0,
        thesis="ok",
    )
    bad_id = store.log_proposal(
        ticker="MSFT",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="duplicate",
        planned_entry=201.0,
        stop=200.0,
        target=203.0,
        thesis="duplicate",
        status="duplicate_quarantined",
    )
    store.log_paper_trade(proposal_id=good_id, actual_entry=101, actual_exit=103, position_size=1, pnl=2, actual_r_multiple=2, rule_adherent=True)
    store.log_paper_trade(
        proposal_id=bad_id,
        actual_entry=201,
        actual_exit=203,
        position_size=1,
        pnl=2,
        actual_r_multiple=2,
        rule_adherent=False,
        mistake_category="duplicate_overlap_quarantined",
    )

    assert [p["ticker"] for p in store.list_proposals()] == ["AAPL"]
    assert [t["proposal_id"] for t in store.list_paper_trades()] == [good_id]
    assert len(store.list_proposals(include_quarantined=True)) == 2
    assert len(store.list_paper_trades(include_quarantined=True)) == 2


def test_candidate_outcome_round_trip_is_one_per_immutable_event(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    event_id = store.log_candidate_event(
        {"ticker": "AAPL", "strategy_id": "orb", "direction": "long"},
        disposition="duplicate",
    )
    outcome = {
        "fill_status": "filled", "entered_at": "2026-07-20T13:36:00Z",
        "closed_at": "2026-07-20T13:37:00Z", "actual_entry": 101.1,
        "actual_exit": 102.9, "exit_reason": "target", "net_dollars": 1.7,
        "net_r": 0.85, "fees": 0.1, "entry_slippage_dollars": 0.05,
        "exit_slippage_dollars": 0.05, "mfe_dollars": 2.4, "mae_dollars": -0.6,
        "mfe_r": 1.2, "mae_r": -0.3, "duration_seconds": 60,
        "same_bar_ambiguity": False, "data_quality_flags": [],
    }

    outcome_id = store.log_candidate_outcome(event_id, outcome)
    second_id = store.log_candidate_outcome(event_id, outcome)

    assert second_id == outcome_id
    assert store.list_unresolved_candidate_events() == []
    stored = store.list_candidate_outcomes()[0]
    assert stored["candidate_event_id"] == event_id
    assert stored["net_dollars"] == 1.7
    assert stored["data_quality_flags"] == []
