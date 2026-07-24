from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from trading_lab.market_calendar import XNYSCalendar, filter_research_session_bars, lifecycle_cutoffs

ET = ZoneInfo("America/New_York")
UTC = timezone.utc


def test_nyse_holidays_and_weekends_are_closed():
    calendar = XNYSCalendar()

    assert calendar.is_open(datetime(2026, 7, 3, 10, 0, tzinfo=ET)) is False
    assert calendar.is_open(datetime(2026, 11, 26, 10, 0, tzinfo=ET)) is False
    assert calendar.is_open(datetime(2026, 7, 25, 10, 0, tzinfo=ET)) is False


def test_nyse_early_close_is_enforced():
    calendar = XNYSCalendar()

    assert calendar.is_open(datetime(2026, 11, 27, 12, 59, tzinfo=ET)) is True
    assert calendar.is_open(datetime(2026, 11, 27, 13, 1, tzinfo=ET)) is False
    assert calendar.session_bounds(datetime(2026, 11, 27, tzinfo=ET).date())[1].hour == 13


def test_nyse_session_bounds_follow_dst_in_utc():
    calendar = XNYSCalendar()

    before = calendar.session_bounds(datetime(2026, 3, 6, tzinfo=UTC).date())
    after = calendar.session_bounds(datetime(2026, 3, 9, tzinfo=UTC).date())

    assert before[0].astimezone(UTC).hour == 14
    assert after[0].astimezone(UTC).hour == 13


def test_lifecycle_cutoffs_shift_for_early_close():
    calendar = XNYSCalendar()

    assert lifecycle_cutoffs(calendar, datetime(2026, 11, 27, tzinfo=ET).date()) == ("11:30", "12:45")
    assert lifecycle_cutoffs(calendar, datetime(2026, 11, 30, tzinfo=ET).date()) == ("14:30", "15:45")


def test_research_bar_gate_excludes_premarket_and_post_flatten_bars():
    bars = [
        {"timestamp": "2026-07-20T13:29:00Z"},
        {"timestamp": "2026-07-20T13:30:00Z"},
        {"timestamp": "2026-07-20T19:44:00Z"},
        {"timestamp": "2026-07-20T19:45:00Z"},
    ]

    assert [bar["timestamp"] for bar in filter_research_session_bars(bars)] == [
        "2026-07-20T13:30:00Z", "2026-07-20T19:44:00Z"
    ]
