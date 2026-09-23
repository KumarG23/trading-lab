from datetime import datetime, timedelta, timezone

import pytest

from trading_lab.v3_event_context import match_event_market
from trading_lab.v3_universe import FINGERPRINT

T = datetime(2026, 9, 22, 14, tzinfo=timezone.utc)
EVENT = {"id": "event-1", "symbol": "AMD", "available_at": T.isoformat()}


def snap(received, source, *, usable=True, bid=100, ask=100.02):
    return {"schema": "v3-iex-snapshot-v1", "feed": "iex", "universe_sha256": FINGERPRINT,
            "execution_eligible": False, "received_at": received.isoformat(),
            "rows": [{"symbol": "AMD", "quote": {"source_at": source.isoformat(), "bid": bid,
                                                 "ask": ask, "usable_for_spread": usable}}]}


def test_market_match_never_backdates_news_or_uses_pre_event_quote():
    earlier = snap(T - timedelta(minutes=1), T - timedelta(minutes=1))
    stale = snap(T + timedelta(minutes=3), T - timedelta(seconds=1))
    usable = snap(T + timedelta(minutes=4), T + timedelta(minutes=3))
    result = match_event_market(EVENT, [usable, earlier, stale])
    assert result["status"] == "context_only" and result["iex_ask"] == 100.02
    assert result["quote_source_at"] == (T + timedelta(minutes=3)).isoformat()
    assert not result["execution_eligible"]
    assert match_event_market(EVENT, [earlier, stale])["status"] == "no_valid_post_event_quote"
    assert match_event_market(EVENT, [snap(T + timedelta(minutes=11), T + timedelta(minutes=10))])["status"] == "no_valid_post_event_quote"
    assert match_event_market(EVENT, [snap(T + timedelta(minutes=2), T + timedelta(minutes=1), usable=False)])["status"] == "no_valid_post_event_quote"


def test_market_match_rejects_wrong_feed_and_contradictory_quote():
    bad = snap(T + timedelta(minutes=2), T + timedelta(minutes=1))
    bad["feed"] = "sip"
    with pytest.raises(ValueError, match="provenance"):
        match_event_market(EVENT, [bad])
    crossed = snap(T + timedelta(minutes=2), T + timedelta(minutes=1), bid=101, ask=100)
    with pytest.raises(ValueError, match="contradictory"):
        match_event_market(EVENT, [crossed])
