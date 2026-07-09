import sqlite3

from trading_lab.journal_store import JournalStore, init_db


def test_init_db_creates_proposal_trade_review_and_model_usage_tables(tmp_path):
    db_path = tmp_path / "lab.db"

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"proposals", "paper_trades", "reviews", "model_usage"}.issubset(tables)


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
