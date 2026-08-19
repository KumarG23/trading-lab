#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.alpaca_client import AlpacaClient  # noqa: E402
from trading_lab.autonomous_runner import AutonomousRunner  # noqa: E402
from trading_lab.config import LabConfig  # noqa: E402
from trading_lab.counterfactual import resolve_candidate_events  # noqa: E402
from trading_lab.data_quality import validate_minute_bars  # noqa: E402
from trading_lab.journal_store import JournalStore  # noqa: E402
from trading_lab.local_worker import LocalAIWorker  # noqa: E402
from trading_lab.market_calendar import XNYSCalendar, lifecycle_cutoffs  # noqa: E402
from trading_lab.paper_lifecycle import completed_bar_end, entry_window_open, market_is_open, update_paper_positions  # noqa: E402
from trading_lab.provenance import repository_code_sha, stable_config_hash  # noqa: E402
from trading_lab.run_telemetry import write_run_telemetry  # noqa: E402
from trading_lab.strategy_suite import generate_strategy_candidates  # noqa: E402
from trading_lab.training_export import export_training_examples  # noqa: E402
from trading_lab.training_memory import TrainingMemory  # noqa: E402
from trading_lab.watchlist import load_scanner_context, load_symbols  # noqa: E402

ET = ZoneInfo("America/New_York")
DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN", "GOOGL", "SPY", "QQQ"]



