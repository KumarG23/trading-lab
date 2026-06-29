from trading_lab.metrics import summarize_trades


def test_summarize_trades_calculates_r_expectancy_profit_factor_drawdown_and_adherence():
    trades = [
        {"actual_r_multiple": 2.0, "pnl": 200.0, "rule_adherent": True, "strategy_id": "orb"},
        {"actual_r_multiple": -1.0, "pnl": -100.0, "rule_adherent": True, "strategy_id": "orb"},
        {"actual_r_multiple": 1.5, "pnl": 150.0, "rule_adherent": False, "strategy_id": "vwap"},
        {"actual_r_multiple": -0.5, "pnl": -50.0, "rule_adherent": True, "strategy_id": "vwap"},
    ]

    summary = summarize_trades(trades)

    assert summary["trade_count"] == 4
    assert summary["win_count"] == 2
    assert summary["loss_count"] == 2
    assert summary["expectancy_r"] == 0.5
    assert summary["profit_factor"] == 2.3333
    assert summary["max_drawdown"] == -100.0
    assert summary["max_drawdown_r"] == -1.0
    assert summary["rule_adherence_rate"] == 0.75
    assert summary["by_strategy"]["orb"]["expectancy_r"] == 0.5
    assert summary["by_strategy"]["vwap"]["expectancy_r"] == 0.5


def test_summarize_trades_returns_empty_summary_for_no_closed_trades():
    summary = summarize_trades([])

    assert summary["trade_count"] == 0
    assert summary["expectancy_r"] == 0.0
    assert summary["profit_factor"] == 0.0
    assert summary["max_drawdown"] == 0.0
    assert summary["rule_adherence_rate"] == 0.0
