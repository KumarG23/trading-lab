from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from trading_lab.journal_store import JournalStore
from trading_lab.metrics import summarize_trades

ET = ZoneInfo("America/New_York")


def build_dashboard_snapshot(
    store: JournalStore,
    *,
    account_equity: float,
    live_enabled: bool,
    broker_orders_enabled: bool = False,
) -> dict[str, Any]:
    proposals = store.list_proposals()
    positions = store.list_paper_positions()
    trades = store.list_paper_trades()
    active_positions = [p for p in positions if p["status"] in {"pending_entry", "open"}]
    proposals_by_strategy = dict(sorted(Counter(p["strategy_id"] for p in proposals).items()))
    positions_by_status = dict(sorted(Counter(p["status"] for p in positions).items()))
    metrics = summarize_trades(trades)
    return {
        "generated_at": datetime.now(ET).isoformat(timespec="seconds"),
        "mode": "paper_proposal_only_no_orders" if not broker_orders_enabled else "broker_paper_execution",
        "account": {"paper_equity": account_equity},
        "safety": {
            "live_trading_enabled": live_enabled,
            "broker_orders_enabled": broker_orders_enabled,
            "real_money_requires_explicit_trade_approval": True,
        },
        "counts": {
            "proposals": len(proposals),
            "positions": len(positions),
            "active_positions": len(active_positions),
            "paper_trades": len(trades),
        },
        "proposals_by_strategy": proposals_by_strategy,
        "positions_by_status": positions_by_status,
        "metrics": metrics,
        "active_positions": [_position_card(p) for p in active_positions[-12:]],
        "latest_proposals": [_proposal_card(p) for p in proposals[-20:]][::-1],
        "latest_trades": [_trade_card(t) for t in trades[-20:]][::-1],
        "readiness": _readiness(live_enabled=live_enabled, broker_orders_enabled=broker_orders_enabled, trades=trades, proposals=proposals),
    }


def _readiness(*, live_enabled: bool, broker_orders_enabled: bool, trades: list[dict[str, Any]], proposals: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "proposal_mode": {
            "status": "ok" if proposals else "warming_up",
            "detail": "Strategy suite is logging proposals and simulated positions." if proposals else "Waiting for first proposal.",
        },
        "backtest_harness": {
            "status": "ok",
            "detail": "Historical replay harness exists; expand with larger data windows before promotion.",
        },
        "broker_paper_execution": {
            "status": "ok" if broker_orders_enabled else "blocked",
            "detail": "Blocked until order lifecycle, duplicate locks, and reconciliation are enabled." if not broker_orders_enabled else "Paper broker execution enabled.",
        },
        "live_execution": {
            "status": "forbidden" if not live_enabled else "armed",
            "detail": "Live trading requires Neal's explicit trade-level approval." if not live_enabled else "Live flag is on; verify explicit approval scope.",
        },
        "sample_size": {
            "status": "ok" if len(trades) >= 20 else "insufficient",
            "detail": f"{len(trades)}/20 closed simulated trades logged before strategy promotion review.",
        },
    }


def _proposal_card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "ticker": row["ticker"],
        "strategy_id": row["strategy_id"],
        "direction": row["direction"],
        "status": row["status"],
        "entry": row["planned_entry"],
        "stop": row["stop"],
        "target": row["target"],
        "trigger": row["trigger"],
    }


def _position_card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "ticker": row["ticker"],
        "strategy_id": row["strategy_id"],
        "direction": row["direction"],
        "status": row["status"],
        "entry": row["entry"],
        "stop": row["stop"],
        "target": row["target"],
        "position_size": row["position_size"],
        "risk_dollars": row["risk_dollars"],
        "pnl": row.get("pnl"),
        "r_multiple": row.get("r_multiple"),
    }


def _trade_card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "proposal_id": row["proposal_id"],
        "created_at": row["created_at"],
        "entry": row["actual_entry"],
        "exit": row["actual_exit"],
        "pnl": row["pnl"],
        "r": row["actual_r_multiple"],
        "exit_reason": row["exit_reason"],
        "rule_adherent": row["rule_adherent"],
    }
