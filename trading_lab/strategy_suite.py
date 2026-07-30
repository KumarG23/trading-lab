from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from trading_lab.market_regime import bullish_market_regime, market_regime_label
from trading_lab.momentum_pullback import generate_momentum_pullback_candidates
from trading_lab.opening_range_breakout import generate_orb_candidates
from trading_lab.vwap_reclaim import generate_vwap_reclaim_candidates
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
    live_latest_only: bool = False,
    require_bullish_market_regime: bool = False,
) -> list[dict[str, Any]]:
    enabled = {strategy.strip().lower() for strategy in enabled_strategies}
    candidates: list[dict[str, Any]] = []

    if "orb" in enabled or "opening-range-breakout" in enabled:
        candidates.extend(
            generate_orb_candidates(
                bars,
                opening_range_minutes=opening_range_minutes,
                risk_dollars=risk_dollars,
                latest_only=live_latest_only,
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
    if "reclaim" in enabled or "vwap-reclaim" in enabled:
        candidates.extend(
            generate_vwap_reclaim_candidates(
                bars,
                symbols=symbols,
                risk_dollars=risk_dollars,
            )
        )
    if "momentum" in enabled or "momentum-pullback" in enabled:
        candidates.extend(
            generate_momentum_pullback_candidates(
                bars,
                symbols=symbols,
                risk_dollars=risk_dollars,
            )
        )

    if require_bullish_market_regime and not bullish_market_regime(bars):
        candidates = [candidate for candidate in candidates if str(candidate.get("direction") or "").lower() != "long"]

    regime = market_regime_label(bars)
    for candidate in candidates:
        context = dict(candidate.get("market_context") or {})
        context["regime"] = regime
        _enrich_decision_context(candidate, context, bars)
        candidate["market_context"] = context

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


def _enrich_decision_context(candidate: dict[str, Any], context: dict[str, Any], bars: list[dict[str, Any]]) -> None:
    """Add model inputs observable at signal time; never inspect future bars."""
    signal = str(context.get("signal_timestamp") or "")
    signal_at = _timestamp_utc(signal)
    symbol = str(candidate.get("ticker") or "").upper()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bar in bars:
        if _timestamp_utc(bar.get("timestamp")) <= signal_at:
            grouped[str(bar.get("symbol") or "").upper()].append(bar)

    visible = sorted(grouped.get(symbol, []), key=lambda row: _timestamp_utc(row.get("timestamp")))
    if visible:
        current = visible[-1]
        close = float(current["close"])
        high = float(current["high"])
        low = float(current["low"])
        volume = float(current.get("volume") or 0.0)
        context.setdefault("current_volume", volume)
        context.setdefault("volume", volume)
        context.setdefault("close", close)
        context.setdefault("dollar_volume", close * volume)
        context.setdefault("high", high)
        context.setdefault("low", low)
        context.setdefault("range_pct", (high - low) / close if close else 0.0)
        if len(visible) >= 2:
            context.setdefault("previous_close", float(visible[-2]["close"]))
        if len(visible) >= 4:
            context.setdefault("close_3_bars_ago", float(visible[-4]["close"]))
        if len(visible) >= 6:
            context.setdefault("close_5_bars_ago", float(visible[-6]["close"]))

        recent = visible[-15:]
        true_ranges: list[float] = []
        for index, bar in enumerate(recent):
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])
            previous = float(recent[index - 1]["close"]) if index else None
            true_ranges.append(
                max(bar_high - bar_low, abs(bar_high - previous), abs(bar_low - previous))
                if previous is not None else bar_high - bar_low
            )
        if true_ranges:
            context.setdefault("atr", mean(true_ranges[-14:]))

    market_rows = grouped.get("SPY") or grouped.get("QQQ") or []
    market = sorted(market_rows, key=lambda row: _timestamp_utc(row.get("timestamp")))
    if market:
        first = float(market[0].get("open") or market[0]["close"])
        latest = float(market[-1]["close"])
        context.setdefault("market_return", (latest - first) / first if first else 0.0)


def _timestamp_utc(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
