"""Append-only, read-only-source event intake for V3 research. No trading authority."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

KINDS = frozenset({"earnings", "guidance"})
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.]{0,7}\Z")


def _instant(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("naive timestamp")
    return timestamp.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_event(raw: dict, *, observed_at: datetime) -> dict:
    """Record a claimed publication time and the actual intake time separately.

    A publisher timestamp never establishes historical availability. Decisions
    may use an event only after max(published_at, first_seen_at).
    """
    if not isinstance(raw, dict) or set(raw) != {"provider", "url", "symbol", "kind", "published_at", "text"}:
        raise ValueError("event must have exactly provider,url,symbol,kind,published_at,text")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("naive observation time")
    seen = observed_at.astimezone(timezone.utc)
    published = _instant(raw["published_at"])
    if published > seen:
        raise ValueError("future publication time")
    provider, url, symbol, kind, text = (raw[k] for k in ("provider", "url", "symbol", "kind", "text"))
    if not isinstance(provider, str) or not 1 <= len(provider) <= 80 or not provider.strip():
        raise ValueError("invalid provider")
    if not isinstance(url, str) or len(url) > 2048 or urlsplit(url).scheme != "https" or not urlsplit(url).hostname or urlsplit(url).username or urlsplit(url).password:
        raise ValueError("invalid https source URL")
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        raise ValueError("invalid symbol")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("unsupported event kind")
    if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 100_000:
        raise ValueError("invalid event text")
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    key = json.dumps([provider, url, symbol, kind, _iso(published)], separators=(",", ":"))
    return {
        "schema": "catalyst-event-v1", "id": hashlib.sha256(key.encode()).hexdigest(),
        "provider": provider, "url": url, "symbol": symbol, "kind": kind,
        "published_at": _iso(published), "first_seen_at": _iso(seen),
        "available_at": _iso(seen), "text_sha256": content_hash, "text": text,
        "text_model_features": None, "historical_backtest_eligible": False,
    }


def available_events(events: list[dict], decision_at: str) -> list[dict]:
    decision = _instant(decision_at)
    return [event for event in events if _instant(event["available_at"]) <= decision]


def load_ledger(path: Path) -> list[dict]:
    """Read back stored rows only if immutable content and availability agree."""
    rows = []
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("schema") != "catalyst-event-v1" or row.get("id") in ids:
            raise ValueError("invalid or duplicate ledger entry")
        try:
            text_hash = hashlib.sha256(row["text"].encode("utf-8")).hexdigest()
            first_seen = _instant(row["first_seen_at"])
            published = _instant(row["published_at"])
            available = _instant(row["available_at"])
            key = json.dumps([row["provider"], row["url"], row["symbol"], row["kind"], _iso(published)], separators=(",", ":"))
            expected_id = hashlib.sha256(key.encode()).hexdigest()
        except (KeyError, TypeError) as exc:
            raise ValueError("malformed ledger entry") from exc
        if (row["text_sha256"] != text_hash or row["id"] != expected_id
                or published > first_seen or available != first_seen
                or row.get("historical_backtest_eligible") is not False):
            raise ValueError("ledger content/provenance mismatch")
        ids.add(row["id"])
        rows.append(row)
    return rows


def import_jsonl(input_path: Path, ledger_path: Path, *, observed_at: datetime | None = None) -> dict:
    """Validate whole batch before append; never accept supplied first_seen_at."""
    raw_lines = input_path.read_text(encoding="utf-8-sig").splitlines()
    observed_at = observed_at or datetime.now(timezone.utc)
    batch = [validate_event(json.loads(line), observed_at=observed_at) for line in raw_lines if line.strip()]
    if not batch:
        raise ValueError("empty event batch")
    if len({event["id"] for event in batch}) != len(batch):
        raise ValueError("duplicate event in batch")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    # Advisory lock lives in a separate file: atomic append remains serialized
    # even when another process starts with a missing ledger.
    with ledger_path.with_suffix(ledger_path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = {row["id"]: row for row in load_ledger(ledger_path)} if ledger_path.exists() else {}
        new = []
        for event in batch:
            previous = existing.get(event["id"])
            if previous:
                if previous["text_sha256"] != event["text_sha256"]:
                    raise ValueError("source revision conflicts with existing event")
                continue
            new.append(event)
        if new:
            with ledger_path.open("a", encoding="utf-8") as output:
                for event in new:
                    output.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
                output.flush()
                os.fsync(output.fileno())
    return {"input": len(batch), "appended": len(new), "already_present": len(batch) - len(new), "ledger": str(ledger_path)}
