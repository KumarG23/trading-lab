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


def test_dashboard_metrics_attribute_closed_trades_to_proposal_strategy(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    proposal_id = store.log_proposal(
        ticker="QQQ",
        strategy_id="vwap-reclaim",
        direction="long",
        trigger="reclaim",
        planned_entry=100,
        stop=99,
        target=102,
        thesis="test",
        rule_checklist={},
    )
    position_id = store.create_paper_position(
        proposal_id=proposal_id,
        ticker="QQQ",
        strategy_id="vwap-reclaim",
        direction="long",
        entry=100,
        stop=99,
        target=102,
        position_size=1,
        risk_dollars=1,
        status="open",
    )
    store.close_position(position_id, closed_at="2026-07-20T10:00:00-04:00", exit_price=102, exit_reason="target")

    snapshot = build_dashboard_snapshot(store, account_equity=200, live_enabled=False)

    assert snapshot["metrics"]["by_strategy"]["vwap-reclaim"]["trade_count"] == 1
    assert "unknown" not in snapshot["metrics"]["by_strategy"]


def test_dashboard_splits_research_metrics_from_portfolio_metrics(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    for ticker, admitted, exit_price, reason in (
        ("AAPL", True, 103, "target"),
        ("MSFT", False, 100, "stop"),
    ):
        proposal_id = store.log_proposal(
            ticker=ticker,
            strategy_id="opening-range-breakout",
            direction="long",
            trigger="breakout",
            planned_entry=101,
            stop=100,
            target=103,
            thesis="test",
            rule_checklist={"portfolio_admitted": admitted},
        )
        position_id = store.create_paper_position(
            proposal_id=proposal_id,
            ticker=ticker,
            strategy_id="opening-range-breakout",
            direction="long",
            entry=101,
            stop=100,
            target=103,
            position_size=1,
            risk_dollars=1,
            status="open",
        )
        store.close_position(position_id, closed_at="2026-07-20T10:00:00-04:00", exit_price=exit_price, exit_reason=reason)

    snapshot = build_dashboard_snapshot(store, account_equity=200, live_enabled=False)

    assert snapshot["research_metrics"]["trade_count"] == 2
    assert snapshot["portfolio_metrics"]["trade_count"] == 1
    assert snapshot["portfolio_metrics"]["total_r"] == 2.0
    assert snapshot["metrics"] == snapshot["portfolio_metrics"]


def test_dashboard_snapshot_includes_latest_runtime_latency(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    telemetry = tmp_path / "runtime.json"
    telemetry.write_text('{"timings_ms":{"total":869.1,"decision":5.51},"strategies":["orb","reclaim"]}')

    snapshot = build_dashboard_snapshot(
        store,
        account_equity=200,
        live_enabled=False,
        telemetry_path=telemetry,
    )

    assert snapshot["runtime"]["available"] is True
    assert snapshot["runtime"]["timings_ms"]["total"] == 869.1
    assert snapshot["runtime"]["strategies"] == ["orb", "reclaim"]
