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
from trading_lab.config import LabConfig  # noqa: E402
from trading_lab.market_calendar import XNYSCalendar  # noqa: E402
from trading_lab.universe_scanner import (  # noqa: E402
    CORE_SYMBOLS,
    DEFAULT_SCAN_UNIVERSE,
    completed_bar_cutoff,
    filter_bars_before_cutoff,
    filter_stocks_in_play,
    pick_watchlist,
    scanner_content_sha256,
    score_universe,
)

ET = ZoneInfo("America/New_York")
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "scanner-watchlist.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a broader small-account-friendly universe and write today's dynamic watchlist.")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SCAN_UNIVERSE), help="Comma-separated scan universe")
    parser.add_argument("--days", type=int, default=6)
    parser.add_argument("--max-symbols", type=int, default=30)
    parser.add_argument("--min-price", type=float, default=2.0)
    parser.add_argument("--max-price", type=float, default=300.0)
    parser.add_argument("--min-dollar-volume", type=float, default=250_000.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    now = datetime.now(ET)
    if not XNYSCalendar().is_session(now.date()):
        print(json.dumps({"ok": True, "skipped": "market_closed", "session": now.date().isoformat()}))
        return 0

    cfg = LabConfig.from_env_file(ROOT / ".env")
    if not cfg.alpaca_configured:
        print(json.dumps({"ok": False, "error": "alpaca_not_configured"}, indent=2))
        return 2
    if cfg.live_trading_enabled:
        print(json.dumps({"ok": False, "error": "live_trading_enabled_refused_by_universe_scanner"}, indent=2))
        return 3
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    end_dt = completed_bar_cutoff(datetime.now(timezone.utc))
    start_dt = end_dt - timedelta(days=args.days)
    client = AlpacaClient(base_url=cfg.alpaca_base_url, api_key=cfg.alpaca_api_key or "", secret_key=cfg.alpaca_secret_key or "")
    bars = client.fetch_stock_bars(
        symbols,
        timeframe="1Min",
        start=start_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
        end=end_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
        batch_size=1,
    )
    bars = filter_bars_before_cutoff(bars, cutoff=end_dt)
    scored = score_universe(
        bars,
        symbols=symbols,
        min_price=args.min_price,
        max_price=args.max_price,
        min_dollar_volume=args.min_dollar_volume,
    )
    stocks_in_play = filter_stocks_in_play(scored)
    watchlist = pick_watchlist(stocks_in_play, core_symbols=CORE_SYMBOLS, max_symbols=args.max_symbols)
    top_matches = scored[:30]
    content_hash = scanner_content_sha256(
        rows=top_matches,
        watchlist=watchlist,
        data_cutoff_at=end_dt,
    )
    payload = {
        "ok": True,
        "mode": "dynamic_universe_scan_no_orders",
        "generated_at": datetime.now(ET).isoformat(timespec="seconds"),
        "data_cutoff_at": end_dt.isoformat(timespec="seconds"),
        "scanner_content_sha256": content_hash,
        "period": {"start": start_dt.astimezone(ET).isoformat(timespec="seconds"), "end": end_dt.astimezone(ET).isoformat(timespec="seconds")},
        "scan_universe_count": len(symbols),
        "bars": len(bars),
        "watchlist": watchlist,
        "stocks_in_play_count": len(stocks_in_play),
        "top_matches": top_matches,
        "filters": {
            "min_price": args.min_price,
            "max_price": args.max_price,
            "min_dollar_volume": args.min_dollar_volume,
            "max_symbols": args.max_symbols,
        },
        "broker_orders": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(_format_report(payload, args.output))
    return 0


def _format_report(payload: dict, output: Path) -> str:
    lines = [
        f"Trading Lab premarket scanner — {payload['generated_at']}",
        f"Universe scanned: {payload['scan_universe_count']} · watchlist: {len(payload['watchlist'])} · broker orders: 0",
        "Watchlist: " + ", ".join(payload["watchlist"][:30]),
        "Top scanner matches:",
    ]
    for row in payload["top_matches"][:10]:
        reasons = ", ".join(row.get("why", [])) or "candidate"
        lines.append(f"- {row['symbol']} score {row['score']} price {row['price']} change {row['change_pct']}% RVOL {row['relative_volume']} — {reasons}")
    lines.append(f"Output: {output}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
