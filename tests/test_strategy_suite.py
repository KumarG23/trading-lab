from trading_lab.strategy_suite import generate_strategy_candidates


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


def test_generate_strategy_candidates_combines_orb_and_vwap_when_enabled():
    bars = [
        _bar("QQQ", 0, 100.2, 99.8, 100.0, 1000),
        _bar("QQQ", 1, 100.4, 100.0, 100.2, 1000),
        _bar("QQQ", 2, 100.7, 100.2, 100.5, 1000),
        _bar("QQQ", 3, 101.0, 100.5, 100.8, 1000),
        _bar("QQQ", 4, 101.3, 100.8, 101.1, 1000),
        _bar("QQQ", 5, 102.4, 101.6, 102.2, 2300),
    ]

    candidates = generate_strategy_candidates(
        bars,
        symbols=["QQQ"],
        enabled_strategies=["orb", "vwap"],
        risk_dollars=2.0,
        opening_range_minutes=5,
    )

    assert {candidate["strategy_id"] for candidate in candidates} == {
        "opening-range-breakout",
        "vwap-trend-imbalance",
    }


def test_generate_strategy_candidates_caps_risk_to_fit_small_account_notional_limit():
    bars = [
        _bar("SPY", 0, 700.2, 699.8, 700.0, 1000),
        _bar("SPY", 1, 700.4, 700.0, 700.2, 1000),
        _bar("SPY", 2, 700.7, 700.2, 700.5, 1000),
        _bar("SPY", 3, 701.0, 700.5, 700.8, 1000),
        _bar("SPY", 4, 701.3, 700.8, 701.1, 1000),
        _bar("SPY", 5, 702.4, 701.6, 702.2, 2300),
    ]

    candidates = generate_strategy_candidates(
        bars,
        symbols=["SPY"],
        enabled_strategies=["vwap"],
        risk_dollars=2.0,
        account_equity=200.0,
        max_position_notional_pct=2.0,
        opening_range_minutes=5,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    risk_per_share = candidate["planned_entry"] - candidate["stop"]
    position_size = candidate["risk_dollars"] / risk_per_share
    assert position_size * candidate["planned_entry"] <= 400.01
    assert candidate["risk_dollars"] < 2.0


def test_generate_strategy_candidates_can_run_vwap_only():
    bars = [
        _bar("SPY", 0, 100.2, 99.8, 100.0, 1000),
        _bar("SPY", 1, 100.4, 100.0, 100.2, 1000),
        _bar("SPY", 2, 100.7, 100.2, 100.5, 1000),
        _bar("SPY", 3, 101.0, 100.5, 100.8, 1000),
        _bar("SPY", 4, 101.3, 100.8, 101.1, 1000),
        _bar("SPY", 5, 102.4, 101.6, 102.2, 2300),
    ]

    candidates = generate_strategy_candidates(
        bars,
        symbols=["SPY"],
        enabled_strategies=["vwap"],
        risk_dollars=2.0,
        opening_range_minutes=5,
    )

    assert [candidate["strategy_id"] for candidate in candidates] == ["vwap-trend-imbalance"]
