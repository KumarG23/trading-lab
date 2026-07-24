from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

ET = ZoneInfo("America/New_York")


class XNYSCalendar:
    """Thin NYSE calendar boundary used by live and replay paths."""

    def __init__(self) -> None:
        self._calendar = xcals.get_calendar("XNYS")

    def session_bounds(self, session: date) -> tuple[datetime, datetime]:
        label = pd.Timestamp(session)
        if not self._calendar.is_session(label):
            raise ValueError(f"not an XNYS trading session: {session.isoformat()}")
        opening = self._calendar.session_open(label).to_pydatetime().astimezone(ET)
        closing = self._calendar.session_close(label).to_pydatetime().astimezone(ET)
        return opening, closing

    def is_open(self, now: datetime) -> bool:
        local = now.astimezone(ET)
        try:
            opening, closing = self.session_bounds(local.date())
        except ValueError:
            return False
        return opening <= local < closing

    def is_session(self, session: date) -> bool:
        return bool(self._calendar.is_session(pd.Timestamp(session)))


def lifecycle_cutoffs(calendar: XNYSCalendar, session: date) -> tuple[str, str]:
    """Return no-new-entry and flatten clocks relative to the actual close."""
    _opening, closing = calendar.session_bounds(session)
    no_new = closing - timedelta(minutes=90)
    flatten = closing - timedelta(minutes=15)
    return no_new.strftime("%H:%M"), flatten.strftime("%H:%M")


def filter_research_session_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calendar = XNYSCalendar()
    bounds: dict[date, tuple[datetime, datetime] | None] = {}
    accepted = []
    for bar in bars:
        instant = datetime.fromisoformat(str(bar["timestamp"]).replace("Z", "+00:00")).astimezone(ET)
        session = instant.date()
        if session not in bounds:
            try:
                opening, closing = calendar.session_bounds(session)
                bounds[session] = (opening, closing - timedelta(minutes=15))
            except ValueError:
                bounds[session] = None
        window = bounds[session]
        if window is not None and window[0] <= instant < window[1]:
            accepted.append(bar)
    return accepted
