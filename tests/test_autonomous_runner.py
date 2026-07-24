from trading_lab.autonomous_runner import AutonomousRunner
from trading_lab.journal_store import JournalStore


class FakeWorker:
    def __init__(self):
        self.reviewed = []

    def review(self, proposal):
        self.reviewed.append(proposal["ticker"])
        return {
            "approved": True,
            "thesis": "local model agrees with deterministic setup",
            "risk_officer_objection": "none",
            "model_used": "fake-local",
        }


def _good_candidate(ticker="AAPL"):
    return {
        "ticker": ticker,
        "asset_class": "stock",
        "direction": "long",
        "strategy_id": "opening-range-breakout",
        "trigger": "break 5m high",
        "planned_entry": 101.0,
        "stop": 100.0,
        "target": 103.0,
        "risk_dollars": 10.0,
    }


def test_autonomous_runner_logs_only_policy_approved_proposals(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    runner = AutonomousRunner(store=store, worker=FakeWorker(), account_equity=1000)

    ids = runner.process_candidates(
        [
            _good_candidate(),
            {
                "ticker": "DOGE-USD",
                "asset_class": "crypto",
                "direction": "long",
                "strategy_id": "momentum-pullback",
                "trigger": "bad idea",
                "planned_entry": 1.0,
                "stop": 0.9,
                "target": 1.2,
                "risk_dollars": 10.0,
            },
        ]
    )

    proposals = store.list_proposals()
    positions = store.list_paper_positions()
    assert ids == [proposals[0]["id"]]
    assert len(proposals) == 1
    assert len(positions) == 1
    assert positions[0]["status"] == "pending_entry"
    assert proposals[0]["ticker"] == "AAPL"
    assert proposals[0]["rule_checklist"]["policy_approved"] is True
    assert "planned_r_multiple" in proposals[0]["rule_checklist"]


def test_autonomous_runner_suppresses_duplicate_proposals(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    runner = AutonomousRunner(store=store, worker=FakeWorker(), account_equity=1000)

    first = runner.process_candidates([_good_candidate()])
    second = runner.process_candidates([_good_candidate()])

    assert len(first) == 1
    assert second == []
    assert len(store.list_proposals()) == 1
    assert len(store.list_paper_positions()) == 1


def test_autonomous_runner_caps_model_reviews_per_run(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    worker = FakeWorker()
    runner = AutonomousRunner(store=store, worker=worker, account_equity=1000, max_reviews_per_run=1, max_active_positions=None)

    ids = runner.process_candidates([_good_candidate("AAPL"), _good_candidate("MSFT")])

    assert len(ids) == 1
    assert worker.reviewed == ["AAPL"]
    assert [p["ticker"] for p in store.list_proposals()] == ["AAPL"]


def test_autonomous_runner_tracks_all_research_candidates_but_caps_portfolio_admission(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    worker = FakeWorker()
    runner = AutonomousRunner(store=store, worker=worker, account_equity=1000, max_active_positions=1)

    ids = runner.process_candidates([_good_candidate("AAPL"), _good_candidate("MSFT")])

    proposals = store.list_proposals()
    assert len(ids) == 2
    assert worker.reviewed == ["AAPL", "MSFT"]
    assert len(store.list_active_paper_positions()) == 2
    assert [proposal["rule_checklist"]["portfolio_admitted"] for proposal in proposals] == [True, False]


def test_autonomous_runner_prioritizes_underrepresented_strategy(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    store.log_proposal(
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="historical orb",
        planned_entry=101,
        stop=100,
        target=103,
        thesis="history",
        rule_checklist={},
    )
    worker = FakeWorker()
    runner = AutonomousRunner(store=store, worker=worker, account_equity=1000, max_active_positions=1)
    orb = _good_candidate("MSFT")
    reclaim = _good_candidate("QQQ")
    reclaim["strategy_id"] = "vwap-reclaim"

    ids = runner.process_candidates([orb, reclaim])

    proposals = store.list_proposals()
    assert len(ids) == 2
    assert worker.reviewed == ["QQQ", "MSFT"]
    assert proposals[-2]["strategy_id"] == "vwap-reclaim"
    assert proposals[-2]["rule_checklist"]["portfolio_admitted"] is True
    assert proposals[-1]["rule_checklist"]["portfolio_admitted"] is False


def test_autonomous_runner_research_default_allows_more_than_twenty_trades(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    for index in range(20):
        proposal_id = store.log_proposal(
            ticker=f"T{index}",
            strategy_id="opening-range-breakout",
            direction="long",
            trigger="historical",
            planned_entry=101,
            stop=100,
            target=103,
            thesis="history",
            rule_checklist={},
        )
        store.log_paper_trade(
            proposal_id=proposal_id,
            actual_entry=101,
            actual_exit=103,
            position_size=1,
            pnl=2,
            actual_r_multiple=2,
            rule_adherent=True,
        )
    worker = FakeWorker()
    runner = AutonomousRunner(store=store, worker=worker, account_equity=1000, max_active_positions=None)

    ids = runner.process_candidates([_good_candidate("MSFT")])

    assert len(ids) == 1
    assert worker.reviewed == ["MSFT"]


def test_autonomous_runner_research_cap_counts_proposals_and_cannot_be_overshot_within_one_tick(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    for index in range(49):
        store.log_proposal(
            ticker=f"T{index}",
            strategy_id="opening-range-breakout",
            direction="long",
            trigger="historical",
            planned_entry=101,
            stop=100,
            target=103,
            thesis="history",
            rule_checklist={},
        )
    worker = FakeWorker()
    runner = AutonomousRunner(store=store, worker=worker, account_equity=1000, max_active_positions=None)

    ids = runner.process_candidates([_good_candidate("MSFT"), _good_candidate("NVDA")])

    assert len(ids) == 1
    assert len(store.list_proposals()) == 50


def test_autonomous_runner_keeps_research_capture_running_after_portfolio_loss_breaker(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    proposal_id = store.log_proposal(
        ticker="AAPL",
        strategy_id="opening-range-breakout",
        direction="long",
        trigger="historical loss",
        planned_entry=101,
        stop=100,
        target=103,
        thesis="history",
        rule_checklist={"portfolio_admitted": True},
    )
    store.log_paper_trade(
        proposal_id=proposal_id,
        actual_entry=101,
        actual_exit=95,
        position_size=10,
        pnl=-60,
        actual_r_multiple=-6,
        rule_adherent=True,
    )
    worker = FakeWorker()
    runner = AutonomousRunner(store=store, worker=worker, account_equity=1000, max_active_positions=2)

    ids = runner.process_candidates([_good_candidate("MSFT")])

    assert len(ids) == 1
    proposal = store.list_proposals()[-1]
    assert proposal["ticker"] == "MSFT"
    assert proposal["rule_checklist"]["portfolio_admitted"] is False


def test_autonomous_runner_uses_net_realized_pnl_for_loss_circuit_breaker(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    for index, pnl in enumerate((-60, 100)):
        proposal_id = store.log_proposal(
            ticker=f"P{index}",
            strategy_id="opening-range-breakout",
            direction="long",
            trigger="historical",
            planned_entry=101,
            stop=100,
            target=103,
            thesis="history",
            rule_checklist={},
        )
        store.log_paper_trade(
            proposal_id=proposal_id,
            actual_entry=101,
            actual_exit=103,
            position_size=1,
            pnl=pnl,
            actual_r_multiple=2,
            rule_adherent=True,
        )
    worker = FakeWorker()
    runner = AutonomousRunner(store=store, worker=worker, account_equity=1000, max_active_positions=None)

    ids = runner.process_candidates([_good_candidate("MSFT")])

    assert len(ids) == 1
    assert worker.reviewed == ["MSFT"]
