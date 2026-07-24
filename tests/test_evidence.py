from trading_lab.evidence import build_dataset_manifest, build_readiness, dataset_artifact_digest
from trading_lab.journal_store import JournalStore


def test_dataset_manifest_is_deterministic_and_reports_exact_coverage():
    bars = [
        {"symbol": "MSFT", "timestamp": "2026-07-21T13:30:00Z", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        {"symbol": "AAPL", "timestamp": "2026-07-20T13:30:00Z", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
    ]
    records = [{"candidate_event_id": 2, "net_r": -1}, {"candidate_event_id": 1, "net_r": 2}]

    first = build_dataset_manifest(bars=bars, records=records, source="alpaca-iex", code_sha="abc", schema_version="v1")
    second = build_dataset_manifest(bars=list(reversed(bars)), records=list(reversed(records)), source="alpaca-iex", code_sha="abc", schema_version="v1")

    assert first == second
    assert first["coverage"] == {
        "bar_count": 2, "candidate_count": 2,
        "start": "2026-07-20T13:30:00Z", "end": "2026-07-21T13:30:00Z",
        "sessions": 2, "symbols": ["AAPL", "MSFT"],
    }
    assert len(first["dataset_sha256"]) == 64


def test_artifact_digest_is_independent_of_local_absolute_paths():
    first = [{"period": "2026-07", "path": "/home/neal/a.jsonl.gz", "sha256": "abc", "candidate_count": 2}]
    second = [{"period": "2026-07", "path": "/mnt/lab/a.jsonl.gz", "sha256": "abc", "candidate_count": 2}]

    assert dataset_artifact_digest(first) == dataset_artifact_digest(second)


def test_readiness_fails_closed_and_counts_evidence_slices(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    candidate = {
        "ticker": "AAPL", "strategy_id": "orb", "direction": "long",
        "market_context": {"signal_timestamp": "2026-07-20T13:35:00Z", "regime": "bull"},
    }
    event_id = store.log_candidate_event(candidate, disposition="slot_blocked")
    store.log_candidate_outcome(event_id, {
        "fill_status": "no_fill", "net_dollars": 0, "net_r": 0, "fees": 0,
        "same_bar_ambiguity": False, "data_quality_flags": [],
    })

    readiness = build_readiness(store, dataset_manifest=None, model_evaluation=None, minimum_candidates=10_000)

    assert readiness["promotion_ready"] is False
    assert readiness["mode"] == "paper_proposal_only_no_orders"
    assert readiness["broker_orders_enabled"] is False
    assert readiness["live_trading_enabled"] is False
    assert readiness["counts"]["resolved_candidates"] == 1
    assert readiness["counts"]["by_disposition"] == {"slot_blocked": 1}
    assert readiness["counts"]["by_strategy"] == {"orb": 1}
    assert readiness["counts"]["by_session"] == {"2026-07-20": 1}
    assert readiness["counts"]["by_regime"] == {"bull": 1}
    assert "resolved_candidates_below_10000:1" in readiness["blockers"]
    assert "dataset_manifest_missing" in readiness["blockers"]
    assert "model_evaluation_missing" in readiness["blockers"]
    assert "human_promotion_not_granted" in readiness["blockers"]


def test_readiness_can_use_historical_evidence_rows_instead_of_live_db(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    rows = [{
        "disposition": "policy_approved",
        "candidate": {"strategy_id": "orb", "market_context": {"signal_timestamp": "2026-07-20T13:35:00Z", "regime": "bull"}},
        "outcome": {"fill_status": "filled", "data_quality_flags": []},
    }]

    readiness = build_readiness(
        store, dataset_manifest={"dataset_sha256": "x"},
        model_evaluation={"all_promotion_gates_pass": False},
        minimum_candidates=1, evidence_rows=rows,
    )

    assert readiness["counts"]["resolved_candidates"] == 1
    assert readiness["counts"]["by_strategy"] == {"orb": 1}
    assert "resolved_candidates_below_1:1" not in readiness["blockers"]
