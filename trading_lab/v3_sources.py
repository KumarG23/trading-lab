"""Read-only V3 source adapters. Source timestamps never replace local observation time."""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

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


def sec_events(submissions: dict, *, cik: int, symbol: str, observed_at: datetime, fetch_document, lookback_days: int = 7, stats: dict | None = None) -> list[dict]:
    """Only Item 2.02 filings with a real EX-99.1 release; no cover-page proxy."""
    if stats is not None:
        stats.update(item_202_recent=0, without_single_exhibit=0, skipped_cap=0, matched=0)
    if int(submissions["cik"]) != cik or symbol not in submissions.get("tickers", []):
        raise ValueError("SEC CIK/ticker mismatch")
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
            accepted = accepted.replace(tzinfo=ZoneInfo("America/New_York"))
        accepted = accepted.astimezone(timezone.utc)
        if accepted < observed_at.astimezone(timezone.utc) - timedelta(days=lookback_days + 1):
            continue
        if stats is not None:
            stats["item_202_recent"] += 1
        if len(events) >= 3:
            if stats is not None:
                stats["skipped_cap"] += 1
            continue
        accession = recent["accessionNumber"][i]
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            raise ValueError("unsafe SEC accession")
        root = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/"
        filing_text = fetch_document(root + accession + ".txt")
        header = filing_text[:4096]
        match = re.search(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", header)
        if not match:
            raise ValueError("SEC raw acceptance header missing")
        # SEC submissions has been observed using BOTH conventions for the same
        # accession: Z on the Eastern wall clock, then a corrected true UTC Z.
        # Anchor on the raw Eastern header and accept only either exact clock.
        raw_time = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
        raw_utc = raw_time.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
        json_time = datetime.fromisoformat(recent["acceptanceDateTime"][i].replace("Z", "+00:00"))
        if not (json_time.replace(tzinfo=None) == raw_time
                or (json_time.tzinfo is not None and json_time.astimezone(timezone.utc) == raw_utc)):
            raise ValueError("SEC acceptance clocks disagree")
        accepted = raw_utc
        if accepted > observed_at.astimezone(timezone.utc):
            raise ValueError("future SEC acceptance time")
        if accepted < observed_at.astimezone(timezone.utc) - timedelta(days=lookback_days):
            continue
        matches = re.findall(r"<DOCUMENT>\s*<TYPE>\s*([^\r\n]+).*?<FILENAME>\s*([^\r\n]+)",
                             filing_text, flags=re.IGNORECASE | re.DOTALL)
        releases = [name.strip() for doc_type, name in matches if doc_type.strip().upper() == "EX-99.1"]
        if len(releases) != 1:
            if stats is not None:
                stats["without_single_exhibit"] += 1
            continue  # no unambiguous release; never label the 8-K cover as earnings text
        doc = releases[0]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", doc) or doc in {".", ".."}:
            raise ValueError("unsafe SEC document path")
        url = root + doc
        page = fetch_document(url)
        parser = _Text()
        parser.feed(page)
        text = " ".join(" ".join(parser.parts).split())
        if not text:
            raise ValueError("empty SEC exhibit")
        # No truncation: reject oversized content rather than mislabel a partial filing.
        raw = {"provider": "sec-edgar-ex-99.1", "url": url, "symbol": symbol,
               "kind": "earnings", "published_at": accepted.isoformat(), "text": text}
        validate_event(raw, observed_at=observed_at)
        events.append(raw)
        if stats is not None:
            stats["matched"] += 1
    return events


def fetch_sec(cik: int, *, contact: str, agent_name: str = "TradingLabResearch", timeout: float = 15):
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact):
        raise ValueError("SEC contact email required")
    headers = {"User-Agent": f"{agent_name} {contact}", "Accept-Encoding": "identity"}

    def get(url: str) -> str:
        if not (url.startswith("https://www.sec.gov/Archives/edgar/data/") or
                url == f"https://data.sec.gov/submissions/CIK{cik:010d}.json"):
            raise ValueError("unexpected SEC URL")
        # A complete 8-K bundle can exceed the individual exhibit cap (CCL: 2.35 MB).
        # Keep both reads bounded; never parse a truncated submission as complete.
        size_limit = (8_000_000 if url.startswith("https://data.sec.gov/submissions/") else
                      4_000_000 if re.search(r"/\d{10}-\d{2}-\d{6}\.txt$", url) else 2_000_000)
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
            body = response.read(size_limit + 1)
            if len(body) > size_limit:
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
