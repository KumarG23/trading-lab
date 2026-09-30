"""Preregistered V3 next-session earnings shadow rule v1; no order authority."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from .market_calendar import ET, XNYSCalendar
from .v3_news_history import instant
from .v3_universe import ELIGIBLE

PREREGISTERED = datetime(2026, 9, 30, 23, 2, 51, tzinfo=timezone.utc)
MINUTE = timedelta(minutes=1)


def next_session(event: dict, activated: datetime) -> tuple[datetime, datetime] | None:
    """Return next actual exchange session bounds for eligible after-close observations."""
    try:
        seen = instant(event["first_seen_at"])
        if (seen != instant(event["available_at"]) or seen < max(PREREGISTERED, activated)
                or event.get("symbol") not in ELIGIBLE or event.get("provider") != "sec-edgar-ex-99.1"
                or event.get("kind") != "earnings"):
            return None
        cal = XNYSCalendar()
        local = seen.astimezone(ET)
        _opening, closing = cal.session_bounds(local.date())
        if not closing <= local < local.replace(hour=20, minute=0, second=0, microsecond=0):
            return None
        for days in range(1, 8):
            candidate = local.date() + timedelta(days=days)
            if cal.is_session(candidate):
                return cal.session_bounds(candidate)
    except (ValueError, KeyError, TypeError, OverflowError):
        return None
    return None


def decide(event: dict, bars: list[dict], *, received_at: datetime,
           session: tuple[datetime, datetime]) -> dict | None:
    """None means before 09:35; after that persist one plan or abstention."""
    opening, closing = session
    now = instant(received_at.isoformat())
    cutoff = opening + 5 * MINUTE
    base = {"schema": "v3-next-session-decision-v1", "rule": "v3-next-session-rule-v1",
            "event_id": event["id"], "symbol": event["symbol"],
            "event_available_at": event["available_at"], "observed_at": now.isoformat(),
            "session_open_at": opening.isoformat(), "mode": "offline_counterfactual_no_orders",
            "execution_eligible": False}
    def abstain(reason: str) -> dict:
        return base | {"status": "abstain", "reason": reason}
    if now < cutoff:
        return None
    if now > cutoff + 2 * MINUTE:
        return abstain("late_capture")
    source = {}
    for bar in bars:
        if bar.get("symbol") != event["symbol"] or bar.get("feed") != "iex":
            return abstain("invalid_iex_bar")
        try:
            stamp = instant(bar["timestamp"])
            if stamp not in (opening + i * MINUTE for i in range(5)):
                continue
            vals = [bar.get(k) for k in ("open", "high", "low", "close", "volume")]
            if (stamp in source or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in vals)
                    or not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]):
                return abstain("invalid_iex_bar")
            source[stamp] = bar
        except (ValueError, KeyError, TypeError):
            return abstain("invalid_iex_bar")
    if len(source) != 5:
        # The provider may not have published its just-completed last minute yet.
        # Retry inside the fixed capture window, but never reconstruct afterward.
        return None if now < cutoff + 2 * MINUTE else abstain("missing_opening_bars")
    cent = Decimal("0.01")
    high = max(Decimal(str(b["high"])) for b in source.values())
    low = min(Decimal(str(b["low"])) for b in source.values())
    entry = (high + cent).quantize(cent, rounding=ROUND_CEILING)
    stop = (low - cent).quantize(cent, rounding=ROUND_FLOOR)
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
                   "data_cutoff_at": cutoff.astimezone(timezone.utc).isoformat(), "entry_deadline_at": deadline.isoformat(),
                   "bar_received_at": now.isoformat(), "bar_feed": "iex",
                   "decision_bars": [source[opening + i * MINUTE] for i in range(5)],
                   "planned_entry": float(entry), "stop": float(stop),
                   "target": float(entry + 2 * risk), "shares": shares}
