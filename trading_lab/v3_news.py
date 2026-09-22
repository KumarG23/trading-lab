"""Bounded read-only Alpaca news capture for forward research, not a trade signal."""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from .v3_universe import ELIGIBLE, FINGERPRINT, tier


def capture_news(*, api_key: str, secret_key: str, observed_at: datetime,
                 hours: int = 24, max_pages: int = 4, fetch_json=None) -> dict:
    """Require complete pages; preserve all eligible stories, not just exciting ones."""
    if observed_at.tzinfo is None or not 1 <= hours <= 24 or not 1 <= max_pages <= 10:
        raise ValueError("invalid capture bounds")
    seen = observed_at.astimezone(timezone.utc)
    start = seen - timedelta(hours=hours)
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}

    def default_fetch(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as response:
            return json.load(response)

    fetch = fetch_json or default_fetch
    rows, token, tokens = [], None, set()
    for _ in range(max_pages):
        params = {"symbols": ",".join(sorted(ELIGIBLE)), "start": start.isoformat(),
                  "end": seen.isoformat(), "sort": "asc", "limit": 50}
        if token:
            params["page_token"] = token
        payload = fetch("https://data.alpaca.markets/v1beta1/news?" + urlencode(params))
        if not isinstance(payload.get("news"), list):
            raise ValueError("invalid Alpaca news payload")
        rows.extend(payload["news"])
        token = payload.get("next_page_token")
        if not token:
            break
        if not isinstance(token, str) or token in tokens:
            raise ValueError("repeated or invalid Alpaca pagination token")
        tokens.add(token)
    else:
        raise ValueError("Alpaca pagination exceeds bound; no partial capture")
    received = datetime.now(timezone.utc)
    observations = []
    ids = set()
    for row in rows:
        ident = row.get("id")
        published = datetime.fromisoformat(str(row.get("created_at", "")).replace("Z", "+00:00"))
        if not isinstance(ident, int) or ident in ids or published.tzinfo is None or published > seen:
            raise ValueError("invalid/duplicate news id or timestamp")
        ids.add(ident)
        headline = row.get("headline")
        symbols = row.get("symbols")
        if not isinstance(headline, str) or not headline.strip() or not isinstance(symbols, list):
            raise ValueError("invalid news headline or symbols")
        eligible = sorted(set(symbols) & ELIGIBLE)
        if not eligible:
            raise ValueError("non-eligible article returned for bounded query")
        # Classification is a *lead*, never verified earnings or automatic admission.
        lead = start <= published <= seen and bool(re.search(r"\b(earnings|quarterly results|financial results|guidance)\b", headline, re.I))
        observations.append({"provider": "alpaca-news", "provider_id": ident,
                             "headline": headline, "symbols": eligible,
                             "url": row.get("url"), "source_created_at": published.isoformat(),
                             "source_updated_at": row.get("updated_at"),
                             "created_in_requested_window": start <= published <= seen,
                             "first_seen_at": received.isoformat(), "earnings_keyword_lead": lead,
                             "tiers": {s: tier(s) for s in eligible},
                             "historical_backtest_eligible": False})
    return {"schema": "v3-news-snapshot-v1", "universe_sha256": FINGERPRINT,
            "observed_at": received.isoformat(), "window_start": start.isoformat(),
            "window_end": seen.isoformat(), "articles": observations}
