from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def load_symbols(symbols_csv: str, *, watchlist_file: str | Path | None = None) -> list[str]:
    if watchlist_file:
        path = Path(watchlist_file)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
            file_symbols = _extract_symbols(payload)
            if file_symbols:
                return file_symbols
    return _dedupe(s.strip().upper() for s in symbols_csv.split(",") if s.strip())


def load_scanner_context(
    watchlist_file: str | Path,
    *,
    decision_at: datetime,
) -> dict[str, dict[str, Any]]:
    """Load a same-session scanner snapshot that existed before the decision."""
    path = Path(watchlist_file)
    if not path.exists():
        return {}
    if decision_at.tzinfo is None or decision_at.utcoffset() is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(str(payload["generated_at"]).replace("Z", "+00:00"))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        return {}
    generated_et = generated_at.astimezone(ET)
    decision_et = decision_at.astimezone(ET)
    if generated_et.date() != decision_et.date() or generated_et > decision_et:
        return {}
    rows = payload.get("top_matches")
    if not isinstance(rows, list):
        return {}
    context: dict[str, dict[str, Any]] = {}
    for rank, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        context[symbol] = {
            "scanner_generated_at": generated_at.isoformat(),
            "scanner_rank": rank,
            "scanner_score": _finite_number(row.get("score")),
            "scanner_change_pct": _finite_number(row.get("change_pct")),
            "scanner_relative_volume": _finite_number(row.get("relative_volume")),
            "scanner_dollar_volume": _finite_number(row.get("dollar_volume")),
            "scanner_intraday_range_pct": _finite_number(row.get("intraday_range_pct")),
            "scanner_price": _finite_number(row.get("price")),
        }
    return context


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _extract_symbols(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        value = payload.get("watchlist") or payload.get("symbols") or []
    else:
        value = payload
    if not isinstance(value, list):
        return []
    return _dedupe(str(item).strip().upper() for item in value if str(item).strip())


def _dedupe(symbols: Any) -> list[str]:
    out: list[str] = []
    for symbol in symbols:
        if symbol not in out:
            out.append(symbol)
    return out
