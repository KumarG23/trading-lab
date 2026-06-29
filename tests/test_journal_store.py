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
