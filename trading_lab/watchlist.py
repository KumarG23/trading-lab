from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
