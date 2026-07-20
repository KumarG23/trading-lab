from __future__ import annotations

from typing import Any

from trading_lab.metrics import summarize_trades
from trading_lab.policy_gate import PolicyGate
from trading_lab.strategy_suite import generate_strategy_candidates


def run_strategy_backtest(
    bars: list[dict[str, Any]],
    *,
    symbols: list[str],
    enabled_strategies: list[str],
    account_equity: float,
    risk_dollars: float,
    opening_range_minutes: int = 5,
    entry_slippage_bps: float = 0.0,
    exit_slippage_bps: float = 0.0,
) -> dict[str, Any]:
    """Replay strategy candidates against historical bars.

    This intentionally uses the same strategy suite and policy gate as live
    proposal mode, then applies a simple conservative OHLC lifecycle. It is not
    a tick-accurate exchange simulator. It is the first sieve for killing bad
    ideas before they get broker-paper privileges.
    """
    ordered = sorted(bars, key=lambda item: (str(item["timestamp"]), str(item["symbol"]).upper()))
    candidate_sessions = _generate_replay_candidates(
        ordered,
        symbols=symbols,
        enabled_strategies=enabled_strategies,
        risk_dollars=risk_dollars,
        opening_range_minutes=opening_range_minutes,
        account_equity=account_equity,
    )
    candidates = [candidate for candidate, _session_bars in candidate_sessions]
    gate = PolicyGate(account_equity=account_equity)
    trades: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for candidate, session_bars in candidate_sessions:
        decision = gate.validate(candidate)
        if not decision.ok:
            rejected.append({"ticker": candidate.get("ticker"), "strategy_id": candidate.get("strategy_id"), "violations": decision.violations})
            continue
        trade = _simulate_candidate(candidate, session_bars, position_size=float(decision.position_size or 0.0), entry_slippage_bps=entry_slippage_bps, exit_slippage_bps=exit_slippage_bps)
        if trade:
            trades.append(trade)
    return {
        "symbols": symbols,
        "strategies": enabled_strategies,
        "bars": len(ordered),
        "candidates": len(candidates),
        "proposals": len(candidates) - len(rejected),
        "rejected": rejected,
        "trades": len(trades),
        "slippage": {"entry_bps": entry_slippage_bps, "exit_bps": exit_slippage_bps},
        "metrics": summarize_trades(trades),
        "trade_rows": trades,
    }


def _generate_replay_candidates(
    bars: list[dict[str, Any]],
    *,
    symbols: list[str],
    enabled_strategies: list[str],
    risk_dollars: float,
    opening_range_minutes: int,
    account_equity: float,
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    sessions: dict[str, list[dict[str, Any]]] = {}
    for bar in bars:
        session = str(bar["timestamp"])[:10]
        sessions.setdefault(session, []).append(bar)
    replay: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for session_bars in sessions.values():
        ordered_session = sorted(session_bars, key=lambda item: (str(item["timestamp"]), str(item["symbol"]).upper()))
        timestamps = sorted({str(bar["timestamp"]) for bar in ordered_session})
        seen: set[tuple[str, str, str]] = set()
        for timestamp in timestamps:
            visible = [bar for bar in ordered_session if str(bar["timestamp"]) <= timestamp]
            candidates = generate_strategy_candidates(
                visible,
                symbols=symbols,
                enabled_strategies=enabled_strategies,
                risk_dollars=risk_dollars,
                opening_range_minutes=opening_range_minutes,
                account_equity=account_equity,
                live_latest_only=True,
            )
            for candidate in candidates:
                key = (
                    str(candidate["strategy_id"]),
                    str(candidate["ticker"]),
                    str(candidate["direction"]),
                )
                if key in seen:
                    continue
                seen.add(key)
                replay.append((candidate, ordered_session))
    return replay


def _simulate_candidate(
    candidate: dict[str, Any],
    bars: list[dict[str, Any]],
    *,
    position_size: float,
    entry_slippage_bps: float,
    exit_slippage_bps: float,
) -> dict[str, Any] | None:
    symbol = str(candidate["ticker"]).upper()
    direction = str(candidate["direction"])
    signal_ts = str((candidate.get("market_context") or {}).get("signal_timestamp") or "")
    planned_entry = float(candidate["planned_entry"])
    stop = float(candidate["stop"])
    target = float(candidate["target"])
    entry = _apply_slippage(planned_entry, direction=direction, kind="entry", bps=entry_slippage_bps)
    entered = False
    entered_at = None
    for bar in bars:
        if str(bar["symbol"]).upper() != symbol:
            continue
        ts = str(bar["timestamp"])
        if signal_ts and ts <= signal_ts:
            continue
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        if not entered:
            if direction == "long" and high >= planned_entry:
                entered = True
                entered_at = ts
            elif direction == "short" and low <= planned_entry:
                entered = True
                entered_at = ts
            else:
                continue
        exit_reason = None
        exit_price = None
        if direction == "long":
            if low <= stop:
                exit_reason = "stop"
                exit_price = _apply_slippage(stop, direction=direction, kind="exit", bps=exit_slippage_bps)
            elif high >= target:
                exit_reason = "target"
                exit_price = _apply_slippage(target, direction=direction, kind="exit", bps=exit_slippage_bps)
        else:
            if high >= stop:
                exit_reason = "stop"
                exit_price = _apply_slippage(stop, direction=direction, kind="exit", bps=exit_slippage_bps)
            elif low <= target:
                exit_reason = "target"
                exit_price = _apply_slippage(target, direction=direction, kind="exit", bps=exit_slippage_bps)
        if exit_reason and exit_price is not None:
            pnl = (exit_price - entry) * position_size if direction == "long" else (entry - exit_price) * position_size
            risk_per_share = abs(entry - stop)
            actual_r = pnl / (risk_per_share * position_size) if risk_per_share and position_size else 0.0
            return {
                "ticker": symbol,
                "strategy_id": candidate["strategy_id"],
                "direction": direction,
                "created_at": signal_ts,
                "entered_at": entered_at,
                "closed_at": ts,
                "actual_entry": round(entry, 4),
                "actual_exit": round(exit_price, 4),
                "position_size": round(position_size, 4),
                "pnl": round(pnl, 4),
                "actual_r_multiple": round(actual_r, 4),
                "rule_adherent": True,
                "exit_reason": exit_reason,
                "close_at_bar": close,
            }
    return None


def _apply_slippage(price: float, *, direction: str, kind: str, bps: float) -> float:
    if bps <= 0:
        return price
    rate = bps / 10000.0
    if kind == "entry":
        return price * (1 + rate) if direction == "long" else price * (1 - rate)
    return price * (1 - rate) if direction == "long" else price * (1 + rate)
