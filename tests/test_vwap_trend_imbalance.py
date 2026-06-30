from trading_lab.vwap_trend_imbalance import STRATEGY_ID, generate_vwap_trend_candidates


def _bar(symbol, minute, high, low, close, volume):
    return {
        "symbol": symbol,
        "timestamp": f"2026-06-29T13:{30 + minute:02d}:00Z",
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def test_generate_vwap_trend_long_candidate_when_price_above_rising_vwap_with_volume():
    bars = [
        _bar("QQQ", 0, 100.2, 99.8, 100.0, 1000),
        _bar("QQQ", 1, 100.4, 100.0, 100.2, 1000),
        _bar("QQQ", 2, 100.7, 100.2, 100.5, 1000),
        _bar("QQQ", 3, 101.0, 100.5, 100.8, 1000),
        _bar("QQQ", 4, 101.3, 100.8, 101.1, 1000),
        _bar("QQQ", 5, 102.4, 101.6, 102.2, 2300),
    ]

    candidates = generate_vwap_trend_candidates(
        bars,
        symbols=["QQQ"],
        risk_dollars=2.0,
        min_bars=6,
        slope_lookback=3,
        volume_lookback=5,
        volume_confirmation_multiple=1.5,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["ticker"] == "QQQ"
    assert candidate["strategy_id"] == STRATEGY_ID
    assert candidate["direction"] == "long"
    assert candidate["planned_entry"] == 102.2
    assert candidate["stop"] < candidate["planned_entry"]
    assert candidate["target"] > candidate["planned_entry"]
    assert candidate["risk_dollars"] == 2.0
    assert candidate["rule_checklist"]["vwap_trend_confirmed"] is True
    assert candidate["rule_checklist"]["volume_confirmed"] is True
    assert candidate["market_context"]["vwap"] < candidate["planned_entry"]


def test_generate_vwap_trend_requires_symbol_allowlist_and_volume_confirmation():
    bars = [
        _bar("AAPL", 0, 100.2, 99.8, 100.0, 1000),
        _bar("AAPL", 1, 100.4, 100.0, 100.2, 1000),
        _bar("AAPL", 2, 100.7, 100.2, 100.5, 1000),
        _bar("AAPL", 3, 101.0, 100.5, 100.8, 1000),
        _bar("AAPL", 4, 101.3, 100.8, 101.1, 1000),
        _bar("AAPL", 5, 102.4, 101.6, 102.2, 2300),
        _bar("SPY", 0, 100.2, 99.8, 100.0, 1000),
        _bar("SPY", 1, 100.4, 100.0, 100.2, 1000),
        _bar("SPY", 2, 100.7, 100.2, 100.5, 1000),
        _bar("SPY", 3, 101.0, 100.5, 100.8, 1000),
        _bar("SPY", 4, 101.3, 100.8, 101.1, 1000),
        _bar("SPY", 5, 102.4, 101.6, 102.2, 1200),
    ]

    assert generate_vwap_trend_candidates(
        bars,
        symbols=["SPY", "QQQ"],
        risk_dollars=2.0,
        min_bars=6,
        slope_lookback=3,
        volume_lookback=5,
        volume_confirmation_multiple=1.5,
    ) == []
