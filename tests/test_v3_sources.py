from datetime import datetime, timezone

import pytest

from trading_lab.v3_sources import sec_events


def fixture(*, items="2.02", cik=866787, doc="earnings.htm", accepted="2026-09-22T12:30:00Z"):
    return {"cik": cik, "filings": {"recent": {
        "form": ["8-K"], "items": [items], "acceptanceDateTime": [accepted],
        "accessionNumber": ["0001171843-26-006159"], "primaryDocument": [doc]}}}


def test_sec_item_202_only_and_true_availability():
    calls = []
    observed = datetime(2026, 9, 22, 18, tzinfo=timezone.utc)
    def fetch(url):
        calls.append(url)
        return "<ACCEPTANCE-DATETIME>20260922123000\n" if url.endswith(".txt") else "<script>ignore</script><p>Quarterly earnings announced</p>"
    events = sec_events(fixture(), cik=866787, symbol="AZO", observed_at=observed, fetch_document=fetch)
    assert len(events) == 1
    assert events[0]["text"] == "Quarterly earnings announced"
    assert len(calls) == 2 and calls[1] == events[0]["url"]
    assert events[0]["published_at"] == "2026-09-22T16:30:00+00:00"
    assert sec_events(fixture(items="1.01"), cik=866787, symbol="AZO", observed_at=observed,
                      fetch_document=lambda url: pytest.fail("should not fetch")) == []


def test_sec_rejects_wrong_issuer_or_document_escape():
    observed = datetime(2026, 9, 22, 18, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="CIK mismatch"):
        sec_events(fixture(cik=123), cik=866787, symbol="AZO", observed_at=observed, fetch_document=lambda _: "x")
    with pytest.raises(ValueError, match="unsafe SEC"):
        sec_events(fixture(doc="../secret"), cik=866787, symbol="AZO", observed_at=observed, fetch_document=lambda _: "x")


def test_sec_old_filing_does_not_fetch_or_retroactively_apply():
    observed = datetime(2026, 9, 22, 18, tzinfo=timezone.utc)
    assert sec_events(fixture(accepted="2026-08-22T12:30:00Z"), cik=866787, symbol="AZO", observed_at=observed,
                      fetch_document=lambda _: pytest.fail("old filing")) == []
    with pytest.raises(ValueError, match="acceptance clocks disagree"):
        sec_events(fixture(), cik=866787, symbol="AZO", observed_at=observed,
                   fetch_document=lambda _: "<ACCEPTANCE-DATETIME>20260922123001\n")
    with pytest.raises(ValueError, match="future SEC"):
        sec_events(fixture(accepted="2026-09-23T12:30:00Z"), cik=866787, symbol="AZO", observed_at=observed,
                   fetch_document=lambda _: "<ACCEPTANCE-DATETIME>20260923123000\n")
