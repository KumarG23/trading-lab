from datetime import datetime, timedelta, timezone
import json

import pytest

from trading_lab.v3_news import capture_news
from trading_lab.v3_news_history import audit_news, load_snapshots, next_window
from trading_lab.v3_universe import FINGERPRINT

NOW = datetime(2026, 9, 22, 23, tzinfo=timezone.utc)


def article(ident, headline="Quarterly results", url="https://example.com/a"):
    return {"provider": "alpaca-news", "provider_id": ident, "headline": headline,
            "url": url, "source_created_at": "2026-09-22T22:00:00Z",
            "first_seen_at": NOW.isoformat(), "earnings_keyword_lead": True}


def snapshot(*articles, end=NOW):
    return {"schema": "v3-news-snapshot-v1", "universe_sha256": FINGERPRINT,
            "observed_at": end.isoformat(), "window_start": (end - timedelta(hours=1)).isoformat(),
            "window_end": end.isoformat(), "articles": list(articles)}


def test_reconcile_keeps_provider_ids_and_counts_repeat_and_exact_syndication():
    first = snapshot(article(1), article(2, url="https://example.com/a?ref=wire"))
    later = snapshot(article(1), article(3, headline="Unrelated", url="https://example.com/b"))
    report = audit_news([first, later])
    assert report["article_observations"] == 4
    assert report["distinct_provider_ids"] == 3
    assert report["repeat_observations"] == 1
    assert report["distinct_story_groups"] == 2
    assert report["possible_syndicated_copies"] == 1


def test_fail_closed_on_bad_provenance_and_gap(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot(article(1))))
    loaded = load_snapshots(tmp_path)
    start, end = next_window(loaded, now=NOW + timedelta(minutes=10))
    assert start == NOW - timedelta(minutes=30) and end == NOW + timedelta(minutes=10)
    with pytest.raises(ValueError, match="gap exceeds"):
        next_window(loaded, now=NOW + timedelta(hours=25))
    path.write_text(json.dumps(snapshot(article(1), article(1))))
    with pytest.raises(ValueError, match="provenance"):
        load_snapshots(tmp_path)
    bad = snapshot(article(1))
    bad["universe_sha256"] = "changed"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="schema/universe"):
        load_snapshots(tmp_path)


def test_incremental_capture_window_is_bounded_and_visible_in_request():
    captured_urls = []
    def fetch(url):
        captured_urls.append(url)
        return {"news": [], "next_page_token": None}
    start = NOW - timedelta(minutes=40)
    result = capture_news(api_key="k", secret_key="s", observed_at=NOW,
                          window_start=start, fetch_json=fetch)
    assert result["window_start"] == start.isoformat()
    assert "start=2026-09-22T22%3A20%3A00%2B00%3A00" in captured_urls[0]
    with pytest.raises(ValueError, match="bounds"):
        capture_news(api_key="k", secret_key="s", observed_at=NOW,
                     window_start=NOW - timedelta(hours=25), fetch_json=fetch)
