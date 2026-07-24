import pytest

from scripts.replay_evidence_dataset import _write_immutable_rows


def test_evidence_partition_is_deterministic_immutable_and_uses_portable_manifest_path(tmp_path):
    path = tmp_path / "candidate-outcomes-v4" / "2026-07.jsonl.gz"
    rows = [{"candidate": {"ticker": "AAPL"}, "outcome": {"net_r": 1.0}}]

    first = _write_immutable_rows(path, rows)
    second = _write_immutable_rows(path, rows)

    assert first == second
    assert first["path"] == "2026-07.jsonl.gz"
    assert first["candidate_count"] == 1
    assert len(first["sha256"]) == 64

    with pytest.raises(RuntimeError, match="immutable evidence conflict"):
        _write_immutable_rows(path, [{"candidate": {"ticker": "AAPL"}, "outcome": {"net_r": -1.0}}])
