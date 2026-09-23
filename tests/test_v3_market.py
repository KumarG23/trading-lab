from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

from trading_lab.v3_market import capture_market, SYMBOLS

NOW = datetime.now(timezone.utc)


def test_market_rows_preserve_iex_quote_time_and_missing_denominator():
    url_seen = []
    def fetch(url):
        url_seen.append(url)
        return {"AMD": {"latestQuote": {"t": (NOW - timedelta(minutes=2)).isoformat(),
                                        "bp": 100.0, "ap": 100.02, "bs": 10, "as": 20},
                        "minuteBar": {"t": (NOW - timedelta(minutes=3)).isoformat(), "o": 100,
                                      "h": 101, "l": 99, "c": 100.5, "v": 450}}}
    result = capture_market(api_key="k", secret_key="s", requested_at=NOW, fetch_json=fetch)
    assert result["feed"] == "iex" and result["execution_eligible"] is False
    assert result["symbols_expected"] == len(SYMBOLS) and result["quotes_present"] == 1
    assert result["quotes_fresh_10m"] == 1
    assert next(row for row in result["rows"] if row["symbol"] == "AMD")["quote"]["ask"] == 100.02
    assert next(row for row in result["rows"] if row["symbol"] == "QQQ")["missing"]
    assert set(parse_qs(urlsplit(url_seen[0]).query)["symbols"][0].split(",")) == SYMBOLS
    assert parse_qs(urlsplit(url_seen[0]).query)["feed"] == ["iex"]


def test_market_flags_crossed_and_rejects_future_iex_quote():
    def payload(bid, ask, offset=0):
        return {"AMD": {"latestQuote": {"t": (NOW + timedelta(minutes=offset)).isoformat(),
                                        "bp": bid, "ap": ask}}}
    result = capture_market(api_key="k", secret_key="s", requested_at=NOW,
                            fetch_json=lambda _: payload(100, 99))
    assert result["quotes_crossed"] == 1 and result["quotes_usable_for_spread"] == 0
    assert not next(row for row in result["rows"] if row["symbol"] == "AMD")["quote"]["usable_for_spread"]
    with pytest.raises(ValueError, match="invalid IEX quote"):
        capture_market(api_key="k", secret_key="s", requested_at=NOW,
                       fetch_json=lambda _: payload(100, 101, 5))
