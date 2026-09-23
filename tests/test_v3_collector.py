from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from scripts.v3_collector import health, run_source
from trading_lab.v3_universe import FINGERPRINT

NOW = datetime(2026, 9, 23, 1, tzinfo=timezone.utc)


def test_receipts_sanitize_failures_and_do_not_turn_zero_into_error(tmp_path):
    private = tmp_path / "receipts"
    def success(command, **kwargs):
        assert command[-1] == "--capture-news"
        return SimpleNamespace(returncode=0, stdout=json.dumps({"capture_news": {"articles": 0,
                           "snapshot": "data/events/news-snapshots/first.json"}}), stderr="")
    receipt = run_source("news", state=private, invoke=success, now=lambda: NOW)
    assert receipt["status"] == "ok" and receipt["articles"] == 0
    def failure(command, **kwargs):
        return SimpleNamespace(returncode=42, stdout="secret-key-in-provider-payload", stderr="secret-key")
    failed = run_source("news", state=private, invoke=failure, now=lambda: NOW + timedelta(minutes=1))
    assert failed["status"] == "failure" and failed["error_type"] == "RuntimeError"
    assert "secret-key" not in (private / "news.jsonl").read_text()
    assert (private / "news.jsonl").stat().st_mode & 0o777 == 0o600


def test_health_requires_successful_recent_both_sources_and_valid_snapshot(tmp_path, monkeypatch):
    contact = tmp_path / "contact"
    contact.write_text("test@example.invalid\n")
    contact.chmod(0o600)
    monkeypatch.setattr("scripts.v3_collector.SEC_CONTACT", contact)
    state, snaps = tmp_path / "receipts", tmp_path / "snapshots"
    state.mkdir()
    snaps.mkdir()
    for source, report in (("news", {"capture_news": {"articles": 0, "snapshot": "first.json"}}),
                           ("sec", {"sec": {"issuers_checked": 44, "appended": 0, "coverage":
                                     {"item_202_recent": 0, "without_single_exhibit": 0, "skipped_cap": 0, "matched": 0}}})):
        run_source(source, state=state, invoke=lambda *a, r=report, **k: SimpleNamespace(returncode=0, stdout=json.dumps(r)), now=lambda: NOW)
    snapshot = {"schema": "v3-news-snapshot-v1", "universe_sha256": FINGERPRINT,
                "observed_at": NOW.isoformat(), "window_start": (NOW - timedelta(minutes=30)).isoformat(),
                "window_end": NOW.isoformat(), "articles": []}
    (snaps / "first.json").write_text(json.dumps(snapshot))
    assert health(state=state, snapshots=snaps, at=NOW + timedelta(minutes=5))["healthy"]
    assert not health(state=state, snapshots=snaps, at=NOW - timedelta(hours=2))["healthy"]
    assert not health(state=state, snapshots=snaps, at=NOW + timedelta(minutes=25))["healthy"]
    snapshot["universe_sha256"] = "tampered"
    (snaps / "first.json").write_text(json.dumps(snapshot))
    assert not health(state=state, snapshots=snaps, at=NOW + timedelta(minutes=5))["healthy"]


def test_market_receipt_has_feed_quality_and_can_fail_closed(tmp_path):
    report = {"capture_market": {"feed": "iex", "symbols_expected": 46, "quotes_present": 46,
                                 "quotes_usable_for_spread": 0, "quotes_unpriced": 18,
                                 "snapshot": "data/events/market-snapshots/first.json"}}
    receipt = run_source("market", state=tmp_path,
                         invoke=lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(report)), now=lambda: NOW)
    assert receipt["status"] == "ok" and receipt["quotes_usable_for_spread"] == 0
    report["capture_market"]["quotes_present"] = 0
    failure = run_source("market", state=tmp_path,
                         invoke=lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(report)), now=lambda: NOW)
    assert failure["status"] == "failure"


def test_incomplete_sec_and_failure_receipt_prevent_healthy_status(tmp_path, monkeypatch):
    contact = tmp_path / "contact"
    contact.write_text("test@example.invalid\n")
    contact.chmod(0o600)
    monkeypatch.setattr("scripts.v3_collector.SEC_CONTACT", contact)
    report = {"sec": {"issuers_checked": 43, "appended": 0, "coverage":
                      {"item_202_recent": 0, "without_single_exhibit": 0, "skipped_cap": 0, "matched": 0}}}
    receipt = run_source("sec", state=tmp_path,
                         invoke=lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(report)), now=lambda: NOW)
    assert receipt["status"] == "failure" and receipt["error_type"] == "ValueError"
    assert health(state=tmp_path, snapshots=tmp_path / "missing", at=NOW)["sources"]["sec"]["last_status"] == "failure"
