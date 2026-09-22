#!/usr/bin/env python3
"""Read-only Alpaca market data -> local untracked ETF research artifact."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import exchange_calendars as xcals  # noqa: E402
from trading_lab.alpaca_client import AlpacaClient  # noqa: E402
from trading_lab.config import LabConfig  # noqa: E402
from trading_lab.etf_trend import SYMBOLS, validate_bars, simulate  # noqa: E402

OUTPUT = ROOT / "data/processed/etf-trend/report.json"


def run(start: date, dev_end: date, end: date) -> dict:
    if not (start < dev_end < end < datetime.now(ZoneInfo("America/New_York")).date()):
        raise ValueError("require start < dev-end < end < current Eastern date (completed sessions only)")
    cal = xcals.get_calendar("XNYS")
    # Bound the experiment so the CLI cannot accidentally fetch an unbounded corpus.
    if (end - start).days > 3653 or (dev_end - start).days < 365 or (end - dev_end).days < 90:
        raise ValueError("range requires >=1 year development, >=90 days holdout, <=10 years total")
    warmup_start = start - timedelta(days=420)
    sessions = [ts.date() for ts in cal.sessions_in_range(warmup_start.isoformat(), end.isoformat())]
    scored = [d for d in sessions if start <= d <= end]
    if not scored or scored[0] != start or dev_end not in scored or scored[-1] != end:
        raise ValueError("start, dev-end and end must be NYSE sessions")
    cfg = LabConfig.from_env_file(ROOT / ".env")
    if not cfg.alpaca_configured or not cfg.alpaca_paper or cfg.live_trading_enabled:
        raise ValueError("requires configured paper-only Alpaca credentials and live disabled")
    client = AlpacaClient(base_url=cfg.alpaca_base_url, api_key=cfg.alpaca_api_key or "", secret_key=cfg.alpaca_secret_key or "")
    dev_sessions = [d for d in sessions if d <= dev_end]
    raw = client.fetch_stock_bars(list(SYMBOLS), timeframe="1Day", start=warmup_start.isoformat(),
                                  end=(dev_end + timedelta(days=1)).isoformat(), feed="iex", adjustment="all", batch_size=1)
    data = validate_bars(raw, dev_sessions)
    development = simulate(data, dev_sessions, start, dev_end)
    passed = development["return"] > 0 and development["sell_transactions"] >= 10 and development["sessions"] >= 252
    holdout_start = sessions[sessions.index(dev_end) + 1]
    if passed:
        holdout_raw = client.fetch_stock_bars(list(SYMBOLS), timeframe="1Day", start=holdout_start.isoformat(),
                                              end=(end + timedelta(days=1)).isoformat(), feed="iex", adjustment="all", batch_size=1)
        raw += holdout_raw
        data = validate_bars(raw, sessions)
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    result = {
        "mode": "offline_historical_research_no_orders", "broker_orders": 0,
        "universe": SYMBOLS, "parameters": {"sma_sessions": 200, "momentum_sessions": 63,
            "max_positions": 2, "stop_from_peak_close": 0.12, "entry_slippage_bps": 5,
            "exit_slippage_bps": 10, "fee_per_share": 0.005, "research_notional": 10000,
            "feed": "iex", "timeframe": "1Day", "adjustment": "all"},
        "request": {"start": start.isoformat(), "dev_end": dev_end.isoformat(), "end": end.isoformat(),
                    "warmup_start": warmup_start.isoformat()},
        "data": {"sha256_raw_normalized_bars": hashlib.sha256(canonical).hexdigest(), "bar_count": len(raw),
                 "calendar_sessions_fetched": len(sessions if passed else dev_sessions),
                 "holdout_fetched": passed},
        "development": development, "development_gate_passed": passed,
        "holdout": simulate(data, sessions, holdout_start, end) if passed else "not_scored_development_failed",
        "caveats": "Historical selected ETF survivors; IEX-only adjusted synthetic OHLC, fractional same-open fills, no spread/impact/tax/interest; not execution or promotion evidence.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--dev-end", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    try:
        result = run(args.start, args.dev_end, args.end)
    except (ValueError, KeyError, IndexError) as exc:
        print(f"ETF research aborted: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
