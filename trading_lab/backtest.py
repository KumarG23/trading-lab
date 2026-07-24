from __future__ import annotations

from typing import Any

from trading_lab.fill_engine import simulate_position
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
    fee_per_share: float = 0.0,
    require_bullish_market_regime: bool = False,
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
        require_bullish_market_regime=require_bullish_market_regime,
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
        trade = _simulate_candidate(
            candidate,
            session_bars,
            position_size=float(decision.position_size or 0.0),
            entry_slippage_bps=entry_slippage_bps,
            exit_slippage_bps=exit_slippage_bps,
            fee_per_share=fee_per_share,
        )
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
        "costs": {"fee_per_share": fee_per_share},
        "require_bullish_market_regime": require_bullish_market_regime,
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
    require_bullish_market_regime: bool,
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
                require_bullish_market_regime=require_bullish_market_regime,
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
    fee_per_share: float,
) -> dict[str, Any] | None:
    outcome = simulate_position(
        candidate,
        bars,
        position_size=position_size,
        entry_slippage_bps=entry_slippage_bps,
        exit_slippage_bps=exit_slippage_bps,
        fee_per_share=fee_per_share,
    )
    if outcome["fill_status"] != "filled":
        return None
    return {
        "ticker": str(candidate["ticker"]).upper(),
        "strategy_id": candidate["strategy_id"],
        "direction": candidate["direction"],
        "created_at": str((candidate.get("market_context") or {}).get("signal_timestamp") or ""),
        "entered_at": outcome["entered_at"],
        "closed_at": outcome["closed_at"],
        "actual_entry": outcome["actual_entry"],
        "actual_exit": outcome["actual_exit"],
        "position_size": round(position_size, 4),
        "pnl": outcome["net_dollars"],
        "fees": outcome["fees"],
        "actual_r_multiple": outcome["net_r"],
        "rule_adherent": True,
        "exit_reason": outcome["exit_reason"],
        "same_bar_ambiguity": outcome["same_bar_ambiguity"],
    }
