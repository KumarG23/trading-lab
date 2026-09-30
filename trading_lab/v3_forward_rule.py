"""Frozen V3 v0 decision rule. Only decision-time IEX data; no order authority."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from .market_calendar import ET, XNYSCalendar
from .v3_news_history import instant
from .v3_universe import ELIGIBLE

EFFECTIVE = datetime(2026, 9, 30, 14, tzinfo=timezone.utc)
MINUTE = timedelta(minutes=1)

def positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def relevant(event: dict, activated: datetime) -> bool:
    try:
        seen = instant(event["first_seen_at"])
        return (seen == instant(event["available_at"]) and seen >= max(EFFECTIVE, activated)
                and event["symbol"] in ELIGIBLE and event.get("provider") == "sec-edgar-ex-99.1"
                and event.get("kind") == "earnings" and XNYSCalendar().is_open(seen))
    except (ValueError, KeyError, TypeError):
        return False


def decide(event: dict, bars: list[dict], *, received_at: datetime) -> dict | None:
    """Return a fixed plan or an abstention; None means still awaiting a timely bar."""
    seen = instant(event["available_at"])
    now = received_at.astimezone(timezone.utc)
    opening, closing = XNYSCalendar().session_bounds(seen.astimezone(ET).date())
    base = {"schema": "v3-forward-decision-v0", "event_id": event["id"],
            "symbol": event["symbol"], "event_available_at": seen.isoformat(),
            "observed_at": now.isoformat(), "mode": "offline_counterfactual_no_orders",
            "execution_eligible": False, "rule": "v3-forward-rule-v0"}
    def abstain(reason: str) -> dict:
        return base | {"status": "abstain", "reason": reason}
    if now < seen:
        raise ValueError("decision precedes event")
    if not opening <= seen < closing - timedelta(minutes=90):
        return abstain("outside_decision_window")
    first = seen.replace(second=0, microsecond=0) + MINUTE
    eligible = []
    for bar in bars:
        if bar.get("symbol") != event["symbol"] or bar.get("feed") != "iex":
            raise ValueError("wrong symbol or unproven IEX feed")
        stamp = instant(bar["timestamp"])
        if stamp < first or stamp > seen + timedelta(minutes=10) or stamp + MINUTE > now:
            continue
        values = [bar.get(key) for key in ("open", "high", "low", "close", "volume")]
        if (any(not positive_number(v) for v in values)
                or not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]):
            raise ValueError("invalid decision bar")
        eligible.append((stamp, bar))
    if not eligible:
        return abstain("no_completed_iex_bar") if now > seen + timedelta(minutes=11) else None
    stamp, bar = min(eligible, key=lambda item: item[0])
    cutoff = stamp + MINUTE
    if now - cutoff > timedelta(minutes=2):
        return abstain("late_first_bar")
    if now >= closing - timedelta(minutes=90):
        return abstain("outside_decision_window")
    cent = Decimal("0.01")
    entry = (Decimal(str(bar["high"])) + cent).quantize(cent, rounding=ROUND_CEILING)
    stop = (Decimal(str(bar["low"])) - cent).quantize(cent, rounding=ROUND_FLOOR)
    risk = entry - stop
    if entry <= 0 or stop <= 0 or not Decimal("0.002") <= risk / entry <= Decimal("0.05"):
        return abstain("stop_width_invalid")
    shares = min(int(Decimal("200") // entry), int(Decimal("2") // risk))
    if shares < 1:
        return abstain("notional_or_risk_too_small")
    deadline = min(now + timedelta(minutes=10), closing - timedelta(minutes=90))
    if deadline <= now:
        return abstain("outside_decision_window")
    return base | {"status": "planned", "decision_at": now.isoformat(),
                   "data_cutoff_at": cutoff.isoformat(), "entry_deadline_at": deadline.isoformat(),
                   "bar_received_at": now.isoformat(), "bar_feed": "iex", "decision_bar": bar,
                   "planned_entry": float(entry), "stop": float(stop),
                   "target": float(entry + risk * 2), "shares": shares}
