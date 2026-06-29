from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Iterable, Mapping, Any


def _num(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round(value: float, places: int = 4) -> float:
    if not isfinite(value):
        return value
    return round(value, places)


def summarize_trades(trades: Iterable[Mapping[str, Any]], *, include_strategy_breakdown: bool = True) -> dict[str, Any]:
    rows = [dict(t) for t in trades]
    if not rows:
        return {
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "expectancy_r": 0.0,
            "profit_factor": 0.0,
            "total_pnl": 0.0,
            "total_r": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_r": 0.0,
            "rule_adherence_rate": 0.0,
            "by_strategy": {},
        }

    r_values = [_num(t.get("actual_r_multiple")) for t in rows]
    pnls = [_num(t.get("pnl")) for t in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    adherent = sum(1 for t in rows if bool(t.get("rule_adherent")))

    summary = {
        "trade_count": len(rows),
        "win_count": len(wins),
        "loss_count": len(losses),
        "expectancy_r": _round(sum(r_values) / len(r_values)),
        "profit_factor": _profit_factor(wins, losses),
        "total_pnl": _round(sum(pnls)),
        "total_r": _round(sum(r_values)),
        "max_drawdown": _round(_max_drawdown(pnls)),
        "max_drawdown_r": _round(_max_drawdown(r_values)),
        "rule_adherence_rate": _round(adherent / len(rows)),
        "by_strategy": {},
    }
    if include_strategy_breakdown:
        summary["by_strategy"] = _summarize_by_strategy(rows)
    return summary


def _profit_factor(wins: list[float], losses: list[float]) -> float:
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss == 0:
        return 0.0 if gross_profit == 0 else float("inf")
    return _round(gross_profit / gross_loss)


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def _summarize_by_strategy(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("strategy_id") or "unknown")].append(row)
    return {
        strategy: summarize_trades(group, include_strategy_breakdown=False)
        for strategy, group in sorted(groups.items())
    }
