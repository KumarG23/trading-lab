from trading_lab.vwap_reclaim import STRATEGY_ID, generate_vwap_reclaim_candidates


def _bar(minute, open_, high, low, close, volume):
    return {
        "symbol": "AAPL",
        "timestamp": f"2026-07-20T13:{30 + minute:02d}:00Z",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def test_generates_long_candidate_when_price_reclaims_vwap_on_volume():
    bars = [
        _bar(0, 100.0, 100.2, 99.8, 100.0, 1000),
        _bar(1, 100.0, 100.1, 99.8, 99.9, 1000),
        _bar(2, 99.9, 100.0, 99.7, 99.8, 1000),
        _bar(3, 99.8, 99.9, 99.6, 99.7, 1000),
        _bar(4, 99.7, 99.9, 99.5, 99.6, 1000),
        _bar(5, 99.6, 100.7, 99.5, 100.6, 1600),
    ]

    candidates = generate_vwap_reclaim_candidates(bars, symbols=["AAPL"], risk_dollars=2.0)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["strategy_id"] == STRATEGY_ID
    assert candidate["direction"] == "long"
    assert candidate["planned_entry"] == 100.6
    assert candidate["stop"] < candidate["planned_entry"]
    assert candidate["target"] > candidate["planned_entry"]
    assert candidate["rule_checklist"]["vwap_reclaimed"] is True
    assert candidate["market_context"]["signal_timestamp"] == bars[-1]["timestamp"]


def test_requires_actual_cross_from_below_vwap():
    bars = [
        _bar(0, 100.0, 100.2, 99.8, 100.1, 1000),
        _bar(1, 100.1, 100.3, 100.0, 100.2, 1000),
        _bar(2, 100.2, 100.4, 100.1, 100.3, 1000),
        _bar(3, 100.3, 100.5, 100.2, 100.4, 1000),
        _bar(4, 100.4, 100.6, 100.3, 100.5, 1000),
        _bar(5, 100.5, 101.0, 100.4, 100.9, 1600),
    ]

    assert generate_vwap_reclaim_candidates(bars, symbols=["AAPL"], risk_dollars=2.0) == []
