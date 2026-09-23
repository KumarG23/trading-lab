"""Offline reconciliation of private Alpaca snapshots; never changes source evidence."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .v3_universe import FINGERPRINT


def instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("naive timestamp")
    return stamp.astimezone(timezone.utc)


def load_snapshots(directory: Path, *, latest_only: bool = False) -> list[dict]:
    snapshots = []
    paths = sorted(directory.glob("*.json"))
    for path in (paths[-1:] if latest_only else paths):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("schema") != "v3-news-snapshot-v1" or record.get("universe_sha256") != FINGERPRINT:
            raise ValueError(f"unknown news snapshot schema/universe: {path.name}")
        observed = instant(record["observed_at"])
        start, end = instant(record["window_start"]), instant(record["window_end"])
        if not start < end <= observed or not isinstance(record.get("articles"), list):
            raise ValueError(f"invalid news snapshot window: {path.name}")
        ids = set()
        for article in record["articles"]:
            ident = article["provider_id"]
            seen = instant(article["first_seen_at"])
            created = instant(article["source_created_at"])
            if (article.get("provider") != "alpaca-news" or type(ident) is not int or ident in ids
                    or seen != observed or created > seen or not isinstance(article.get("headline"), str)
                    or not article["headline"].strip()):
                raise ValueError(f"invalid news article provenance: {path.name}")
            ids.add(ident)
        snapshots.append(record)
    return sorted(snapshots, key=lambda s: instant(s["observed_at"]))


def next_window(snapshots: list[dict], *, now: datetime, overlap: timedelta = timedelta(minutes=30)) -> tuple[datetime, datetime]:
    """Overlap prior query to tolerate delays; refuse a gap larger than one day."""
    if now.tzinfo is None or now.utcoffset() is None or overlap < timedelta(0):
        raise ValueError("invalid next-window clock or overlap")
    now = now.astimezone(timezone.utc)
    if not snapshots:
        return now - timedelta(hours=24), now
    last = max(instant(s["window_end"]) for s in snapshots)
    if last > now or now - last > timedelta(hours=24):
        raise ValueError("news capture gap exceeds 24 hours or last window is in future")
    return max(now - timedelta(hours=24), last - overlap), now


def _story_key(article: dict) -> str:
    # Exact normalized headline + calendar date only: conservative syndication
    # heuristic, not a fuzzy similarity claim. Keep every original provider ID.
    headline = re.sub(r"\W+", " ", article["headline"].casefold()).strip()
    created_day = instant(article["source_created_at"]).date().isoformat()
    url = article.get("url")
    if isinstance(url, str) and url.startswith("https://"):
        parsed = urlsplit(url)
        canonical = urlunsplit((parsed.scheme, parsed.netloc.casefold(), parsed.path.rstrip("/"), "", ""))
    else:
        canonical = ""
    # An identical article URL across headline edits should remain one story.
    key = canonical if canonical else created_day + ":" + headline
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def audit_news(snapshots: list[dict]) -> dict:
    """Counts only; no article contents or potentially sensitive URLs in report."""
    provider_ids: dict[int, dict] = {}
    observations = 0
    for snapshot in snapshots:
        for article in snapshot["articles"]:
            observations += 1
            ident = article["provider_id"]
            prior = provider_ids.get(ident)
            if prior is None:
                provider_ids[ident] = article
            elif instant(article["first_seen_at"]) < instant(prior["first_seen_at"]):
                provider_ids[ident] = article
    groups: dict[str, set[int]] = {}
    for ident, article in provider_ids.items():
        groups.setdefault(_story_key(article), set()).add(ident)
    return {"snapshots": len(snapshots), "article_observations": observations,
            "distinct_provider_ids": len(provider_ids),
            "repeat_observations": observations - len(provider_ids),
            "distinct_story_groups": len(groups),
            "possible_syndicated_copies": sum(len(ids) - 1 for ids in groups.values()),
            "keyword_leads_by_provider_id": sum(bool(row["earnings_keyword_lead"]) for row in provider_ids.values()),
            "last_window_end": max((s["window_end"] for s in snapshots), default=None)}
