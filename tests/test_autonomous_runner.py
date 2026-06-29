from trading_lab.autonomous_runner import AutonomousRunner
from trading_lab.journal_store import JournalStore


class FakeWorker:
    def review(self, proposal):
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
