from trading_lab.backtest import run_strategy_backtest


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


def test_run_strategy_backtest_replays_candidates_to_closed_trades_with_metrics():
    bars = [
        _bar("AAPL", 0, 101.0, 99.0, 100.0, 1000),
        _bar("AAPL", 1, 101.2, 99.2, 100.2, 1000),
        _bar("AAPL", 2, 101.3, 99.3, 100.3, 1000),
        _bar("AAPL", 3, 101.4, 99.4, 100.4, 1000),
        _bar("AAPL", 4, 101.5, 99.5, 100.5, 1000),
        _bar("AAPL", 5, 102.2, 101.6, 102.0, 2500),
        _bar("AAPL", 6, 103.2, 101.9, 103.1, 2000),
    ]

    result = run_strategy_backtest(
        bars,
        symbols=["AAPL"],
        enabled_strategies=["orb"],
        account_equity=200.0,
        risk_dollars=2.0,
        opening_range_minutes=5,
    )

    assert result["proposals"] == 1
    assert result["trades"] == 1
    assert result["metrics"]["total_r"] == 0.0
    assert result["metrics"]["expectancy_r"] == 0.0
    assert result["metrics"]["by_strategy"]["opening-range-breakout"]["trade_count"] == 1


def test_run_strategy_backtest_applies_slippage_to_entries_and_exits():
    bars = [
        _bar("AAPL", 0, 101.0, 99.0, 100.0, 1000),
        _bar("AAPL", 1, 101.2, 99.2, 100.2, 1000),
        _bar("AAPL", 2, 101.3, 99.3, 100.3, 1000),
        _bar("AAPL", 3, 101.4, 99.4, 100.4, 1000),
        _bar("AAPL", 4, 101.5, 99.5, 100.5, 1000),
        _bar("AAPL", 5, 102.2, 101.6, 102.0, 2500),
        _bar("AAPL", 6, 103.2, 101.9, 103.1, 2000),
    ]

    clean = run_strategy_backtest(bars, symbols=["AAPL"], enabled_strategies=["orb"], account_equity=200.0, risk_dollars=2.0)
    slipped = run_strategy_backtest(
        bars,
        symbols=["AAPL"],
        enabled_strategies=["orb"],
        account_equity=200.0,
        risk_dollars=2.0,
        entry_slippage_bps=10,
        exit_slippage_bps=10,
        fee_per_share=0.005,
    )

    assert slipped["metrics"]["total_r"] < clean["metrics"]["total_r"]
    assert slipped["slippage"]["entry_bps"] == 10
    assert slipped["slippage"]["exit_bps"] == 10
    assert slipped["costs"]["fee_per_share"] == 0.005
    assert slipped["trade_rows"][0]["fees"] > 0


def test_run_strategy_backtest_flattens_unresolved_entry_at_session_end():
    bars = [
        _bar("AAPL", 0, 101.0, 99.0, 100.0, 1000),
        _bar("AAPL", 1, 101.2, 99.2, 100.2, 1000),
        _bar("AAPL", 2, 101.3, 99.3, 100.3, 1000),
        _bar("AAPL", 3, 101.4, 99.4, 100.4, 1000),
        _bar("AAPL", 4, 101.5, 99.5, 100.5, 1000),
        _bar("AAPL", 5, 102.2, 101.6, 102.0, 2500),
        _bar("AAPL", 6, 102.4, 101.9, 102.2, 2000),
        _bar("AAPL", 7, 102.5, 102.0, 102.4, 1800),
    ]

    result = run_strategy_backtest(
        bars,
        symbols=["AAPL"],
        enabled_strategies=["orb"],
        account_equity=200.0,
        risk_dollars=2.0,
        exit_slippage_bps=10,
        fee_per_share=0.005,
    )

    assert result["trades"] == 1
    trade = result["trade_rows"][0]
    assert trade["exit_reason"] == "eod_flatten"
    assert trade["closed_at"].endswith("13:37:00Z")
    assert trade["fees"] > 0


def test_run_strategy_backtest_resets_intraday_state_for_each_session():
    bars = []
    for day in ("2026-06-29", "2026-06-30"):
        bars.extend(
            [
                {**_bar("AAPL", 0, 101.0, 99.0, 100.0, 1000), "timestamp": f"{day}T13:30:00Z"},
                {**_bar("AAPL", 1, 101.2, 99.2, 100.2, 1000), "timestamp": f"{day}T13:31:00Z"},
                {**_bar("AAPL", 2, 101.3, 99.3, 100.3, 1000), "timestamp": f"{day}T13:32:00Z"},
                {**_bar("AAPL", 3, 101.4, 99.4, 100.4, 1000), "timestamp": f"{day}T13:33:00Z"},
                {**_bar("AAPL", 4, 101.5, 99.5, 100.5, 1000), "timestamp": f"{day}T13:34:00Z"},
                {**_bar("AAPL", 5, 102.2, 101.6, 102.0, 2500), "timestamp": f"{day}T13:35:00Z"},
                {**_bar("AAPL", 6, 103.2, 101.9, 103.1, 2000), "timestamp": f"{day}T13:36:00Z"},
            ]
        )

    result = run_strategy_backtest(
        bars,
        symbols=["AAPL"],
        enabled_strategies=["orb"],
        account_equity=200.0,
        risk_dollars=2.0,
    )

    assert result["proposals"] == 2
    assert result["trades"] == 2
    assert result["metrics"]["by_strategy"]["opening-range-breakout"]["trade_count"] == 2


def test_backtest_does_not_use_signal_bars_earlier_low_after_close_entry():
    bars = [
        _bar("AAPL", 0, 101.0, 99.0, 100.0, 1000),
        _bar("AAPL", 1, 101.2, 99.2, 100.2, 1000),
        _bar("AAPL", 2, 101.3, 99.3, 100.3, 1000),
        _bar("AAPL", 3, 101.4, 99.4, 100.4, 1000),
        _bar("AAPL", 4, 101.5, 99.5, 100.5, 1000),
        _bar("AAPL", 5, 102.2, 100.0, 102.0, 2500),
        _bar("AAPL", 6, 103.2, 101.9, 103.1, 2000),
    ]

    result = run_strategy_backtest(
        bars,
        symbols=["AAPL"],
        enabled_strategies=["orb"],
        account_equity=200.0,
        risk_dollars=2.0,
    )

    assert result["trades"] == 1
    assert result["metrics"]["total_r"] == 0.0
    assert result["trade_rows"][0]["entered_at"].endswith("13:36:00Z")


def test_backtest_can_apply_bullish_market_regime_filter():
    aapl = [
        _bar("AAPL", 0, 101.0, 99.0, 100.0, 1000),
        _bar("AAPL", 1, 101.2, 99.2, 100.2, 1000),
        _bar("AAPL", 2, 101.3, 99.3, 100.3, 1000),
        _bar("AAPL", 3, 101.4, 99.4, 100.4, 1000),
        _bar("AAPL", 4, 101.5, 99.5, 100.5, 1000),
        _bar("AAPL", 5, 102.2, 101.6, 102.0, 2500),
        _bar("AAPL", 6, 103.2, 101.9, 103.1, 2000),
    ]
    spy = [_bar("SPY", minute, 101.1 - minute * 0.2, 100.9 - minute * 0.2, 101 - minute * 0.2, 1000) for minute in range(7)]

    result = run_strategy_backtest(
        aapl + spy,
        symbols=["AAPL", "SPY"],
        enabled_strategies=["orb"],
        account_equity=200.0,
        risk_dollars=2.0,
        require_bullish_market_regime=True,
    )

    assert result["proposals"] == 0
    assert result["trades"] == 0
