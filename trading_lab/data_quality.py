from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

WARNING_EVIDENCE_FLAGS = {
    "entry_bar_path_unknown",
    "missing_minutes",
}
EXCLUSION_EVIDENCE_FLAGS = {
    "same_bar_stop_target",
}
FATAL_EVIDENCE_FLAGS = {
    "stale_data",
    "stale_quote",
    "missing_provenance",
    "impossible_chronology",
    "duplicate_bars",
    "non_monotonic",
    "zero_volume",
}


def validate_minute_bars(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic structural quality counts for minute OHLCV bars."""
    duplicate_bars = 0
    non_monotonic = 0
    zero_volume = 0
    seen: set[tuple[str, datetime]] = set()
    grouped: dict[tuple[str, object], set[datetime]] = defaultdict(set)
    previous_by_symbol: dict[str, datetime] = {}
    for bar in bars:
        symbol = str(bar.get("symbol") or "").upper()
        timestamp = _timestamp(str(bar["timestamp"]))
        key = (symbol, timestamp)
        if key in seen:
            duplicate_bars += 1
        else:
            seen.add(key)
            grouped[(symbol, timestamp.date())].add(timestamp)
        previous = previous_by_symbol.get(symbol)
        if previous is not None and timestamp < previous:
            non_monotonic += 1
        previous_by_symbol[symbol] = timestamp
        if float(bar.get("volume") or 0.0) <= 0:
            zero_volume += 1
    missing_minutes = 0
    for timestamps in grouped.values():
        ordered = sorted(timestamps)
        for earlier, later in zip(ordered, ordered[1:]):
            gap = int((later - earlier).total_seconds() // 60) - 1
            missing_minutes += max(0, gap)
    counts = {
        "duplicate_bars": duplicate_bars,
        "missing_minutes": missing_minutes,
        "non_monotonic": non_monotonic,
        "zero_volume": zero_volume,
    }
    flags = sorted(name for name, count in counts.items() if count)
    fatal = any(counts[name] for name in ("duplicate_bars", "non_monotonic", "zero_volume"))
    return {"ok": not flags, "fatal": fatal, **counts, "flags": flags, "bars": len(bars)}


def classify_evidence_quality_flags(flags: list[str] | tuple[str, ...] | None) -> dict[str, Any]:
    """Classify preserved evidence flags by promotion severity.

    Unknown flags are fatal so new data defects cannot be silently laundered by
    older readiness code.
    """
    preserved = sorted({str(flag) for flag in (flags or []) if str(flag)})
    warnings = sorted(flag for flag in preserved if flag in WARNING_EVIDENCE_FLAGS)
    exclusions = sorted(flag for flag in preserved if flag in EXCLUSION_EVIDENCE_FLAGS)
    fatal = sorted(
        flag for flag in preserved
        if flag in FATAL_EVIDENCE_FLAGS
        or flag not in WARNING_EVIDENCE_FLAGS | EXCLUSION_EVIDENCE_FLAGS
    )
    return {
        "flags": preserved,
        "warning_flags": warnings,
        "exclusion_flags": exclusions,
        "fatal_flags": fatal,
        "has_warning": bool(warnings),
        "has_exclusion": bool(exclusions),
        "has_fatal": bool(fatal),
    }


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"bar timestamp must be timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)
