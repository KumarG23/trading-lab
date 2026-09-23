"""Read-only IEX market observations for V3; not a consolidated NBBO or fill model."""
from __future__ import annotations

import json
import math
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from .v3_news_history import instant
from .v3_universe import ELIGIBLE, FINGERPRINT

SYMBOLS = frozenset(ELIGIBLE | {"SPY", "QQQ"})


def capture_market(*, api_key: str, secret_key: str, requested_at: datetime, fetch_json=None) -> dict:
    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise ValueError("naive market request")
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
    url = "https://data.alpaca.markets/v2/stocks/snapshots?" + urlencode({"symbols": ",".join(sorted(SYMBOLS)), "feed": "iex"})
    def default_fetch(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
            return json.load(response)
    payload = (fetch_json or default_fetch)(url)
    if not isinstance(payload, dict) or set(payload) - SYMBOLS:
        raise ValueError("unexpected market payload or symbol")
    received = datetime.now(timezone.utc)
    rows = []
    for symbol in sorted(SYMBOLS):
        data = payload.get(symbol)
        quote = data.get("latestQuote") if isinstance(data, dict) else None
        bar = data.get("minuteBar") if isinstance(data, dict) else None
        row = {"symbol": symbol, "quote": None, "minute_bar": None, "missing": True}
        if isinstance(quote, dict):
            stamp = instant(quote["t"])
            bid, ask = quote["bp"], quote["ap"]
            if (stamp > received or type(bid) not in (int, float) or type(ask) not in (int, float)
                    or not math.isfinite(bid) or not math.isfinite(ask) or bid < 0 or ask < 0):
                raise ValueError("invalid IEX quote")
            unpriced = bid == 0 or ask == 0
            crossed = not unpriced and ask < bid
            stale = received - stamp > timedelta(minutes=10)
            row["quote"] = {"source_at": stamp.isoformat(), "bid": bid, "ask": ask,
                            "bid_size": quote.get("bs"), "ask_size": quote.get("as"),
                            "stale_10m": stale, "crossed": crossed, "unpriced": unpriced,
                            "usable_for_spread": not crossed and not unpriced and not stale}
            row["missing"] = False
        if isinstance(bar, dict):
            stamp = instant(bar["t"])
            if stamp > received or not all(type(bar.get(k)) in (int, float) and math.isfinite(bar[k]) and bar[k] > 0 for k in ("o", "h", "l", "c", "v")):
                raise ValueError("invalid IEX minute bar")
            row["minute_bar"] = {"source_at": stamp.isoformat(), "open": bar["o"], "high": bar["h"],
                                 "low": bar["l"], "close": bar["c"], "volume": bar["v"],
                                 "stale_10m": received - stamp > timedelta(minutes=10)}
        rows.append(row)
    return {"schema": "v3-iex-snapshot-v1", "universe_sha256": FINGERPRINT, "feed": "iex",
            "requested_at": requested_at.astimezone(timezone.utc).isoformat(),
            "received_at": received.isoformat(), "symbols_expected": len(SYMBOLS),
            "quotes_present": sum(not row["missing"] for row in rows),
            "quotes_fresh_10m": sum(row["quote"] is not None and not row["quote"]["stale_10m"] for row in rows),
            "quotes_usable_for_spread": sum(row["quote"] is not None and row["quote"]["usable_for_spread"] for row in rows),
            "quotes_crossed": sum(row["quote"] is not None and row["quote"]["crossed"] for row in rows),
            "quotes_unpriced": sum(row["quote"] is not None and row["quote"]["unpriced"] for row in rows),
            "rows": rows, "execution_eligible": False}
