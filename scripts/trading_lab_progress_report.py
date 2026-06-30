#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "journal" / "trading-lab.db"
SCANNER = ROOT / "data" / "processed" / "scanner-watchlist.json"
ET = ZoneInfo("America/New_York")


def main() -> int:
    now = datetime.now(ET)
    session_start = datetime.combine(now.date(), time(0, 0), ET).isoformat(timespec="seconds")
    if not DB.exists():
        print(f"Trading Lab progress — {now:%Y-%m-%d %I:%M %p %Z}\nDB missing: {DB}")
        return 1

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    proposals = [dict(r) for r in con.execute("SELECT * FROM proposals WHERE created_at >= ? ORDER BY id", (session_start,))]
    positions = [dict(r) for r in con.execute("SELECT * FROM paper_positions ORDER BY id")]
    trades = [dict(r) for r in con.execute("SELECT * FROM paper_trades WHERE created_at >= ? ORDER BY id", (session_start,))]
    active = [p for p in positions if p["status"] in {"pending_entry", "open"}]
    by_strategy = Counter(p["strategy_id"] for p in proposals)
    by_status = Counter(p["status"] for p in positions)
    scanner = _load_scanner()
    closed_today = [p for p in positions if p["closed_at"] and str(p["closed_at"]) >= session_start and p["status"] == "closed"]
    total_r = sum(float(p["r_multiple"] or 0) for p in closed_today)
    total_pnl = sum(float(p["pnl"] or 0) for p in closed_today)

    lines = [
        f"Trading Lab progress — {now:%Y-%m-%d %I:%M %p %Z}",
        "Mode: paper proposal only; broker orders: 0; live trading: disabled",
        f"Today: {len(proposals)} proposals, {len(trades)} simulated closes, PnL ${total_pnl:.2f}, R {total_r:.2f}",
        f"Active simulated positions: {len(active)}",
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


if __name__ == "__main__":
    raise SystemExit(main())
