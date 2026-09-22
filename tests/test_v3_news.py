from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

from trading_lab.v3_news import capture_news
from trading_lab.v3_universe import CORE, EXPANSION, ELIGIBLE, FINGERPRINT, focus, tier


NOW = datetime(2026, 9, 22, 23, tzinfo=timezone.utc)


def story(ident=1, *, symbols=None, title="Quarterly earnings released", created="2026-09-22T22:00:00Z"):
    return {"id": ident, "symbols": symbols or ["AMD"], "headline": title,
            "created_at": created, "url": "https://example.com/news/1"}


def test_universe_is_disjoint_and_attention_does_not_admit_noise():
    assert len(CORE) == 24 and len(EXPANSION) == 20 and len(ELIGIBLE) == 44
    assert len(FINGERPRINT) == 64
    assert tier("AMD") == "core" and tier("ROKU") == "expansion"
    assert focus("AMD", verified_earnings=False)
    assert not focus("ROKU", verified_earnings=False)
    assert focus("ROKU", verified_earnings=True)
    assert not focus("UNKNOWN", verified_earnings=True)


def test_news_keeps_quiet_and_non_earnings_stories_as_evidence():
    urls = []
    def fetch(url):
        urls.append(url)
        q = parse_qs(urlsplit(url).query)
        return {"news": [story(symbols=["AMD", "ROKU"], title="AMD faces lawsuit")],
                "next_page_token": "next"} if "page_token" not in q else {
                "news": [story(2, symbols=["ROKU"], title="Roku quarterly earnings announced")],
                "next_page_token": None}
    capture = capture_news(api_key="key", secret_key="secret", observed_at=NOW, fetch_json=fetch)
    assert len(urls) == 2
    assert set(parse_qs(urlsplit(urls[0]).query)["symbols"][0].split(",")) == ELIGIBLE
    assert capture["universe_sha256"] == FINGERPRINT
    assert [a["earnings_keyword_lead"] for a in capture["articles"]] == [False, True]
    assert capture["articles"][0]["historical_backtest_eligible"] is False
    assert capture["articles"][1]["tiers"] == {"ROKU": "expansion"}
    old = capture_news(api_key="k", secret_key="s", observed_at=NOW,
                       fetch_json=lambda _: {"news": [story(created="2026-09-18T05:20:02Z")], "next_page_token": None})
    assert old["articles"][0]["created_in_requested_window"] is False
    assert old["articles"][0]["earnings_keyword_lead"] is False


def test_news_rejects_partial_pages_and_bad_clocks():
    with pytest.raises(ValueError, match="pagination exceeds"):
        capture_news(api_key="k", secret_key="s", observed_at=NOW, max_pages=1,
                     fetch_json=lambda _: {"news": [], "next_page_token": "more"})
    with pytest.raises(ValueError, match="timestamp"):
        capture_news(api_key="k", secret_key="s", observed_at=NOW,
                     fetch_json=lambda _: {"news": [story(created="2026-09-23T00:00:00Z")]})
    with pytest.raises(ValueError, match="duplicate"):
        capture_news(api_key="k", secret_key="s", observed_at=NOW,
                     fetch_json=lambda _: {"news": [story(), story()]})