def main() -> int:
    run_started = perf_counter()
    parser = argparse.ArgumentParser(description="Generate and log Alpaca paper/proposal strategy candidates. Places no broker orders.")
    parser.add_argument("--symbols", default=",".join(DEFAULT_WATCHLIST), help="Comma-separated fallback symbols")
    parser.add_argument("--watchlist-file", type=Path, default=ROOT / "data" / "processed" / "scanner-watchlist.json", help="Dynamic scanner watchlist JSON; falls back to --symbols if missing")
    parser.add_argument("--db", type=Path, default=ROOT / "journal" / "trading-lab.db")
    parser.add_argument("--risk-dollars", type=float, default=None, help="Risk per proposal. Defaults to 1%% of configured paper equity.")
    parser.add_argument("--opening-range-minutes", type=int, default=5)
    parser.add_argument("--strategies", default="orb,vwap,reclaim,momentum", help="Comma-separated strategy aliases: orb,vwap,reclaim,momentum")
    parser.add_argument("--bullish-regime-filter", action="store_true", help="Require SPY above rising intraday VWAP for long candidates")
    parser.add_argument("--no-local-ai", action="store_true")
    parser.add_argument("--max-reviews-per-run", type=int, default=50, help="Research-candidate runaway cap per tick")
    parser.add_argument("--max-active-positions", type=int, default=2, help="Cap portfolio-admitted positions; research-only positions continue to be tracked")
    parser.add_argument("--max-trades-per-day", type=int, default=50, help="Research close/proposal runaway cap per day")
    parser.add_argument("--entry-slippage-bps", type=float, default=5.0)
    parser.add_argument("--exit-slippage-bps", type=float, default=10.0)
    parser.add_argument("--fee-per-share", type=float, default=0.005)
    parser.add_argument("--training-output", type=Path, default=ROOT / "training" / "proposal_outcomes.jsonl", help="Derived JSONL research-provenance export; not predictive-training evidence")
    parser.add_argument("--telemetry-output", type=Path, default=ROOT / "data" / "processed" / "last-paper-watch.json", help="Latest scan/decision latency telemetry")
    parser.add_argument("--no-training-export", action="store_true", help="Skip updating the derived training JSONL")
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

    symbols = load_symbols(args.symbols, watchlist_file=args.watchlist_file)
    scanner_context = load_scanner_context(args.watchlist_file, decision_at=now_et)
    calendar = XNYSCalendar()
    market_open_et, _market_close_et = calendar.session_bounds(now_et.date())
    no_new_entries_after, flatten_at = lifecycle_cutoffs(calendar, now_et.date())
    start = market_open_et.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    end = completed_bar_end(now_et).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    client = AlpacaClient(base_url=cfg.alpaca_base_url, api_key=cfg.alpaca_api_key or "", secret_key=cfg.alpaca_secret_key or "")
    fetch_started = perf_counter()
    bars = client.fetch_stock_bars(symbols, timeframe="1Min", start=start, end=end)
    fetch_finished = perf_counter()
    data_quality = validate_minute_bars(bars)
    if data_quality["fatal"]:
        payload = {
            "ok": False, "mode": "paper_proposal_only_no_orders", "broker_orders": 0,
            "error": "market_data_quality_gate", "data_quality": data_quality,
        }
        write_run_telemetry(args.telemetry_output, payload)
        _emit(payload, args.quiet_no_events)
        return 4
    store = JournalStore(args.db)

    lifecycle_started = perf_counter()
    lifecycle = update_paper_positions(
        store,
        bars,
        no_new_entries_after=no_new_entries_after,
        flatten_at=flatten_at,
        entry_slippage_bps=args.entry_slippage_bps,
        exit_slippage_bps=args.exit_slippage_bps,
        fee_per_share=args.fee_per_share,
    )
    lifecycle_finished = perf_counter()
    risk_dollars = args.risk_dollars if args.risk_dollars is not None else round(cfg.account_equity * 0.01, 2)
    strategies = [s.strip().lower() for s in args.strategies.split(",") if s.strip()]
    strategy_started = perf_counter()
    candidates = generate_strategy_candidates(
        bars,
        symbols=symbols,
        enabled_strategies=strategies,
        risk_dollars=risk_dollars,
        opening_range_minutes=args.opening_range_minutes,
        account_equity=cfg.account_equity,
        live_latest_only=True,
        require_bullish_market_regime=args.bullish_regime_filter,
        scanner_context=scanner_context,
    )
    if not entry_window_open(now_et, no_new_entries_after):
        candidates = []
    strategy_finished = perf_counter()

    training_memory = TrainingMemory(ROOT / "training" / "claude_bot_sanitized_examples.jsonl")
    worker = None if args.no_local_ai else LocalAIWorker(
        base_url=cfg.local_model_base_url,
        model=cfg.local_model,
        training_memory=training_memory,
        timeout=120,
    )
    decision_started = perf_counter()
    run_config = {
        "symbols": symbols,
        "strategies": strategies,
        "risk_dollars": risk_dollars,
        "opening_range_minutes": args.opening_range_minutes,
        "bullish_regime_filter": args.bullish_regime_filter,
        "max_reviews_per_run": args.max_reviews_per_run,
        "max_active_positions": args.max_active_positions,
        "portfolio_admission_enabled": cfg.portfolio_admission_enabled,
        "max_trades_per_day": args.max_trades_per_day,
        "entry_slippage_bps": args.entry_slippage_bps,
        "exit_slippage_bps": args.exit_slippage_bps,
        "fee_per_share": args.fee_per_share,
    }
    proposal_ids = AutonomousRunner(
        store=store,
        worker=worker,
        account_equity=cfg.account_equity,
        max_reviews_per_run=args.max_reviews_per_run,
        max_active_positions=args.max_active_positions,
        portfolio_admission_enabled=cfg.portfolio_admission_enabled,
        max_trades_per_day=args.max_trades_per_day,
        run_provenance={
            "run_id": str(uuid4()),
            "decision_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "code_sha": repository_code_sha(ROOT),
            "config_hash": stable_config_hash(run_config),
        },
    ).process_candidates(candidates)
    decision_finished = perf_counter()
    counterfactual = resolve_candidate_events(
        store,
        bars,
        session_complete=now_et.time() >= datetime.strptime(flatten_at, "%H:%M").time(),
        entry_slippage_bps=args.entry_slippage_bps,
        exit_slippage_bps=args.exit_slippage_bps,
        fee_per_share=args.fee_per_share,
    )
    export_started = perf_counter()
    training_export = None if args.no_training_export else export_training_examples(args.db, args.training_output)
    export_finished = perf_counter()
    timings_ms = {
        "fetch": round((fetch_finished - fetch_started) * 1000, 2),
        "lifecycle": round((lifecycle_finished - lifecycle_started) * 1000, 2),
        "strategy": round((strategy_finished - strategy_started) * 1000, 2),
        "decision": round((decision_finished - decision_started) * 1000, 2),
        "training_export": round((export_finished - export_started) * 1000, 2),
        "total": round((export_finished - run_started) * 1000, 2),
    }
    payload = {
        "ok": True,
        "mode": "paper_proposal_only_no_orders",
        "broker_orders": 0,
        "paper_equity": cfg.account_equity,
        "risk_dollars": risk_dollars,
        "strategies": strategies,
        "bullish_regime_filter": args.bullish_regime_filter,
        "symbols": symbols,
        "scanner_context_symbols": len(scanner_context),
        "bars": len(bars),
        "data_quality": data_quality,
        "session_cutoffs": {"no_new_entries_after": no_new_entries_after, "flatten_at": flatten_at},
        "candidates": len(candidates),
        "max_reviews_per_run": args.max_reviews_per_run,
        "max_active_positions": args.max_active_positions,
        "portfolio_admission_enabled": cfg.portfolio_admission_enabled,
        "max_trades_per_day": args.max_trades_per_day,
        "fill_costs": {
            "entry_slippage_bps": args.entry_slippage_bps,
            "exit_slippage_bps": args.exit_slippage_bps,
            "fee_per_share": args.fee_per_share,
        },
        "logged_proposal_ids": proposal_ids,
        "lifecycle": lifecycle,
        "counterfactual": counterfactual,
        "training_export": training_export,
        "start": start,
        "end": end,
        "timings_ms": timings_ms,
    }
    write_run_telemetry(args.telemetry_output, payload)
    if args.quiet_no_events and not proposal_ids and not lifecycle["events"] and not candidates:
        return 0
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _emit(payload: dict, quiet: bool) -> None:
    if quiet and payload.get("skipped") == "market_closed":
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
