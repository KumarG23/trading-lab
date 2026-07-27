from __future__ import annotations

from typing import Any, Iterable, Mapping


def max_drawdown_r(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return round(worst, 4)


def format_daily_summary(summary: Mapping[str, Any]) -> str:
    if summary.get("last_scan_stale"):
        health = "ERROR (stale scanner)"
    else:
        health = "OK" if summary.get("last_scan_ok") else "ERROR"
    loop_ms = round(float(summary.get("loop_ms") or 0))
    decision_ms = float(summary.get("decision_ms") or 0)
    pnl = float(summary.get("pnl") or 0)
    total_r = float(summary.get("r") or 0)
    drawdown_r = float(summary.get("max_drawdown_r") or 0)
    strategy_lines = list(summary.get("strategy_lines") or [])
    strategies = " | ".join(strategy_lines) if strategy_lines else "no closes"
    money = f"{'+' if pnl >= 0 else '-'}${abs(pnl):.2f}"
    portfolio_pnl = float(summary.get("portfolio_pnl") or 0)
    portfolio_money = f"{'+' if portfolio_pnl >= 0 else '-'}${abs(portfolio_pnl):.2f}"
    return "\n".join(
        [
            f"Trading Lab close — {summary['date']}",
            f"Health: {health} · {summary.get('scan_interval_minutes', '?')}m scans · loop {loop_ms}ms · decision {decision_ms:.1f}ms · orders {int(summary.get('broker_orders') or 0)}",
            f"Research: {int(summary.get('proposals') or 0)} proposals · {int(summary.get('closes') or 0)} closes · {int(summary.get('wins') or 0)}W/{int(summary.get('losses') or 0)}L · {money} · {total_r:+.2f}R · DD {drawdown_r:.2f}R",
            f"Portfolio: {int(summary.get('portfolio_closes') or 0)} closes · {int(summary.get('portfolio_wins') or 0)}W/{int(summary.get('portfolio_losses') or 0)}L · {portfolio_money} · {float(summary.get('portfolio_r') or 0):+.2f}R · DD {float(summary.get('portfolio_max_drawdown_r') or 0):.2f}R",
            f"Research strategies: {strategies}",
            f"Open research: {int(summary.get('active_positions') or 0)} · portfolio: {int(summary.get('portfolio_active_positions') or 0)}/{int(summary.get('portfolio_position_limit') or 0)} · errors: {int(summary.get('errors') or 0)}",
            f"Gate: {summary.get('blocker') or 'none'}",
        ]
    )
