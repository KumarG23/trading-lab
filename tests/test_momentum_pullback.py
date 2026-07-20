from trading_lab.momentum_pullback import STRATEGY_ID, generate_momentum_pullback_candidates


def _bar(minute, open_, high, low, close, volume):
    return {
        "symbol": "AMD",
        "timestamp": f"2026-07-20T13:{30 + minute:02d}:00Z",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def test_generates_long_candidate_after_vwap_pullback_and_resumption():
    bars = [
        _bar(0, 100.0, 100.3, 99.9, 100.2, 1000),
        _bar(1, 100.2, 100.6, 100.1, 100.5, 1000),
        _bar(2, 100.5, 100.9, 100.4, 100.8, 1000),
        _bar(3, 100.8, 101.2, 100.7, 101.1, 1000),
        _bar(4, 101.1, 101.5, 101.0, 101.4, 1000),
        _bar(5, 101.4, 101.8, 101.3, 101.7, 1000),
        _bar(6, 101.7, 101.8, 100.8, 101.1, 900),
        _bar(7, 101.1, 102.2, 101.0, 102.1, 1500),
    ]

    candidates = generate_momentum_pullback_candidates(bars, symbols=["AMD"], risk_dollars=2.0)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["strategy_id"] == STRATEGY_ID
    assert candidate["direction"] == "long"
    assert candidate["planned_entry"] == 102.1
    assert candidate["stop"] < candidate["planned_entry"]
    assert candidate["target"] > candidate["planned_entry"]
    assert candidate["rule_checklist"]["pullback_held_vwap"] is True
    assert candidate["rule_checklist"]["momentum_resumed"] is True


def test_rejects_pullback_that_closes_below_vwap():
    bars = [
        _bar(0, 100.0, 100.3, 99.9, 100.2, 1000),
        _bar(1, 100.2, 100.6, 100.1, 100.5, 1000),
        _bar(2, 100.5, 100.9, 100.4, 100.8, 1000),
        _bar(3, 100.8, 101.2, 100.7, 101.1, 1000),
        _bar(4, 101.1, 101.5, 101.0, 101.4, 1000),
        _bar(5, 101.4, 101.8, 101.3, 101.7, 1000),
        _bar(6, 101.7, 101.8, 98.8, 99.0, 900),
        _bar(7, 99.0, 99.6, 98.9, 99.5, 1500),
    ]

    assert generate_momentum_pullback_candidates(bars, symbols=["AMD"], risk_dollars=2.0) == []
