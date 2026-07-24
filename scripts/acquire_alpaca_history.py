#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.alpaca_client import AlpacaClient  # noqa: E402
from trading_lab.config import LabConfig  # noqa: E402
from trading_lab.provenance import repository_code_sha  # noqa: E402
from trading_lab.raw_cache import write_immutable_bar_chunk  # noqa: E402

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "AMZN", "GOOGL", "SPY", "QQQ"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire licensed Alpaca IEX minute bars into immutable monthly chunks.")
    parser.add_argument("--start", required=True, help="Inclusive YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Exclusive YYYY-MM-DD")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data" / "raw" / "alpaca-iex-1min")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "processed" / "alpaca-raw-manifest.json")
    args = parser.parse_args()
    cfg = LabConfig.from_env_file(ROOT / ".env")
    if not cfg.alpaca_configured or cfg.live_trading_enabled:
        print(json.dumps({"ok": False, "error": "paper_credentials_required_and_live_must_be_disabled"}))
        return 2
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if end <= start:
        raise ValueError("end must be after start")
    symbols = sorted({item.strip().upper() for item in args.symbols.split(",") if item.strip()})
    client = AlpacaClient(
        base_url=cfg.alpaca_base_url,
        api_key=cfg.alpaca_api_key or "",
        secret_key=cfg.alpaca_secret_key or "",
    )
    chunks = []
    errors = []
    for month_start, month_end in _months(start, end):
        period = month_start.strftime("%Y-%m")
        fetch_start = max(start, month_start)
        fetch_end = min(end, month_end)
        for symbol in symbols:
            try:
                bars = client.fetch_stock_bars(
                    [symbol], timeframe="1Min",
                    start=datetime.combine(fetch_start, datetime.min.time(), timezone.utc).isoformat().replace("+00:00", "Z"),
                    end=datetime.combine(fetch_end, datetime.min.time(), timezone.utc).isoformat().replace("+00:00", "Z"),
                    feed="iex", batch_size=1,
                )
                chunks.append(write_immutable_bar_chunk(
                    args.raw_root, symbol=symbol, period=period, bars=bars, source="alpaca-iex",
                ))
            except Exception as exc:
                errors.append({"symbol": symbol, "period": period, "error_type": type(exc).__name__, "error": str(exc)[:300]})
    manifest = {
        "manifest_version": "alpaca-raw-cache-v1",
        "ok": not errors,
        "paper_only": True,
        "broker_orders": 0,
        "source": "alpaca-iex",
        "timeframe": "1Min",
        "requested": {"start": args.start, "end": args.end, "symbols": symbols},
        "code_sha": repository_code_sha(ROOT),
        "coverage": {
            "chunks": len(chunks),
            "bar_count": sum(int(chunk["bar_count"]) for chunk in chunks),
            "nonempty_chunks": sum(1 for chunk in chunks if chunk["bar_count"]),
            "start": min((chunk["start"] for chunk in chunks if chunk["start"]), default=None),
            "end": max((chunk["end"] for chunk in chunks if chunk["end"]), default=None),
            "symbols_with_data": sorted({chunk["symbol"] for chunk in chunks if chunk["bar_count"]}),
        },
        "chunks": chunks,
        "errors": errors,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.manifest)
    print(json.dumps({"ok": manifest["ok"], "coverage": manifest["coverage"], "errors": errors}, indent=2))
    return 0 if not errors else 1


def _months(start: date, end: date):
    current = start.replace(day=1)
    while current < end:
        next_month = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)
        yield current, next_month
        current = next_month


if __name__ == "__main__":
    raise SystemExit(main())
