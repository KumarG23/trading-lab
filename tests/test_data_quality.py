from trading_lab.data_quality import validate_minute_bars


def _bar(ts, volume=100):
    return {
        "symbol": "AAPL", "timestamp": ts, "open": 100, "high": 101,
        "low": 99, "close": 100.5, "volume": volume,
    }


def test_quality_gate_detects_duplicate_nonmonotonic_missing_and_zero_volume():
    bars = [
        _bar("2026-07-20T13:31:00Z"),
        _bar("2026-07-20T13:30:00Z"),
        _bar("2026-07-20T13:31:00Z"),
        _bar("2026-07-20T13:33:00Z", volume=0),
    ]

    report = validate_minute_bars(bars)

    assert report["ok"] is False
    assert report["duplicate_bars"] == 1
    assert report["non_monotonic"] == 1
    assert report["missing_minutes"] == 1
    assert report["zero_volume"] == 1
    assert set(report["flags"]) == {"duplicate_bars", "missing_minutes", "non_monotonic", "zero_volume"}


def test_quality_gate_accepts_ordered_contiguous_positive_volume_bars():
    report = validate_minute_bars([
        _bar("2026-07-20T13:30:00Z"),
        _bar("2026-07-20T13:31:00+00:00"),
    ])

    assert report["ok"] is True
    assert report["fatal"] is False
    assert report["flags"] == []


def test_missing_minutes_are_flagged_but_not_globally_fatal():
    report = validate_minute_bars([
        _bar("2026-07-20T13:30:00Z"),
        _bar("2026-07-20T13:32:00Z"),
    ])

    assert report["ok"] is False
    assert report["fatal"] is False
    assert report["flags"] == ["missing_minutes"]
