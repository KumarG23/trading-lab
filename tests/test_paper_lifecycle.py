from datetime import datetime
from zoneinfo import ZoneInfo

from trading_lab.journal_store import JournalStore
from trading_lab.paper_lifecycle import update_paper_positions

ET = ZoneInfo("America/New_York")


def test_update_paper_positions_enters_and_closes_target(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    proposal_id = store.log_proposal(
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="breakout",
        planned_entry=101,
        stop=100,
        target=103,
        thesis="test",
    )
    position_id = store.create_paper_position(
        proposal_id=proposal_id,
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        entry=101,
        stop=100,
        target=103,
        position_size=10,
        risk_dollars=10,
    )

    result = update_paper_positions(
        store,
        [
            {"symbol": "AAPL", "timestamp": datetime.now(ET).isoformat(timespec="seconds"), "open": 100, "high": 101.5, "low": 100.5, "close": 101.2, "volume": 1000},
            {"symbol": "AAPL", "timestamp": datetime.now(ET).isoformat(timespec="seconds"), "open": 101.2, "high": 103.5, "low": 101.1, "close": 103.1, "volume": 1000},
        ],
    )

    positions = store.list_paper_positions()
    trades = store.list_paper_trades()
    assert result["event_count"] == 2
    assert positions[0]["id"] == position_id
    assert positions[0]["status"] == "closed"
    assert positions[0]["exit_reason"] == "target"
    assert trades[0]["actual_r_multiple"] == 2.0


def test_update_paper_positions_stop_wins_same_bar_for_conservative_fill(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    proposal_id = store.log_proposal(
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="breakout",
        planned_entry=101,
        stop=100,
        target=103,
        thesis="test",
    )
    store.create_paper_position(
        proposal_id=proposal_id,
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        entry=101,
        stop=100,
        target=103,
        position_size=10,
        risk_dollars=10,
    )

    update_paper_positions(
        store,
        [
            {"symbol": "AAPL", "timestamp": datetime.now(ET).isoformat(timespec="seconds"), "open": 101, "high": 104, "low": 99, "close": 102, "volume": 1000},
        ],
    )

    trade = store.list_paper_trades()[0]
    assert trade["exit_reason"] == "stop"
    assert trade["actual_r_multiple"] == -1.0


def test_update_paper_positions_ignores_bars_before_position_creation(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    proposal_id = store.log_proposal(
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="breakout",
        planned_entry=101,
        stop=100,
        target=103,
        thesis="test",
    )
    store.create_paper_position(
        proposal_id=proposal_id,
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        entry=101,
        stop=100,
        target=103,
        position_size=10,
        risk_dollars=10,
    )

    result = update_paper_positions(
        store,
        [
            {"symbol": "AAPL", "timestamp": "2020-01-01T13:35:00Z", "open": 101, "high": 104, "low": 99, "close": 102, "volume": 1000},
        ],
    )

    assert result["event_count"] == 0
    assert store.list_paper_positions()[0]["status"] == "pending_entry"
    assert store.list_paper_trades() == []
