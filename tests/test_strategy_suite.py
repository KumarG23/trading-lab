from trading_lab.strategy_suite import _enrich_decision_context, generate_strategy_candidates


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
        scanner_context={
            "QQQ": {
                "scanner_score": 77.5,
                "scanner_rank": 2,
                "scanner_generated_at": "2026-06-29T09:05:00-04:00",
            }
        },
    )

    assert {candidate["strategy_id"] for candidate in candidates} == {
        "opening-range-breakout",
        "vwap-trend-imbalance",
    }
    for candidate in candidates:
        context = candidate["market_context"]
        assert context["current_volume"] > 0
        assert context["dollar_volume"] > 0
        assert context["range_pct"] > 0
        assert context["scanner_score"] == 77.5
        assert context["scanner_rank"] == 2
        assert "market_return" in context
    assert {candidate["market_context"]["regime"] for candidate in candidates} == {"unknown"}


def test_context_enrichment_never_uses_future_bar_across_mixed_timezone_formats():
    candidate = {"ticker": "AAPL"}
    context = {"signal_timestamp": "2026-06-01T12:30:00Z"}
    bars = [
        {"symbol": "AAPL", "timestamp": "2026-06-01T08:00:00-04:00", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100},
        {"symbol": "AAPL", "timestamp": "2026-06-01T09:00:00-04:00", "open": 100, "high": 999, "low": 1, "close": 999, "volume": 777},
    ]

    _enrich_decision_context(candidate, context, bars)

    assert context["volume"] == 100.0
    assert context["close"] == 100.0


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


def test_generate_strategy_candidates_can_require_bullish_spy_regime():
    qqq = [
        _bar("QQQ", 0, 100.2, 99.8, 100.0, 1000),
        _bar("QQQ", 1, 100.4, 100.0, 100.2, 1000),
        _bar("QQQ", 2, 100.7, 100.2, 100.5, 1000),
        _bar("QQQ", 3, 101.0, 100.5, 100.8, 1000),
        _bar("QQQ", 4, 101.3, 100.8, 101.1, 1000),
        _bar("QQQ", 5, 102.4, 101.6, 102.2, 2300),
    ]
    spy = [_bar("SPY", minute, 101.1 - minute * 0.2, 100.9 - minute * 0.2, 101 - minute * 0.2, 1000) for minute in range(6)]

    candidates = generate_strategy_candidates(
        qqq + spy,
        symbols=["QQQ", "SPY"],
        enabled_strategies=["vwap"],
        risk_dollars=2.0,
        require_bullish_market_regime=True,
    )

    assert candidates == []


def test_generate_strategy_candidates_includes_reclaim_and_momentum_aliases():
    reclaim_bars = [
        _bar("AAPL", 0, 100.2, 99.8, 100.0, 1000),
        _bar("AAPL", 1, 100.1, 99.8, 99.9, 1000),
        _bar("AAPL", 2, 100.0, 99.7, 99.8, 1000),
        _bar("AAPL", 3, 99.9, 99.6, 99.7, 1000),
        _bar("AAPL", 4, 99.9, 99.5, 99.6, 1000),
        {**_bar("AAPL", 5, 100.7, 99.5, 100.6, 1600), "open": 99.6},
    ]
    momentum_bars = [
        _bar("AMD", 0, 100.3, 99.9, 100.2, 1000),
        _bar("AMD", 1, 100.6, 100.1, 100.5, 1000),
        _bar("AMD", 2, 100.9, 100.4, 100.8, 1000),
        _bar("AMD", 3, 101.2, 100.7, 101.1, 1000),
        _bar("AMD", 4, 101.5, 101.0, 101.4, 1000),
        _bar("AMD", 5, 101.8, 101.3, 101.7, 1000),
        _bar("AMD", 6, 101.8, 100.8, 101.1, 900),
        _bar("AMD", 7, 102.2, 101.0, 102.1, 1500),
    ]

    candidates = generate_strategy_candidates(
        reclaim_bars + momentum_bars,
        symbols=["AAPL", "AMD"],
        enabled_strategies=["reclaim", "momentum"],
        risk_dollars=2.0,
    )

    assert {candidate["strategy_id"] for candidate in candidates} == {"vwap-reclaim", "momentum-pullback"}
