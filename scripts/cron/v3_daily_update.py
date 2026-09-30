"""No-agent daily V3 status from private receipts; counts only, no market/news text."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

ROOT = Path("/home/neal/trading-lab")
VENV = ROOT / ".venv/bin/python"
if Path(sys.executable).resolve() != VENV.resolve():
    os.execv(str(VENV), [str(VENV), __file__])
sys.path.insert(0, str(ROOT))

from scripts.v3_collector import health  # noqa: E402
from trading_lab.catalyst_events import load_ledger  # noqa: E402
from trading_lab.market_calendar import XNYSCalendar  # noqa: E402
from trading_lab.v3_news_history import instant  # noqa: E402
from trading_lab.v3_universe import ELIGIBLE  # noqa: E402
from trading_lab.v3_forward_rule import EFFECTIVE  # noqa: E402


def report(*, at: datetime, collector: dict, events: list[dict], decisions: list[dict],
           outcomes: list[dict], activated: datetime, safety: dict, forward_timers: bool) -> str:
    day = at.astimezone(ZoneInfo("America/New_York")).date()
    eligible = {row["id"] for row in events if row["symbol"] in ELIGIBLE
                and row.get("provider") == "sec-edgar-ex-99.1" and row.get("kind") == "earnings"
                and XNYSCalendar().is_open(instant(row["available_at"]))}
    prospective = {row['id'] for row in events if row['id'] in eligible
                   and instant(row['first_seen_at']) == instant(row['available_at'])
                   and instant(row['first_seen_at']) >= max(activated, EFFECTIVE)}
    valid = [p for p in decisions if p.get("event_id") in prospective
             and p.get("mode") == "offline_counterfactual_no_orders"]
    statuses = Counter(p.get("status", "unknown") for p in valid)
    results = [r['outcome'] for r in outcomes if r.get('outcome', {}).get('event_id') in prospective]
    result_counts = Counter(r['status'] for r in results)
    scored = [r for r in results if r['status'] in ('resolved', 'no_fill')]
    net = sum(r['net_dollars'] for r in scored)
    today_events = sum(instant(e['first_seen_at']).astimezone(ZoneInfo('America/New_York')).date() == day
                       for e in events if e['id'] in prospective)
    today_decisions = Counter(p['status'] for p in valid
                              if instant(p['observed_at']).astimezone(ZoneInfo('America/New_York')).date() == day)
    today_outcomes = Counter(r['outcome']['status'] for r in outcomes
                             if r.get('outcome', {}).get('event_id') in prospective
                             and instant(r['fetched_at']).astimezone(ZoneInfo('America/New_York')).date() == day)
    sources = ", ".join(f"{name}={'OK' if value['healthy'] else 'DEGRADED'}"
                        for name, value in collector["sources"].items())
    is_session = XNYSCalendar().is_session(day)
    no_orders = (safety.get("mode") == "paper_proposal_only_no_orders"
                 and safety.get("safety", {}).get("broker_orders_enabled") is False
                 and safety.get("safety", {}).get("live_trading_enabled") is False)
    return (f"V3 daily research — {day.isoformat()} ET\n"
            f"Intake: {sources}. Market session: {'yes' if is_session else 'no'}.\n"
            f"Forward timers: {'active' if forward_timers else 'DEGRADED — inspect systemd user units'}.\n"
            f"Today: {today_events} new prospective events; decisions {dict(today_decisions)}; "
            f"outcomes {dict(today_outcomes)}.\n"
            "Since activation (cumulative): "
            f"Forward ledger: {len(events)} total rows; {len(eligible)} verified in-session events; "
            f"{len(prospective)} post-activation (historical rows excluded).\n"
            f"Rule v0: {dict(statuses)}; {len(prospective) - len(valid)} not yet decided; "
            f"outcomes: {dict(result_counts)}. "
            f"Always-admit observed net: ${net:.2f} across {len(scored)} scored plans "
            f"(no-trade $0; {len(valid) - len(results)} awaiting resolution; "
            f"{result_counts.get('data_gap', 0)} data gaps excluded). Partial diagnostic, not an edge claim.\n"
            "Gate: independent after-cost, complete-bar forward evidence; "
            f"Broker/live orders: {'disabled (dashboard verified)' if no_orders else 'UNVERIFIED — investigate'}."
            )


def main() -> None:
    now = datetime.now(timezone.utc)
    try:
        collector = health(at=now)
        events = load_ledger(ROOT / "data/events/catalysts-v1.jsonl")
        store = ROOT / "data/events/v3-forward-decisions"
        marker = store / "activation.json"
        activated = instant(json.loads(marker.read_text())["activated_at"]) if marker.exists() else now
        decisions = [json.loads(p.read_text()) for p in sorted(store.glob('*.json')) if p != marker]
        outcomes = [json.loads(p.read_text()) for p in sorted((ROOT / 'data/processed/v3-forward/outcomes').glob('*.json'))]
        with urlopen("http://127.0.0.1:8787/api/snapshot", timeout=5) as response:
            snapshot = json.load(response)
        timers = subprocess.run(['systemctl', '--user', 'is-active',
                                 'trading-lab-v3-forward-intake.timer', 'trading-lab-v3-forward-resolve.timer'],
                                capture_output=True, text=True, timeout=5)
        forward_timers = timers.returncode == 0 and timers.stdout.splitlines() == ['active', 'active']
        print(report(at=now, collector=collector, events=events, decisions=decisions,
                     outcomes=outcomes, activated=activated, safety=snapshot, forward_timers=forward_timers))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        # Never include raw provider or event text in delivered error output.
        print(f"⚠️ V3 daily research report could not verify data ({type(exc).__name__}). No outcome or order-safety claims.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
