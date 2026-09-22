from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from trading_lab.alpaca_client import AlpacaClient
from trading_lab.etf_trend import SYMBOLS, simulate, validate_bars


def fixture_bars(days=260, rising=True):
    sessions = [date(2020, 1, 1) + timedelta(days=i) for i in range(days)]
    raw = []
    for s in SYMBOLS:
        for i, day in enumerate(sessions):
            c = 100 + i * 0.2 if rising else 100
            raw.append({"symbol": s, "timestamp": day.isoformat() + "T00:00:00Z", "open": c, "high": c + 1,
                        "low": c - 1, "close": c, "volume": 1000})
    return sessions, raw


def test_adjustment_all_reaches_alpaca_read_only_get():
    class HTTP:
        def request_json(self, method, url, headers=None, payload=None, timeout=20):
            assert method == "GET"
            query = parse_qs(urlparse(url).query)
            assert query["adjustment"] == ["all"]
            assert query["timeframe"] == ["1Day"]
            return {"bars": {}}
    client = AlpacaClient(base_url="https://paper-api.alpaca.markets", api_key="x", secret_key="y", http_client=HTTP())
    assert client.fetch_stock_bars(["SPY"], timeframe="1Day", start="2020-01-01", end="2020-02-01", adjustment="all") == []


def test_missing_duplicate_and_bad_bars_abort():
    days, bars = fixture_bars()
    validate_bars(bars, days)
    with pytest.raises(ValueError, match="missing"):
        validate_bars(bars[1:], days)
    with pytest.raises(ValueError, match="duplicate"):
        validate_bars(bars + bars[:1], days)
    bad = [dict(b) for b in bars]
    bad[0]["low"] = bad[0]["high"] + 1
    with pytest.raises(ValueError, match="invalid"):
        validate_bars(bad, days)


def test_signal_uses_prior_close_and_next_open_only():
    days, raw = fixture_bars()
    data = validate_bars(raw, days)
    # First scored date on a new week; changes to its close cannot influence opening choice.
    start = next(d for d in days[201:215] if d.weekday() == 0)
    a = simulate(data, days, start, start)
    for s in SYMBOLS:
        data[s][start]["close"] *= 0.8
        data[s][start]["low"] = min(data[s][start]["low"], data[s][start]["close"])
    b = simulate(data, days, start, start)
    assert a["weekly_decisions"] == b["weekly_decisions"]
    assert a["weekly_decisions"][0]["signal_close"] == days[days.index(start) - 1].isoformat()
    assert a["weekly_decisions"][0]["fill_open"] == start.isoformat()
    assert a["return"] != b["return"]


def test_weekly_gap_stop_precedes_rebalance_no_same_open_reentry():
    days, raw = fixture_bars()
    data = validate_bars(raw, days)
    start = next(d for d in days[201:215] if d.weekday() == 0)
    following_monday = start + timedelta(days=7)
    for s in ("EEM", "EFA"):
        data[s][following_monday].update(open=50, high=51, low=49, close=50)
    result = simulate(data, days, start, following_monday)
    decision = result["weekly_decisions"][-1]
    assert decision["gap_stopped_before_rebalance"] == ["EEM", "EFA"]
    assert not set(decision["selected"]) & {"EEM", "EFA"}
    assert result["stops"] == 2


def test_gap_stop_exits_at_open_not_stop_and_fee_costs():
    days, raw = fixture_bars()
    data = validate_bars(raw, days)
    start = next(d for d in days[201:215] if d.weekday() == 0)
    next_day = days[days.index(start) + 1]
    # Since all candidates tie, EEM and EFA are selected alphabetically.
    for s in ("EEM", "EFA"):
        data[s][next_day].update(open=50, high=51, low=49, close=50)
    gap = simulate(data, days, start, next_day)
    assert gap["stops"] == 2
    assert gap["return"] < -0.15
    no_gap = validate_bars(raw, days)
    for s in ("EEM", "EFA"):
        no_gap[s][next_day].update(open=130, high=131, low=100, close=120)
    stopped = simulate(no_gap, days, start, next_day)
    assert stopped["stops"] == 2
    assert stopped["return"] > gap["return"]
