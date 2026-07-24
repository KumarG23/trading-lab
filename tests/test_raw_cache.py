import pytest

from trading_lab.raw_cache import read_bar_chunk, verify_raw_manifest, write_immutable_bar_chunk


def test_raw_cache_is_content_addressed_and_immutable(tmp_path):
    bars = [{"symbol": "AAPL", "timestamp": "2026-07-20T13:30:00Z", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10}]

    first = write_immutable_bar_chunk(tmp_path, symbol="AAPL", period="2026-07", bars=bars, source="alpaca-iex")
    second = write_immutable_bar_chunk(tmp_path, symbol="AAPL", period="2026-07", bars=list(reversed(bars)), source="alpaca-iex")

    assert first == second
    assert first["bar_count"] == 1
    assert first["path"].endswith("AAPL/2026-07.jsonl.gz")
    assert len(first["sha256"]) == 64
    assert read_bar_chunk(first["path"]) == bars

    with pytest.raises(RuntimeError, match="immutable raw cache conflict"):
        write_immutable_bar_chunk(tmp_path, symbol="AAPL", period="2026-07", bars=[{**bars[0], "close": 9}], source="alpaca-iex")

    with pytest.raises(RuntimeError, match="hash mismatch"):
        read_bar_chunk(first["path"], expected_sha256="0" * 64)


def test_raw_manifest_fails_closed_on_provider_errors():
    with pytest.raises(RuntimeError, match="incomplete raw manifest"):
        verify_raw_manifest({"ok": False, "errors": [{"error": "subscription limit"}]})


def test_raw_manifest_verifies_chunk_hashes_and_declared_coverage(tmp_path):
    bars = [{"symbol": "AAPL", "timestamp": "2026-07-20T13:30:00Z", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10}]
    chunk = write_immutable_bar_chunk(
        tmp_path, symbol="AAPL", period="2026-07", bars=bars, source="alpaca-iex",
    )
    manifest = {
        "ok": True,
        "errors": [],
        "chunks": [chunk],
        "coverage": {
            "chunks": 1, "bar_count": 1, "nonempty_chunks": 1,
            "start": bars[0]["timestamp"], "end": bars[0]["timestamp"],
            "symbols_with_data": ["AAPL"],
        },
    }

    verify_raw_manifest(manifest, verify_files=True)
    manifest["coverage"]["bar_count"] = 2

    with pytest.raises(RuntimeError, match="coverage mismatch"):
        verify_raw_manifest(manifest, verify_files=True)
