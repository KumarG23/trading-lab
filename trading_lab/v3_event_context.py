"""Fail-closed event/observed-market matching. No labels or trade decisions."""
from __future__ import annotations

from datetime import timedelta

from .v3_news_history import instant
from .v3_universe import FINGERPRINT, ELIGIBLE


def match_event_market(event: dict, snapshots: list[dict], *, max_delay: timedelta = timedelta(minutes=10)) -> dict:
    """Only post-receipt IEX quotes whose own source time follows the event."""
    symbol = event["symbol"]
    available = instant(event["available_at"])
    if symbol not in ELIGIBLE or max_delay <= timedelta(0) or max_delay > timedelta(minutes=10):
        raise ValueError("invalid event/snapshot matching bounds")
    base = {"event_id": event["id"], "symbol": symbol,
            "event_available_at": available.isoformat(), "execution_eligible": False}
    candidates = []
    for snapshot in snapshots:
        if (snapshot.get("schema") != "v3-iex-snapshot-v1" or snapshot.get("feed") != "iex"
                or snapshot.get("universe_sha256") != FINGERPRINT or snapshot.get("execution_eligible") is not False):
            raise ValueError("invalid market snapshot provenance")
        received = instant(snapshot["received_at"])
        if not available <= received <= available + max_delay:
            continue
        for row in snapshot["rows"]:
            if row["symbol"] != symbol or not isinstance(row.get("quote"), dict):
                continue
            quote = row["quote"]
            source = instant(quote["source_at"])
            if not available <= source <= received or not quote.get("usable_for_spread"):
                continue
            if quote["bid"] <= 0 or quote["ask"] < quote["bid"]:
                raise ValueError("contradictory market quote flags")
            candidates.append((received, source, quote))
    if not candidates:
        return base | {"status": "no_valid_post_event_quote"}
    received, source, quote = min(candidates, key=lambda item: item[0])
    return base | {"status": "context_only", "quote_received_at": received.isoformat(),
                   "quote_source_at": source.isoformat(), "iex_bid": quote["bid"],
                   "iex_ask": quote["ask"], "spread": quote["ask"] - quote["bid"]}
