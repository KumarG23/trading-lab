from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scripts.cron.v3_collector_alert import message

NOW = datetime(2026, 9, 23, 8, tzinfo=ZoneInfo("America/New_York"))


def test_alert_only_on_change_or_bounded_repeat():
    bad = {"sources": {"news": {"healthy": False}, "sec": {"healthy": True}}}
    notice, state = message(bad, {}, NOW)
    assert "news" in notice and "SEC" not in notice
    assert message(bad, state, NOW + timedelta(minutes=30))[0] == ""
    assert message(bad, state, NOW + timedelta(hours=4))[0]
    good = {"sources": {"news": {"healthy": True}, "sec": {"healthy": True}}}
    recovered, clean = message(good, state, NOW + timedelta(hours=1))
    assert "recovered" in recovered
    assert message(good, clean, NOW + timedelta(hours=2))[0] == ""
