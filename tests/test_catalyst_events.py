import json
from datetime import datetime, timezone

import pytest

from trading_lab.catalyst_events import available_events, import_jsonl, load_ledger, validate_event

NOW = datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)


def event(**changes):
    return {"provider": "issuer", "url": "https://example.org/release/1", "symbol": "ABCD",
            "kind": "earnings", "published_at": "2026-09-21T17:00:00-04:00", "text": "Quarterly results",
            **changes}


def test_publication_is_not_retroactive_availability():
    row = validate_event(event(), observed_at=NOW)
    assert row["published_at"] == "2026-09-21T21:00:00Z"
    assert row["first_seen_at"] == row["available_at"] == "2026-09-22T18:00:00Z"
    assert available_events([row], "2026-09-22T17:59:59Z") == []
    assert available_events([row], "2026-09-22T14:00:00-04:00") == [row]
    assert row["historical_backtest_eligible"] is False
    assert row["text_model_features"] is None


@pytest.mark.parametrize("changes, error", [
    ({"published_at": "2026-09-22T18:01:00Z"}, "future"),
    ({"published_at": "2026-09-20T00:00:00"}, "naive"),
    ({"url": "http://example.org/x"}, "https"),
    ({"symbol": "abcd"}, "symbol"),
    ({"kind": "analyst"}, "kind"),
    ({"text": ""}, "text"),
    ({"url": "https://u:p@example.org/x"}, "URL"),
])
def test_invalid_event_rejected(changes, error):
    with pytest.raises(ValueError, match=error):
        validate_event(event(**changes), observed_at=NOW)


def test_batch_atomicity_idempotence_conflict_and_first_seen(tmp_path):
    incoming = tmp_path / "incoming.jsonl"
    ledger = tmp_path / "events.jsonl"
    incoming.write_text(json.dumps(event()) + "\n" + json.dumps(event(symbol="BAD!")) + "\n")
    with pytest.raises(ValueError, match="symbol"):
        import_jsonl(incoming, ledger, observed_at=NOW)
    assert not ledger.exists()
    incoming.write_text(json.dumps(event()) + "\n")
    assert import_jsonl(incoming, ledger, observed_at=NOW)["appended"] == 1
    first = json.loads(ledger.read_text())
    assert load_ledger(ledger) == [first]
    assert import_jsonl(incoming, ledger, observed_at=NOW)["already_present"] == 1
    assert json.loads(ledger.read_text()) == first
    incoming.write_text(json.dumps(event(text="Corrected results")) + "\n")
    with pytest.raises(ValueError, match="revision"):
        import_jsonl(incoming, ledger, observed_at=NOW)
    assert json.loads(ledger.read_text()) == first
    incoming.write_text(json.dumps({**event(), "first_seen_at": "2020-01-01T00:00:00Z"}) + "\n")
    with pytest.raises(ValueError, match="exactly"):
        import_jsonl(incoming, ledger, observed_at=NOW)


def test_tamper_and_retroactive_availability_fail_closed(tmp_path):
    incoming, ledger = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    incoming.write_text(json.dumps(event()) + "\n")
    import_jsonl(incoming, ledger, observed_at=NOW)
    row = json.loads(ledger.read_text())
    row["available_at"] = "2020-01-01T00:00:00Z"
    ledger.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="provenance"):
        load_ledger(ledger)
    with pytest.raises(ValueError, match="provenance"):
        import_jsonl(incoming, ledger, observed_at=NOW)


def test_duplicate_batch_aborts_before_any_write(tmp_path):
    incoming, ledger = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    incoming.write_text((json.dumps(event()) + "\n") * 2)
    with pytest.raises(ValueError, match="duplicate"):
        import_jsonl(incoming, ledger, observed_at=NOW)
    assert not ledger.exists()
