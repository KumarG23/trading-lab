from trading_lab.opening_range_breakout import generate_orb_candidates


def test_generate_orb_candidate_when_price_breaks_opening_range_high():
    bars = [
        {"symbol": "AAPL", "timestamp": "2026-06-29T13:30:00Z", "open": 100, "high": 101, "low": 99.5, "close": 100.5, "volume": 1000},
        {"symbol": "AAPL", "timestamp": "2026-06-29T13:31:00Z", "open": 100.5, "high": 101.2, "low": 100, "close": 101, "volume": 1100},
        {"symbol": "AAPL", "timestamp": "2026-06-29T13:32:00Z", "open": 101, "high": 101.3, "low": 100.8, "close": 101.1, "volume": 1200},
        {"symbol": "AAPL", "timestamp": "2026-06-29T13:33:00Z", "open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1300},
        {"symbol": "AAPL", "timestamp": "2026-06-29T13:34:00Z", "open": 101.2, "high": 101.5, "low": 101, "close": 101.4, "volume": 1400},
        {"symbol": "AAPL", "timestamp": "2026-06-29T13:35:00Z", "open": 101.4, "high": 102.2, "low": 101.3, "close": 102.0, "volume": 3000},
    ]

    candidates = generate_orb_candidates(bars, opening_range_minutes=5, risk_dollars=10)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["ticker"] == "AAPL"
    assert candidate["direction"] == "long"
    assert candidate["planned_entry"] == 102.0
    assert candidate["stop"] == 101.5
    assert candidate["target"] == 103.0
    assert candidate["strategy_id"] == "opening-range-breakout"
    assert candidate["risk_dollars"] == 10


def test_generate_orb_candidate_requires_breakout_volume_confirmation():
    bars = [
        {"symbol": "AAPL", "timestamp": f"2026-06-29T13:3{i}:00Z", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000}
        for i in range(5)
    ] + [
        {"symbol": "AAPL", "timestamp": "2026-06-29T13:35:00Z", "open": 100.5, "high": 102, "low": 100.4, "close": 101.8, "volume": 900}
    ]

    assert generate_orb_candidates(bars, opening_range_minutes=5, risk_dollars=10) == []
