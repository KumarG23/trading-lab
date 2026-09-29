"""Read-only forward event/market dossiers. No signals, outcomes, fills or order authority."""
from __future__ import annotations

from collections import Counter

from .market_calendar import ET, XNYSCalendar
from .v3_event_context import match_event_market
from .v3_news_history import instant
from .v3_universe import ELIGIBLE, FINGERPRINT


def build_dossiers(events: list[dict], snapshots: list[dict]) -> dict:
    """Keep every event in the denominator; admit only observed, regular-session context.

    An IEX quote is a research observation, never proof of a fill or SIP liquidity.
    No event is relabeled as historically available from its publication timestamp.
    """
    calendar = XNYSCalendar()
    dossiers = []
    for event in events:
        available = instant(event["available_at"])
        base = {"event_id": event["id"], "symbol": event["symbol"],
                "event_available_at": available.isoformat(), "execution_eligible": False}
        if event["symbol"] not in ELIGIBLE:
            row = base | {"status": "outside_frozen_universe"}
        elif event.get("provider") != "sec-edgar-ex-99.1" or event.get("kind") != "earnings":
            row = base | {"status": "unverified_event_source"}
        elif not calendar.is_open(available):
            row = base | {"status": "outside_regular_session"}
        else:
            match = match_event_market(event, snapshots)
            if match["status"] != "context_only":
                row = base | {"status": "no_valid_post_event_quote"}
            else:
                # The matching window must also finish inside the real exchange session.
                quote_at = instant(match["quote_received_at"])
                opening, closing = calendar.session_bounds(available.astimezone(ET).date())
                if not opening <= quote_at < closing:
                    row = base | {"status": "outside_regular_session"}
                else:
                    row = match | {"status": "research_context_only", "quote_feed": "iex"}
        dossiers.append(row)
    return {"schema": "v3-forward-dossiers-v1", "universe_sha256": FINGERPRINT,
            "mode": "read_only_research_no_fills_no_orders", "counts": dict(Counter(row["status"] for row in dossiers)),
            "dossiers": dossiers}
