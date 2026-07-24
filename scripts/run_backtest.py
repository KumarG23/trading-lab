#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.alpaca_client import AlpacaClient  # noqa: E402
from trading_lab.backtest import run_strategy_backtest  # noqa: E402
from trading_lab.config import LabConfig  # noqa: E402

ET = ZoneInfo("America/New_York")
DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN", "GOOGL", "SPY", "QQQ"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a historical strategy-suite backtest using Alpaca 1-minute bars.")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--strategies", default="orb,vwap")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--risk-dollars", type=float, default=None)
    parser.add_argument("--entry-slippage-bps", type=float, default=5.0)
    parser.add_argument("--exit-slippage-bps", type=float, default=10.0)
    parser.add_argument("--fee-per-share", type=float, default=0.005)
    parser.add_argument("--bullish-regime-filter", action="store_true", help="Require SPY above a rising intraday VWAP for long candidates")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    cfg = LabConfig.from_env_file(ROOT / ".env")
    if not cfg.alpaca_configured:
        print(json.dumps({"ok": False, "error": "alpaca_not_configured"}, indent=2))
        return 2
    if cfg.live_trading_enabled:
        print(json.dumps({"ok": False, "error": "live_trading_enabled_refused_by_backtest"}, indent=2))
        return 3

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=args.days)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    strategies = [s.strip().lower() for s in args.strategies.split(",") if s.strip()]
    client = AlpacaClient(base_url=cfg.alpaca_base_url, api_key=cfg.alpaca_api_key or "", secret_key=cfg.alpaca_secret_key or "")
    bars = client.fetch_stock_bars(
        symbols,
        timeframe="1Min",
        start=start_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
        end=end_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
        batch_size=1,
    )
    result = run_strategy_backtest(
        bars,
        symbols=symbols,
        enabled_strategies=strategies,
        account_equity=cfg.account_equity,
        risk_dollars=args.risk_dollars if args.risk_dollars is not None else round(cfg.account_equity * 0.01, 2),
        entry_slippage_bps=args.entry_slippage_bps,
        exit_slippage_bps=args.exit_slippage_bps,
        fee_per_share=args.fee_per_share,
        require_bullish_market_regime=args.bullish_regime_filter,
    )
    result.update({
        "ok": True,
        "period": {"start": start_dt.astimezone(ET).isoformat(timespec="seconds"), "end": end_dt.astimezone(ET).isoformat(timespec="seconds")},
        "mode": "historical_backtest_no_orders",
        "broker_orders": 0,
    })
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
