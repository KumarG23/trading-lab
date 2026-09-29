"""V3 forward dossiers must never turn intake into orders or inferred fills."""
from datetime import datetime, timezone

import pytest

from trading_lab.catalyst_events import validate_event
from trading_lab.v3_forward_dossiers import build_dossiers
from trading_lab.v3_universe import FINGERPRINT


def event(symbol="CCL", at="2026-09-29T16:51:00+00:00", provider="sec-edgar-ex-99.1"):
    return validate_event({"provider": provider, "url": "https://www.sec.gov/example", "symbol": symbol,
                           "kind": "earnings", "published_at": "2026-09-29T13:16:12Z", "text": "Earnings"},
                          observed_at=datetime.fromisoformat(at))


def snapshot(received="2026-09-29T16:55:00+00:00", source="2026-09-29T16:54:59+00:00", bid=24.87, ask=24.88):
    return {"schema": "v3-iex-snapshot-v1", "feed": "iex", "universe_sha256": FINGERPRINT,
            "execution_eligible": False, "received_at": received,
            "rows": [{"symbol": "CCL", "quote": {"source_at": source, "bid": bid, "ask": ask,
                      "usable_for_spread": True}}]}


def test_verified_forward_event_has_context_but_no_fill_or_order():
    report = build_dossiers([event()], [snapshot()])
    row = report["dossiers"][0]
    assert row["status"] == "research_context_only"
    assert row["quote_received_at"] == "2026-09-29T16:55:00+00:00"
    assert row["iex_ask"] == 24.88
    assert row["execution_eligible"] is False
    assert report["counts"] == {"research_context_only": 1}
    assert not any(key in row for key in ("fill", "pnl", "order", "signal"))


def test_preserves_all_abstentions_and_cannot_promote_smoke_or_after_hours():
    rows = [event(), event(at="2026-09-29T23:01:00+00:00"),
            event(provider="SEC-EDGAR-exhibit-headline"), event(symbol="SPY")]
    result = build_dossiers(rows, [snapshot(source="2026-09-29T16:50:00+00:00")])
    assert [r["status"] for r in result["dossiers"]] == [
        "no_valid_post_event_quote", "outside_regular_session", "unverified_event_source", "outside_frozen_universe"]
    assert len(result["dossiers"]) == 4


def test_fail_closed_on_forged_snapshot_provenance():
    bad = snapshot()
    bad["feed"] = "sip"
    with pytest.raises(ValueError, match="provenance"):
        build_dossiers([event()], [bad])


def test_no_quote_is_not_a_simulated_no_fill():
    row = build_dossiers([event()], [])["dossiers"][0]
    assert row["status"] == "no_valid_post_event_quote"
    assert row["execution_eligible"] is False
