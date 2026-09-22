"""Read-only V3 source adapters. Source timestamps never replace local observation time."""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode

from .catalyst_events import validate_event


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"p", "br", "div", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def sec_events(submissions: dict, *, cik: int, symbol: str, observed_at: datetime, fetch_document, lookback_days: int = 7) -> list[dict]:
    """Only 8-K Item 2.02; use the filing's primary document, not invented earnings text."""
    if int(submissions["cik"]) != cik:
        raise ValueError("SEC CIK mismatch")
    recent = submissions["filings"]["recent"]
    keys = ("accessionNumber", "form", "items", "acceptanceDateTime", "primaryDocument")
    if any(len(recent[k]) != len(recent["form"]) for k in keys):
        raise ValueError("SEC submissions columns differ in length")
    events = []
    for i, form in enumerate(recent["form"]):
        if form != "8-K" or not re.search(r"(?<!\d)2\.02(?!\d)", recent["items"][i] or ""):
            continue
        accepted = datetime.fromisoformat(recent["acceptanceDateTime"][i].replace("Z", "+00:00"))
        if accepted.tzinfo is None:
            # SEC submissions acceptanceDateTime is Eastern; DST resolved by zoneinfo.
            from zoneinfo import ZoneInfo
            accepted = accepted.replace(tzinfo=ZoneInfo("America/New_York"))
        accepted = accepted.astimezone(timezone.utc)
        if accepted < observed_at.astimezone(timezone.utc) - timedelta(days=lookback_days + 1):
            continue
        if len(events) >= 3:
            break
        accession = recent["accessionNumber"][i]
        doc = recent["primaryDocument"][i]
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession) or not re.fullmatch(r"[A-Za-z0-9_.-]+", doc) or doc in {".", ".."}:
            raise ValueError("unsafe SEC document path")
        root = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/"
        header = fetch_document(root + accession + ".txt")[:4096]
        match = re.search(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", header)
        if not match:
            raise ValueError("SEC raw acceptance header missing")
        # Raw filing header is Eastern wall time; submissions JSON may carry a Z
        # suffix on that same clock time. Never treat that suffix as proof of UTC.
        from zoneinfo import ZoneInfo
        raw_time = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
        if raw_time != datetime.fromisoformat(recent["acceptanceDateTime"][i].replace("Z", "+00:00")).replace(tzinfo=None):
            raise ValueError("SEC acceptance clocks disagree")
        accepted = raw_time.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
        if accepted > observed_at.astimezone(timezone.utc):
            raise ValueError("future SEC acceptance time")
        if accepted < observed_at.astimezone(timezone.utc) - timedelta(days=lookback_days):
            continue
        url = root + doc
        page = fetch_document(url)
        parser = _Text()
        parser.feed(page)
        text = " ".join(" ".join(parser.parts).split())
        if not text:
            raise ValueError("empty SEC primary document")
        # No truncation: reject oversized content rather than mislabel a partial filing.
        raw = {"provider": "sec-edgar-8k-primary", "url": url, "symbol": symbol,
               "kind": "earnings", "published_at": accepted.isoformat(), "text": text}
        validate_event(raw, observed_at=observed_at)
        events.append(raw)
    return events


def fetch_sec(cik: int, *, contact: str, agent_name: str = "TradingLabResearch", timeout: float = 15):
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact):
        raise ValueError("SEC contact email required")
    headers = {"User-Agent": f"{agent_name} {contact}", "Accept-Encoding": "identity"}

    def get(url: str) -> str:
        if not (url.startswith("https://www.sec.gov/Archives/edgar/data/") or
                url == f"https://data.sec.gov/submissions/CIK{cik:010d}.json"):
            raise ValueError("unexpected SEC URL")
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ValueError("SEC document exceeds size limit")
            return body.decode("utf-8", errors="replace")

    submissions = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    return submissions, get


def alpaca_news_probe(*, api_key: str, secret_key: str, symbol: str, start: str | None = None, timeout: float = 15) -> dict:
    """Inspect news availability; never log article contents or credentials."""
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,7}", symbol):
        raise ValueError("invalid symbol")
    params = {"symbols": symbol, "limit": 1}
    if start:
        params["start"] = start
        params["sort"] = "asc"
    url = "https://data.alpaca.markets/v1beta1/news?" + urlencode(params)
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
        data = json.load(response)
    rows = data.get("news", [])
    return {"reachable": True, "returned": len(rows), "sample_created_at": rows[0].get("created_at") if rows else None,
            "has_pagination": bool(data.get("next_page_token"))}
