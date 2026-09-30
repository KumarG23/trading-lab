"""Isolated read-only next-session earnings shadow lane; no broker or order calls."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading_lab.catalyst_events import load_ledger
from trading_lab.market_calendar import ET
from trading_lab.v3_next_session_rule import PREREGISTERED, decide, next_session
from trading_lab.v3_news_history import instant
from trading_lab.v3_outcomes import resolve_outcome
from scripts.v3_forward_run import ROOT, client, save_private

STORE = ROOT / "data/events/v3-next-session-decisions"
OUTCOMES = ROOT / "data/processed/v3-next-session/outcomes"
LEDGER = ROOT / "data/events/catalysts-v1.jsonl"


def acquire(events: list[dict], *, now: datetime, activated: datetime, data,
            store: Path = STORE) -> dict:
    counts = {"planned": 0, "abstain": 0, "awaiting_open": 0,
              "historical_or_ineligible": 0, "already_recorded": 0}
    for event in events:
        session = next_session(event, activated)
        if session is None:
            counts["historical_or_ineligible"] += 1
            continue
        event_id = event["id"]
        if not isinstance(event_id, str) or not re.fullmatch(r"[0-9a-f]{64}", event_id):
            raise ValueError("invalid event ID")
        destination = store / (event_id + ".json")
        if destination.exists():
            counts["already_recorded"] += 1
            continue
        opening, _closing = session
        if now < instant(event["first_seen_at"]) or now < opening + timedelta(minutes=5):
            counts["awaiting_open"] += 1
            continue
        bars = []
        if now <= opening + timedelta(minutes=7):
            bars = data.fetch_stock_bars([event["symbol"]], timeframe="1Min",
                                         start=opening.isoformat(),
                                         end=(opening + timedelta(minutes=5)).isoformat(),
                                         feed="iex", batch_size=1)
            if any(bar.get("feed", "iex") != "iex" for bar in bars):
                raise ValueError("unexpected bar feed")
            bars = [bar | {"feed": "iex"} for bar in bars]
        decision = decide(event, bars, received_at=max(now, datetime.now(timezone.utc)), session=session)
        if decision is None:
            counts["awaiting_open"] += 1
            continue
        save_private(destination, decision)
        counts[decision["status"]] += 1
    return counts


def resolve(*, now: datetime, data, store: Path = STORE, outcomes: Path = OUTCOMES) -> dict:
    counts = {"resolved": 0, "no_fill": 0, "data_gap": 0, "pending": 0, "abstain": 0}
    for path in sorted(store.glob("*.json")):
        if path.name == "activation.json":
            continue
        plan = json.loads(path.read_text())
        if plan["status"] != "planned":
            counts["abstain"] += 1
            continue
        destination = outcomes / path.name
        if destination.exists():
            continue
        opening = instant(plan["session_open_at"])
        from trading_lab.market_calendar import XNYSCalendar
        _open, closing = XNYSCalendar().session_bounds(opening.astimezone(ET).date())
        if now < closing + timedelta(minutes=15):
            counts["pending"] += 1
            continue
        decision = instant(plan["decision_at"])
        start = decision.replace(second=0, microsecond=0) + timedelta(minutes=1)
        bars = data.fetch_stock_bars([plan["symbol"]], timeframe="1Min",
                                     start=start.isoformat(), end=closing.isoformat(),
                                     feed="iex", batch_size=1)
        if any(bar.get("feed", "iex") != "iex" for bar in bars):
            raise ValueError("unexpected outcome bar feed")
        bars = [bar | {"feed": "iex"} for bar in bars]
        outcome = resolve_outcome(plan, bars, as_of=now.isoformat())
        save_private(destination, {"schema": "v3-next-session-outcome-record-v1", "feed": "iex",
                                   "fetched_at": now.isoformat(), "source_bars": bars, "outcome": outcome})
        counts[outcome["status"]] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("intake", "resolve", "smoke"))
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.action == "smoke":
        # Real zero-event runtime path without credentials/network or production writes.
        class NoNetwork:
            def fetch_stock_bars(self, *args, **kwargs):
                raise AssertionError("no-event smoke attempted network")
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(prefix="v3-next-session-") as temp:
            result = acquire([], now=now, activated=now, data=NoNetwork(), store=Path(temp))
        print(json.dumps({"action": "smoke", "mode": "offline_counterfactual_no_orders", "counts": result}))
        return
    STORE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STORE, 0o700)
    with (STORE / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = client()
        if args.action == "intake":
            events = load_ledger(LEDGER)
            marker = STORE / "activation.json"
            activated = instant(json.loads(marker.read_text())["activated_at"]) if marker.exists() else now
            result = acquire(events, now=now, activated=activated, data=data)
            if not marker.exists():
                save_private(marker, {"activated_at": now.isoformat(),
                                      "preregistered_at": PREREGISTERED.isoformat(),
                                      "rule": "v3-next-session-rule-v1"})
        else:
            result = resolve(now=now, data=data)
    print(json.dumps({"action": args.action, "mode": "offline_counterfactual_no_orders", "counts": result}, sort_keys=True))


if __name__ == "__main__":
    main()
