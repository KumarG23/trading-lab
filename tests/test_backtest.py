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
    assert result["metrics"]["total_r"] == 2.0
    assert result["metrics"]["expectancy_r"] == 2.0
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
    )

    assert slipped["metrics"]["total_r"] < clean["metrics"]["total_r"]
    assert slipped["slippage"]["entry_bps"] == 10
    assert slipped["slippage"]["exit_bps"] == 10
