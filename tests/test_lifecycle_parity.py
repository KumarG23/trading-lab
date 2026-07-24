import sqlite3

from trading_lab.backtest import _simulate_candidate
from trading_lab.fill_engine import simulate_position
from trading_lab.journal_store import JournalStore
from trading_lab.paper_lifecycle import update_paper_positions


def test_shared_lifecycle_is_clock_independent_and_replayable():
    candidate = {
        "ticker": "AAPL",
        "direction": "long",
        "planned_entry": 101.0,
        "stop": 100.0,
        "target": 103.0,
        "risk_dollars": 10.0,
        "market_context": {"signal_timestamp": "2026-07-20T13:35:00Z"},
    }
    bars = [
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:35:00Z", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.5, "volume": 1000},
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:36:00Z", "open": 102.0, "high": 102.5, "low": 101.5, "close": 102.2, "volume": 1000},
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:37:00Z", "open": 102.4, "high": 103.5, "low": 102.0, "close": 103.1, "volume": 1000},
    ]

    first = simulate_position(
        candidate,
        bars,
        position_size=10,
        entry_slippage_bps=10,
        exit_slippage_bps=10,
        fee_per_share=0.005,
    )
    second = simulate_position(
        candidate,
        list(reversed(bars)),
        position_size=10,
        entry_slippage_bps=10,
        exit_slippage_bps=10,
        fee_per_share=0.005,
    )

    assert first == second
    assert first == {
        "status": "closed",
        "fill_status": "filled",
        "entered_at": "2026-07-20T13:36:00Z",
        "closed_at": "2026-07-20T13:37:00Z",
        "actual_entry": 102.102,
        "actual_exit": 102.897,
        "exit_reason": "target",
        "fees": 0.1,
        "net_dollars": 7.85,
        "net_r": 0.785,
        "same_bar_ambiguity": False,
        "entry_slippage_dollars": 1.02,
        "exit_slippage_dollars": 1.03,
        "mfe_dollars": 13.98,
        "mae_dollars": -6.02,
        "mfe_r": 1.398,
        "mae_r": -0.602,
        "duration_seconds": 60,
        "data_quality_flags": ["entry_bar_path_unknown"],
    }


def test_shared_lifecycle_records_no_fill_instead_of_dropping_candidate():
    candidate = {
        "ticker": "AAPL",
        "direction": "long",
        "planned_entry": 105.0,
        "stop": 104.0,
        "target": 107.0,
        "risk_dollars": 10.0,
        "market_context": {"signal_timestamp": "2026-07-20T13:35:00Z"},
    }
    bars = [
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:36:00Z", "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1000},
    ]

    assert simulate_position(candidate, bars, position_size=10) == {
        "status": "expired",
        "fill_status": "no_fill",
        "entered_at": None,
        "closed_at": "2026-07-20T13:36:00Z",
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


def test_shared_lifecycle_can_leave_live_position_open_without_forced_flatten():
    candidate = {
        "ticker": "AAPL", "direction": "long", "planned_entry": 101.0,
        "stop": 100.0, "target": 103.0, "risk_dollars": 10.0,
        "market_context": {"signal_timestamp": "2026-07-20T13:35:00Z"},
    }
    bars = [
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:36:00Z", "open": 101.0, "high": 102.0, "low": 100.5, "close": 101.5, "volume": 1000},
    ]

    result = simulate_position(candidate, bars, position_size=10, flatten_unresolved=False)

    assert result["status"] == "open"
    assert result["fill_status"] == "filled"
    assert result["actual_entry"] == 101.0
    assert result["actual_exit"] is None


def test_live_and_replay_lifecycle_have_exact_fill_parity(tmp_path):
    candidate = {
        "ticker": "AAPL", "strategy_id": "orb", "direction": "long",
        "planned_entry": 101.0, "stop": 100.0, "target": 103.0,
        "risk_dollars": 10.0,
        "market_context": {"signal_timestamp": "2026-07-20T13:35:00+00:00"},
    }
    bars = [
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:36:00+00:00", "open": 102.0, "high": 102.5, "low": 101.5, "close": 102.2, "volume": 1000},
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:37:00+00:00", "open": 102.4, "high": 103.5, "low": 102.0, "close": 103.1, "volume": 1000},
    ]
    replay = _simulate_candidate(
        candidate, bars, position_size=10, entry_slippage_bps=10,
        exit_slippage_bps=10, fee_per_share=0.005,
    )
    store = JournalStore(tmp_path / "parity.db")
    proposal_id = store.log_proposal(
        ticker="AAPL", strategy_id="orb", direction="long", trigger="test",
        planned_entry=101, stop=100, target=103, thesis="parity",
    )
    position_id = store.create_paper_position(
        proposal_id=proposal_id, ticker="AAPL", strategy_id="orb", direction="long",
        entry=101, stop=100, target=103, position_size=10, risk_dollars=10,
    )
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE paper_positions SET created_at = ? WHERE id = ?",
            (candidate["market_context"]["signal_timestamp"], position_id),
        )
    update_paper_positions(
        store, bars, entry_slippage_bps=10, exit_slippage_bps=10,
        fee_per_share=0.005,
    )
    live = store.list_paper_trades()[0]

    assert replay is not None
    assert (live["actual_entry"], live["actual_exit"], live["pnl"], live["actual_r_multiple"], live["fees"], live["exit_reason"]) == (
        replay["actual_entry"], replay["actual_exit"], replay["pnl"],
        replay["actual_r_multiple"], replay["fees"], replay["exit_reason"],
    )


def test_shared_lifecycle_compares_timestamp_instants_not_rendered_offsets():
    candidate = {
        "ticker": "AAPL", "direction": "long", "planned_entry": 101,
        "stop": 100, "target": 103, "risk_dollars": 1,
        "market_context": {"signal_timestamp": "2026-07-20T09:35:00-04:00"},
    }
    bars = [
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:34:00Z", "open": 101, "high": 104, "low": 99, "close": 102, "volume": 1},
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:36:00+00:00", "open": 100, "high": 100.5, "low": 99.5, "close": 100, "volume": 1},
    ]

    outcome = simulate_position(candidate, bars, position_size=1)

    assert outcome["fill_status"] == "no_fill"


def test_shared_lifecycle_keeps_existing_position_open_when_no_new_bars():
    candidate = {
        "ticker": "AAPL", "direction": "long", "planned_entry": 101,
        "stop": 100, "target": 103, "risk_dollars": 1,
        "market_context": {"signal_timestamp": "2026-07-20T13:35:00Z"},
    }

    outcome = simulate_position(
        candidate, [], position_size=1, flatten_unresolved=False,
        initial_entry=101, initial_entered_at="2026-07-20T13:35:00Z",
    )

    assert outcome["status"] == "open"
    assert outcome["fill_status"] == "filled"
