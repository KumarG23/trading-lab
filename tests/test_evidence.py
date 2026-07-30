import hashlib
import gzip

from trading_lab.decision_features import FEATURE_SCHEMA_SHA256, FEATURE_SCHEMA_VERSION
from trading_lab.evidence import (
    CANDIDATE_OUTCOME_SCHEMA_VERSION,
    build_dataset_manifest,
    build_readiness,
    dataset_artifact_digest,
    verify_replay_evidence_manifest,
)
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


def test_replay_manifest_verification_detects_tampering_and_count_drift(tmp_path):
    artifact_path = tmp_path / "2026-07.jsonl.gz"
    artifact_path.write_bytes(gzip.compress(b'{"row":1}\n{"row":2}\n', mtime=0))
    artifact = {
        "path": artifact_path.name,
        "period": "2026-07",
        "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        "candidate_count": 2,
    }
    manifest = {
        "dataset_sha256": dataset_artifact_digest([artifact]),
        "coverage": {"candidate_count": 2},
        "artifacts": [artifact],
    }

    assert verify_replay_evidence_manifest(manifest, tmp_path)["verified"] is True
    artifact_path.write_bytes(b"tampered")
    result = verify_replay_evidence_manifest(manifest, tmp_path)
    assert result["verified"] is False
    assert result["errors"] == ["artifact_sha256_mismatch:2026-07.jsonl.gz"]


def test_replay_manifest_verification_rejects_unmanifested_evidence_partition(tmp_path):
    first = tmp_path / "2026-07.jsonl.gz"
    first.write_bytes(gzip.compress(b'{"row":1}\n', mtime=0))
    artifact = {
        "path": first.name,
        "period": "2026-07",
        "sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
        "candidate_count": 1,
    }
    manifest = {
        "dataset_sha256": dataset_artifact_digest([artifact]),
        "coverage": {"candidate_count": 1},
        "artifacts": [artifact],
    }
    (tmp_path / "unmanifested.jsonl.gz").write_bytes(gzip.compress(b'{"row":2}\n', mtime=0))

    result = verify_replay_evidence_manifest(manifest, tmp_path)

    assert result["verified"] is False
    assert result["errors"] == ["artifact_unexpected:unmanifested.jsonl.gz"]


def test_readiness_blocks_manifest_schema_contract_mismatches(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    manifest = {
        "dataset_sha256": "a" * 64,
        "code_sha": "b" * 40,
        "schema_version": "counterfactual-candidate-v4",
        "feature_schema_version": "stale-features",
        "feature_schema_sha256": "c" * 64,
        "source": "test",
    }
    readiness = build_readiness(
        store,
        dataset_manifest=manifest,
        model_evaluation={"status": "evaluated", "split_policy": "purged_walk_forward_no_random_split", "all_promotion_gates_pass": False},
        minimum_candidates=0,
        evidence_rows=[],
    )

    assert f"dataset_schema_version_mismatch:{manifest['schema_version']}" in readiness["blockers"]
    assert f"dataset_feature_schema_version_mismatch:{manifest['feature_schema_version']}" in readiness["blockers"]
    assert "dataset_feature_schema_sha256_mismatch" in readiness["blockers"]


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


def test_readiness_blocks_dirty_or_incomplete_provenance_even_when_model_gates_pass(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    rows = [{
        "candidate": {"strategy_id": "orb", "market_context": {"signal_timestamp": "2026-07-20T13:35:00Z"}},
        "outcome": {"fill_status": "filled", "data_quality_flags": []},
    }]
    manifest = {
        "dataset_sha256": "a" * 64,
        "code_sha": "abc-dirty",
        "schema_version": "counterfactual-candidate-v4",
        "source": "alpaca-iex",
    }
    evaluation = {
        "status": "evaluated", "split_policy": "purged_walk_forward_no_random_split",
        "all_promotion_gates_pass": True,
    }

    readiness = build_readiness(
        store, dataset_manifest=manifest, model_evaluation=evaluation,
        minimum_candidates=1, evidence_rows=rows,
    )

    assert readiness["promotion_ready"] is False
    assert "dataset_code_sha_not_clean:abc-dirty" in readiness["blockers"]


def test_readiness_distinguishes_warning_exclusion_and_fatal_quality_flags(tmp_path):
    store = JournalStore(tmp_path / "lab.db")
    rows = [
        {
            "candidate": {"strategy_id": "orb", "market_context": {"signal_timestamp": "2026-07-20T13:35:00Z"}},
            "outcome": {"fill_status": "filled", "data_quality_flags": ["entry_bar_path_unknown"]},
        },
        {
            "candidate": {"strategy_id": "orb", "market_context": {"signal_timestamp": "2026-07-21T13:35:00Z"}},
            "outcome": {"fill_status": "filled", "data_quality_flags": ["same_bar_stop_target"]},
        },
        {
            "candidate": {"strategy_id": "orb", "market_context": {"signal_timestamp": "2026-07-22T13:35:00Z"}},
            "outcome": {"fill_status": "filled", "data_quality_flags": ["impossible_chronology"]},
        },
    ]
    manifest = {
        "dataset_sha256": "a" * 64,
        "code_sha": "b" * 40,
        "schema_version": "counterfactual-candidate-v5",
        "source": "alpaca-iex",
    }
    evaluation = {
        "status": "evaluated",
        "split_policy": "purged_walk_forward_no_random_split",
        "all_promotion_gates_pass": True,
    }

    readiness = build_readiness(
        store,
        dataset_manifest=manifest,
        model_evaluation=evaluation,
        minimum_candidates=1,
        evidence_rows=rows,
    )

    assert readiness["counts"]["outcome_quality_warnings"] == 1
    assert readiness["counts"]["outcome_quality_exclusions"] == 1
    assert readiness["counts"]["outcome_quality_fatal"] == 1
    assert readiness["quality"]["warning_flags"] == {"entry_bar_path_unknown": 1}
    assert readiness["quality"]["exclusion_flags"] == {"same_bar_stop_target": 1}
    assert readiness["quality"]["fatal_flags"] == {"impossible_chronology": 1}
    assert "candidate_outcome_quality_flags:3" not in readiness["blockers"]
    assert "candidate_outcome_fatal_quality_flags:1" in readiness["blockers"]
