#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, time
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.daily_summary import format_daily_summary, max_drawdown_r  # noqa: E402
from trading_lab.lanes import is_portfolio_admitted  # noqa: E402
from trading_lab.market_calendar import XNYSCalendar  # noqa: E402

DB = ROOT / "journal" / "trading-lab.db"
SCANNER = ROOT / "data" / "processed" / "scanner-watchlist.json"
RUNTIME = ROOT / "data" / "processed" / "last-paper-watch.json"
ET = ZoneInfo("America/New_York")


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Agentic Trading Lab progress.")
    parser.add_argument("--succinct", action="store_true", help="Emit the compact market-close briefing")
    args = parser.parse_args()
    now = datetime.now(ET)
    calendar = XNYSCalendar()
    if not calendar.is_session(now.date()):
        print(
            f"Market closed — {now:%Y-%m-%d} (NYSE calendar). "
            "No trading session; no daily performance evaluation. "
            "Scheduled market inactivity is not a scanner failure."
        )
        return 0
    session_start = datetime.combine(now.date(), time(0, 0), ET).isoformat(timespec="seconds")
    if not DB.exists():
        print(f"Trading Lab progress — {now:%Y-%m-%d %I:%M %p %Z}\nDB missing: {DB}")
        return 1

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    proposals = [dict(r) for r in con.execute("SELECT * FROM proposals WHERE created_at >= ? AND status NOT LIKE '%quarantined%' ORDER BY id", (session_start,))]
    positions = [
        dict(r)
        for r in con.execute(
            """
            SELECT pp.* FROM paper_positions pp
            JOIN proposals p ON p.id = pp.proposal_id
            WHERE p.status NOT LIKE '%quarantined%'
            ORDER BY pp.id
            """
        )
    ]
    trades = [
        dict(r)
        for r in con.execute(
            """
            SELECT pt.* FROM paper_trades pt
            JOIN proposals p ON p.id = pt.proposal_id
            WHERE pt.created_at >= ?
              AND p.status NOT LIKE '%quarantined%'
              AND COALESCE(pt.mistake_category, '') NOT LIKE '%quarantined%'
            ORDER BY pt.id
            """,
            (session_start,),
        )
    ]
    active = [p for p in positions if p["status"] in {"pending_entry", "open"}]
    proposal_portfolio_admission = {
        int(proposal["id"]): is_portfolio_admitted(
            {"rule_checklist": json.loads(proposal["rule_checklist_json"] or "{}")}
        )
        for proposal in proposals
    }
    active_portfolio = [p for p in active if proposal_portfolio_admission.get(int(p["proposal_id"]), False)]
    by_strategy = Counter(p["strategy_id"] for p in proposals)
    by_status = Counter(p["status"] for p in positions)
    scanner = _load_scanner()
    closed_today = [p for p in positions if p["closed_at"] and str(p["closed_at"]) >= session_start and p["status"] == "closed"]
    portfolio_closed_today = [
        p for p in closed_today if proposal_portfolio_admission.get(int(p["proposal_id"]), False)
    ]
    total_r = sum(float(p["r_multiple"] or 0) for p in closed_today)
    total_pnl = sum(float(p["pnl"] or 0) for p in closed_today)

    if args.succinct:
        runtime = _load_json(RUNTIME)
        _opening, closing = calendar.session_bounds(now.date())
        # Off-session silence is expected, including after a 13:00 early close.
        health_reference = min(now, closing).timestamp()
        runtime_mtime = RUNTIME.stat().st_mtime if RUNTIME.exists() else 0
        runtime_stale = runtime_mtime > now.timestamp() or health_reference - runtime_mtime > 600
        timings = runtime.get("timings_ms") or {}
        strategy_stats: dict[str, dict[str, float]] = {}
        for position in closed_today:
            strategy = str(position.get("strategy_id") or "unknown")
            row = strategy_stats.setdefault(strategy, {"count": 0.0, "r": 0.0})
            row["count"] += 1
            row["r"] += float(position.get("r_multiple") or 0)
        labels = {
            "opening-range-breakout": "ORB",
            "vwap-trend-imbalance": "VWAP trend",
            "vwap-reclaim": "VWAP reclaim",
            "momentum-pullback": "Momentum",
        }
        strategy_lines = [
            f"{labels.get(strategy, strategy)} {int(stats['count'])}: {stats['r']:+.2f}R"
            for strategy, stats in sorted(strategy_stats.items())
        ]
        r_values = [float(position.get("r_multiple") or 0) for position in closed_today]
        portfolio_r_values = [float(position.get("r_multiple") or 0) for position in portfolio_closed_today]
        print(
            format_daily_summary(
                {
                    "date": now.date().isoformat(),
                    "last_scan_ok": bool(runtime.get("ok")),
                    "last_scan_stale": runtime_stale,
                    "scan_interval_minutes": 1,
                    "loop_ms": timings.get("total", 0),
                    "decision_ms": timings.get("decision", 0),
                    "broker_orders": runtime.get("broker_orders", 0),
                    "proposals": len(proposals),
                    "closes": len(closed_today),
                    "wins": sum(1 for value in r_values if value > 0),
                    "losses": sum(1 for value in r_values if value < 0),
                    "pnl": total_pnl,
                    "r": total_r,
                    "max_drawdown_r": max_drawdown_r(r_values),
                    "portfolio_closes": len(portfolio_closed_today),
                    "portfolio_wins": sum(1 for value in portfolio_r_values if value > 0),
                    "portfolio_losses": sum(1 for value in portfolio_r_values if value < 0),
                    "portfolio_pnl": sum(float(position.get("pnl") or 0) for position in portfolio_closed_today),
                    "portfolio_r": sum(portfolio_r_values),
                    "portfolio_max_drawdown_r": max_drawdown_r(portfolio_r_values),
                    "strategy_lines": strategy_lines,
                    "active_positions": len(active),
                    "portfolio_active_positions": len(active_portfolio),
                    "portfolio_position_limit": int(runtime.get("max_active_positions") or 2),
                    "errors": 0 if runtime.get("ok") and not runtime_stale else 1,
                    "blocker": "No strategy has passed walk-forward promotion gates.",
                }
            )
        )
        return 0

    lines = [
        f"Trading Lab progress — {now:%Y-%m-%d %I:%M %p %Z}",
        "Mode: paper proposal only; broker orders: 0; live trading: disabled",
        f"Research today: {len(proposals)} proposals, {len(trades)} simulated closes, PnL ${total_pnl:.2f}, R {total_r:.2f}",
        f"Active research positions: {len(active)}; portfolio-admitted: {len(active_portfolio)}/2",
        f"All position statuses: {dict(sorted(by_status.items()))}",
        f"Today's proposals by strategy: {dict(sorted(by_strategy.items()))}",
        f"Scanner watchlist: {', '.join(scanner.get('watchlist', [])[:15]) if scanner.get('watchlist') else 'not generated yet'}",
    ]
    if scanner.get("top_matches"):
        lines.append("Scanner top matches:")
        for row in scanner["top_matches"][:5]:
            reasons = ", ".join(row.get("why", []))
            lines.append(f"- {row['symbol']} score {row['score']} price {row['price']} change {row['change_pct']}% RVOL {row['relative_volume']} — {reasons}")
    if active:
        lines.append("Active:")
        for pos in active[-5:]:
            lines.append(
                f"- #{pos['id']} {pos['ticker']} {pos['strategy_id']} {pos['direction']} {pos['status']} entry {pos['entry']} stop {pos['stop']} target {pos['target']}"
            )
    if proposals:
        lines.append("Latest proposals:")
        for proposal in proposals[-5:]:
            checklist = json.loads(proposal["rule_checklist_json"] or "{}")
            cap = " capped-risk" if checklist.get("risk_dollars_capped_for_notional") else ""
            lines.append(
                f"- #{proposal['id']} {proposal['ticker']} {proposal['strategy_id']} {proposal['direction']} entry {proposal['planned_entry']} stop {proposal['stop']} target {proposal['target']}{cap}"
            )
    print("\n".join(lines))
    return 0


def _load_scanner() -> dict:
    if not SCANNER.exists():
        return {}
    try:
        return json.loads(SCANNER.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
