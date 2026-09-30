"""Read-only V3 forward plan capture and after-close offline resolution; never submits orders."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, Any

from trading_lab.alpaca_client import AlpacaClient
from trading_lab.catalyst_events import load_ledger
from trading_lab.config import LabConfig
from trading_lab.market_calendar import ET, XNYSCalendar
from trading_lab.v3_forward_rule import decide, relevant
from trading_lab.v3_news_history import instant
from trading_lab.v3_outcomes import resolve_outcome

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data/events/v3-forward-decisions"
OUTCOMES = ROOT / "data/processed/v3-forward/outcomes"

class BarReader(Protocol):
    def fetch_stock_bars(self, symbols: list[str], *, timeframe: str, start: str,
                         end: str, feed: str = "iex", batch_size: int = 1) -> list[dict[str, Any]]: ...


def save_private(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    if path.exists():
        raise FileExistsError(path.name)
    tmp = path.with_suffix(".tmp")
    with os.fdopen(os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as output:
        json.dump(value, output, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(tmp, path)


def client() -> AlpacaClient:
    config = LabConfig.from_env_file(str(ROOT / ".env"))
    if not config.alpaca_api_key or not config.alpaca_secret_key or not config.alpaca_paper or config.live_trading_enabled:
        raise ValueError("read-only V3 requires paper configuration and disabled live trading")
    return AlpacaClient(base_url=config.alpaca_base_url, api_key=config.alpaca_api_key,
                        secret_key=config.alpaca_secret_key)


def acquire(events: list[dict], *, now: datetime, activated: datetime, data: BarReader,
            store: Path = STORE) -> dict:
    counts = {"new_plans": 0, "abstentions": 0, "awaiting_bar": 0, "historical_or_ineligible": 0}
    for event in events:
        if not relevant(event, activated):
            counts["historical_or_ineligible"] += 1
            continue
        event_id = event["id"]
        if not re.fullmatch(r"[0-9a-f]{64}", event_id):
            raise ValueError("invalid event ID")
        destination = store / (event_id + ".json")
        if destination.exists():
            continue
        seen = instant(event["available_at"])
        if now < seen:
            continue
        # No network request beyond the event's ten-minute evidence window.
        bars = []
        _, closing = XNYSCalendar().session_bounds(seen.astimezone(ET).date())
        if now <= seen + timedelta(minutes=11) and seen < closing - timedelta(minutes=90):
            start = seen.replace(second=0, microsecond=0) + timedelta(minutes=1)
            bars = data.fetch_stock_bars([event["symbol"]], timeframe="1Min", start=start.isoformat(),
                                          end=now.isoformat(), feed="iex", batch_size=1)
            bars = [bar | {"feed": "iex"} for bar in bars]
        decision = decide(event, bars, received_at=max(now, datetime.now(timezone.utc)))
        if decision is None:
            counts["awaiting_bar"] += 1
            continue
        save_private(destination, decision)
        counts["new_plans" if decision["status"] == "planned" else "abstentions"] += 1
    return counts


def resolve(*, now: datetime, data: BarReader, store: Path = STORE,
            outcomes: Path = OUTCOMES) -> dict:
    counts = {"resolved": 0, "no_fill": 0, "data_gap": 0, "pending": 0, "abstentions": 0}
    for path in sorted(store.glob("*.json")):
        if path.name == "activation.json":
            continue
        plan = json.loads(path.read_text())
        if plan["status"] != "planned":
            counts["abstentions"] += 1
            continue
        destination = outcomes / path.name
        if destination.exists():
            continue
        decision = instant(plan["decision_at"])
        _, closing = XNYSCalendar().session_bounds(decision.astimezone(ET).date())
        if now < closing + timedelta(minutes=15):
            counts["pending"] += 1
            continue
        start = decision.replace(second=0, microsecond=0) + timedelta(minutes=1)
        bars = data.fetch_stock_bars([plan["symbol"]], timeframe="1Min", start=start.isoformat(),
                                     end=closing.isoformat(), feed="iex", batch_size=1)
        bars = [bar | {"feed": "iex"} for bar in bars]
        outcome = resolve_outcome(plan, bars, as_of=now.isoformat())
        save_private(destination, {"schema": "v3-forward-outcome-record-v0", "feed": "iex",
                                   "fetched_at": now.isoformat(), "source_bars": bars, "outcome": outcome})
        counts[outcome["status"]] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("intake", "resolve"))
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    STORE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STORE, 0o700)
    with (STORE / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        data = client()
        if args.action == "intake":
            events = load_ledger(ROOT / "data/events/catalysts-v1.jsonl")
            marker = STORE / "activation.json"
            activated = instant(json.loads(marker.read_text())["activated_at"]) if marker.exists() else now
            result = acquire(events, now=now, activated=activated, data=data)
            # First activation counts only after the entire first intake succeeds.
            # With activated=now, all existing observations are historical.
            if not marker.exists():
                save_private(marker, {"activated_at": now.isoformat(), "rule": "v3-forward-rule-v0"})
        else:
            result = resolve(now=now, data=data)
    print(json.dumps({"action": args.action, "mode": "offline_counterfactual_no_orders", "counts": result}, sort_keys=True))


if __name__ == "__main__":
    main()
