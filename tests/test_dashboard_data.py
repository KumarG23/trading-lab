from trading_lab.dashboard_data import build_dashboard_snapshot
from trading_lab.journal_store import JournalStore


def test_build_dashboard_snapshot_includes_safety_metrics_and_readiness(tmp_path):
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
        rule_checklist={"policy_approved": True},
    )
    store.create_paper_position(
        proposal_id=proposal_id,
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        entry=101,
        stop=100,
        target=103,
        position_size=2,
        risk_dollars=2,
        status="open",
    )

    scanner_path = tmp_path / "scanner.json"
    scanner_path.write_text('{"watchlist": ["SPY", "SOFI"], "top_matches": [{"symbol": "SOFI", "score": 99}]}', encoding="utf-8")
    snapshot = build_dashboard_snapshot(store, account_equity=200.0, live_enabled=False, scanner_path=scanner_path)

    assert snapshot["safety"]["live_trading_enabled"] is False
    assert snapshot["safety"]["broker_orders_enabled"] is False
    assert snapshot["counts"]["proposals"] == 1
    assert snapshot["counts"]["active_positions"] == 1
    assert snapshot["proposals_by_strategy"] == {"opening-range-breakout": 1}
    assert snapshot["readiness"]["proposal_mode"]["status"] == "ok"
    assert snapshot["readiness"]["broker_paper_execution"]["status"] == "blocked"
    assert snapshot["active_positions"][0]["ticker"] == "AAPL"
    assert snapshot["scanner"]["available"] is True
    assert snapshot["scanner"]["watchlist"] == ["SPY", "SOFI"]
