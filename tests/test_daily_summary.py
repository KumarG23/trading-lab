from trading_lab.daily_summary import format_daily_summary, max_drawdown_r


def test_max_drawdown_r_uses_peak_to_trough_not_total_loss():
    assert max_drawdown_r([2.0, -1.0, -1.5, 3.0, -0.5]) == -2.5


def test_daily_summary_is_compact_and_surfaces_health_performance_and_blockers():
    text = format_daily_summary(
        {
            "date": "2026-07-20",
            "last_scan_ok": True,
            "scan_interval_minutes": 1,
            "loop_ms": 984.3,
            "decision_ms": 5.3,
            "broker_orders": 0,
            "proposals": 12,
            "closes": 6,
            "wins": 4,
            "losses": 2,
            "pnl": 3.25,
            "r": 2.5,
            "max_drawdown_r": -1.0,
            "strategy_lines": ["ORB 3: +2.00R", "VWAP reclaim 3: +0.50R"],
            "active_positions": 1,
            "errors": 0,
            "blocker": "No strategy has passed walk-forward promotion gates.",
        }
    )

    assert text.splitlines() == [
        "Trading Lab close — 2026-07-20",
        "Health: OK · 1m scans · loop 984ms · decision 5.3ms · orders 0",
        "Today: 12 proposals · 6 closes · 4W/2L · +$3.25 · +2.50R · DD -1.00R",
        "Strategies: ORB 3: +2.00R | VWAP reclaim 3: +0.50R",
        "Open: 1 · errors: 0",
        "Gate: No strategy has passed walk-forward promotion gates.",
    ]
