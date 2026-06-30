from __future__ import annotations

from typing import Any

from trading_lab.opening_range_breakout import generate_orb_candidates
from trading_lab.vwap_trend_imbalance import generate_vwap_trend_candidates


def generate_strategy_candidates(
    bars: list[dict[str, Any]],
    *,
    symbols: list[str],
    enabled_strategies: list[str],
    risk_dollars: float,
    opening_range_minutes: int = 5,
    account_equity: float | None = None,
    max_position_notional_pct: float = 2.0,
) -> list[dict[str, Any]]:
    enabled = {strategy.strip().lower() for strategy in enabled_strategies}
    candidates: list[dict[str, Any]] = []

    if "orb" in enabled or "opening-range-breakout" in enabled:
        candidates.extend(
            generate_orb_candidates(
                bars,
                opening_range_minutes=opening_range_minutes,
                risk_dollars=risk_dollars,
            )
        )
    if "vwap" in enabled or "vwap-trend-imbalance" in enabled:
        candidates.extend(
            generate_vwap_trend_candidates(
                bars,
                symbols=[symbol for symbol in symbols if symbol.upper() in {"SPY", "QQQ"}],
                risk_dollars=risk_dollars,
                min_bars=6,
                slope_lookback=3,
                volume_lookback=5,
            )
        )

    return _cap_risk_for_notional(
        candidates,
        account_equity=account_equity,
        max_position_notional_pct=max_position_notional_pct,
    )


def _cap_risk_for_notional(
    candidates: list[dict[str, Any]],
    *,
    account_equity: float | None,
    max_position_notional_pct: float,
) -> list[dict[str, Any]]:
    if account_equity is None or account_equity <= 0:
        return candidates
    max_notional = account_equity * max_position_notional_pct
    capped: list[dict[str, Any]] = []
    for candidate in candidates:
        entry = float(candidate["planned_entry"])
        stop = float(candidate["stop"])
        risk_per_share = abs(entry - stop)
        if entry <= 0 or risk_per_share <= 0:
            capped.append(candidate)
            continue
        max_risk_for_notional = (max_notional / entry) * risk_per_share * 0.995
        current_risk = float(candidate["risk_dollars"])
        if max_risk_for_notional < current_risk:
            candidate = dict(candidate)
            checklist = dict(candidate.get("rule_checklist") or {})
            checklist["risk_dollars_capped_for_notional"] = True
            checklist["configured_risk_dollars"] = round(current_risk, 4)
            candidate["rule_checklist"] = checklist
            candidate["risk_dollars"] = round(max_risk_for_notional, 4)
        capped.append(candidate)
    return capped
