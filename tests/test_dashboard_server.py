from scripts.dashboard_server import performance_kpis


def test_dashboard_performance_kpis_put_real_money_before_r_units():
    kpis = performance_kpis(
        {
            "trade_count": 4,
            "total_pnl": 6.0,
            "total_r": 3.0,
            "expectancy_r": 0.75,
            "profit_factor": 2.0,
            "rule_adherence_rate": 1.0,
        }
    )

    assert [label for label, _value, _hint in kpis[:4]] == [
        "P&L",
        "Average $ / trade",
        "Total R",
        "Expectancy R",
    ]
    assert kpis[0][1] == "+$6.00"
    assert kpis[1][1] == "+$1.50"
