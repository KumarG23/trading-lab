import json
from datetime import datetime
from zoneinfo import ZoneInfo

from trading_lab.universe_scanner import scanner_content_sha256
from trading_lab.watchlist import load_scanner_context, load_symbols


ET = ZoneInfo("America/New_York")
def _write_snapshot(path, *, generated_at="2026-08-18T09:05:00-04:00", data_cutoff_at="2026-08-18T09:05:00-04:00", rows=None, include_cutoff=True):
    rows = rows or [{"symbol": "NVDA", "score": 71.2}]
    watchlist = ["SPY", *[str(row["symbol"]) for row in rows]]
    payload = {
        "generated_at": generated_at,
        "watchlist": watchlist,
        "top_matches": rows,
    }
    if include_cutoff:
        payload["data_cutoff_at"] = data_cutoff_at
        payload["scanner_content_sha256"] = scanner_content_sha256(
            rows=rows,
            watchlist=watchlist,
            data_cutoff_at=datetime.fromisoformat(data_cutoff_at),
        )
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_symbols_prefers_scanner_watchlist_file(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text('{"watchlist": ["spy", "sofi", "pltr"]}', encoding="utf-8")

    assert load_symbols("AAPL,MSFT", watchlist_file=path) == ["SPY", "SOFI", "PLTR"]


def test_load_symbols_falls_back_to_cli_symbols_when_file_missing(tmp_path):
    assert load_symbols("aapl, msft, AAPL", watchlist_file=tmp_path / "missing.json") == ["AAPL", "MSFT"]


def test_load_scanner_context_returns_only_same_session_point_in_time_rows(tmp_path):
    path = tmp_path / "watchlist.json"
    _write_snapshot(
        path,
        rows=[
            {"symbol": "NVDA", "score": 71.2, "change_pct": 3.1, "relative_volume": 1.8},
            {"symbol": "AMD", "score": 64.0, "change_pct": 2.4, "relative_volume": 1.3},
        ],
    )
    decision_at = datetime(2026, 8, 18, 10, 0, tzinfo=ET)

    context = load_scanner_context(path, decision_at=decision_at)

    assert context["NVDA"]["scanner_score"] == 71.2
    assert context["NVDA"]["scanner_rank"] == 1
    assert context["NVDA"]["scanner_change_pct"] == 3.1
    assert context["NVDA"]["scanner_data_cutoff_at"] == "2026-08-18T09:05:00-04:00"
    assert len(context["NVDA"]["scanner_content_sha256"]) == 64
    assert context["AMD"]["scanner_rank"] == 2


def test_load_scanner_context_rejects_stale_or_future_snapshot(tmp_path):
    path = tmp_path / "watchlist.json"
    decision_at = datetime(2026, 8, 18, 10, 0, tzinfo=ET)

    _write_snapshot(
        path,
        generated_at="2026-08-17T09:05:00-04:00",
        data_cutoff_at="2026-08-17T09:05:00-04:00",
    )
    assert load_scanner_context(path, decision_at=decision_at) == {}

    _write_snapshot(
        path,
        generated_at="2026-08-18T10:05:00-04:00",
        data_cutoff_at="2026-08-18T10:05:00-04:00",
    )
    assert load_scanner_context(path, decision_at=decision_at) == {}


def test_load_scanner_context_rejects_missing_or_future_data_cutoff(tmp_path):
    path = tmp_path / "watchlist.json"
    decision_at = datetime(2026, 8, 18, 10, 0, tzinfo=ET)

    _write_snapshot(path, include_cutoff=False)
    assert load_scanner_context(path, decision_at=decision_at) == {}

    _write_snapshot(path, data_cutoff_at="2026-08-18T10:01:00-04:00")
    assert load_scanner_context(path, decision_at=decision_at) == {}


def test_load_scanner_context_rejects_naive_decision_time(tmp_path):
    path = tmp_path / "watchlist.json"
    _write_snapshot(path)

    assert load_scanner_context(path, decision_at=datetime(2026, 8, 18, 9, 30)) == {}


def test_load_scanner_context_sanitizes_non_finite_numeric_values(tmp_path):
    path = tmp_path / "watchlist.json"
    payload = {
        "generated_at": "2026-08-18T09:05:00-04:00",
        "data_cutoff_at": "2026-08-18T09:05:00-04:00",
        "scanner_content_sha256": "a" * 64,
        "watchlist": ["SPY", "NVDA"],
        "top_matches": [{"symbol": "NVDA", "score": float("nan"), "relative_volume": float("inf")}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    context = load_scanner_context(
        path,
        decision_at=datetime(2026, 8, 18, 9, 30, tzinfo=ET),
    )

    assert context == {}
