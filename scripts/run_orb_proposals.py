#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, time, timezone
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.alpaca_client import AlpacaClient  # noqa: E402
from trading_lab.autonomous_runner import AutonomousRunner  # noqa: E402
from trading_lab.config import LabConfig  # noqa: E402
from trading_lab.journal_store import JournalStore  # noqa: E402
from trading_lab.local_worker import LocalAIWorker  # noqa: E402
from trading_lab.opening_range_breakout import generate_orb_candidates  # noqa: E402
from trading_lab.paper_lifecycle import market_is_open, update_paper_positions  # noqa: E402
from trading_lab.training_memory import TrainingMemory  # noqa: E402

ET = ZoneInfo("America/New_York")
DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN", "GOOGL", "SPY", "QQQ"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and log Alpaca paper/proposal ORB candidates. Places no broker orders.")
    parser.add_argument("--symbols", default=",".join(DEFAULT_WATCHLIST), help="Comma-separated symbols")
    parser.add_argument("--db", type=Path, default=ROOT / "journal" / "trading-lab.db")
    parser.add_argument("--risk-dollars", type=float, default=None, help="Risk per proposal. Defaults to 1% of configured paper equity.")
    parser.add_argument("--opening-range-minutes", type=int, default=5)
    parser.add_argument("--no-local-ai", action="store_true")
    parser.add_argument("--ignore-market-hours", action="store_true")
    parser.add_argument("--quiet-no-events", action="store_true", help="Print nothing when no proposals/lifecycle events occur")
    args = parser.parse_args()

    cfg = LabConfig.from_env_file(ROOT / ".env")
    if not cfg.alpaca_configured:
        _emit({"ok": False, "error": "alpaca_not_configured"}, args.quiet_no_events)
        return 2
    if cfg.live_trading_enabled:
        _emit({"ok": False, "error": "live_trading_enabled_refused_by_orb_proposal_loop"}, args.quiet_no_events)
        return 3
    now_et = datetime.now(ET)
    if not args.ignore_market_hours and not market_is_open(now_et):
        _emit({"ok": True, "mode": "paper_proposal_only_no_orders", "skipped": "market_closed", "time_et": now_et.isoformat(timespec="seconds")}, args.quiet_no_events)
        return 0

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    market_open_et = datetime.combine(now_et.date(), time(9, 30), ET)
    start = market_open_et.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    end = now_et.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    client = AlpacaClient(base_url=cfg.alpaca_base_url, api_key=cfg.alpaca_api_key or "", secret_key=cfg.alpaca_secret_key or "")
    bars = client.fetch_stock_bars(symbols, timeframe="1Min", start=start, end=end)
    store = JournalStore(args.db)

    lifecycle = update_paper_positions(store, bars)
    risk_dollars = args.risk_dollars if args.risk_dollars is not None else round(cfg.account_equity * 0.01, 2)
    candidates = generate_orb_candidates(bars, opening_range_minutes=args.opening_range_minutes, risk_dollars=risk_dollars)

    training_memory = TrainingMemory(ROOT / "training" / "claude_bot_sanitized_examples.jsonl")
    worker = None if args.no_local_ai else LocalAIWorker(
        base_url=cfg.local_model_base_url,
        model=cfg.local_model,
        training_memory=training_memory,
        timeout=120,
    )
    proposal_ids = AutonomousRunner(store=store, worker=worker, account_equity=cfg.account_equity).process_candidates(candidates)
    payload = {
        "ok": True,
        "mode": "paper_proposal_only_no_orders",
        "broker_orders": 0,
        "paper_equity": cfg.account_equity,
        "risk_dollars": risk_dollars,
        "symbols": symbols,
        "bars": len(bars),
        "candidates": len(candidates),
        "logged_proposal_ids": proposal_ids,
        "lifecycle": lifecycle,
        "start": start,
        "end": end,
    }
    if args.quiet_no_events and not proposal_ids and not lifecycle["events"]:
        return 0
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _emit(payload: dict, quiet: bool) -> None:
    if quiet and payload.get("skipped") == "market_closed":
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
