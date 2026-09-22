"""Frozen V3 earnings research universe; attention does not rewrite membership."""
from __future__ import annotations

from hashlib import sha256
import json

CORE = (
    "NVDA", "AMD", "MU", "INTC", "AAPL", "MSFT",
    "AMZN", "GOOGL", "META", "UBER",
    "JPM", "BAC", "WFC", "PYPL",
    "WMT", "TGT", "HD", "DIS",
    "GM", "CAT", "XOM", "CVX", "UNH", "PFE",
)
EXPANSION = (
    "NFLX", "TSLA", "PLTR", "SOFI", "HOOD", "XYZ", "AFRM",
    "RBLX", "SHOP", "CRWD", "DDOG", "SNOW", "DKNG", "ROKU",
    "CCL", "DAL", "F", "FCX", "ON", "MRVL",
)
ELIGIBLE = frozenset(CORE + EXPANSION)
VERSION = "v3-earnings-universe-2026-09-22"
FINGERPRINT = sha256(json.dumps({"version": VERSION, "core": CORE, "expansion": EXPANSION},
                              separators=(",", ":")).encode()).hexdigest()
assert len(CORE) == 24 and len(EXPANSION) == 20 and len(ELIGIBLE) == 44


def tier(symbol: str) -> str | None:
    if symbol in CORE:
        return "core"
    if symbol in EXPANSION:
        return "expansion"
    return None


def focus(symbol: str, *, verified_earnings: bool) -> bool:
    """Every core name stays watched; expansion needs verified earnings/guidance.

    News-count spikes are features, never admission criteria. All eligible
    names and no-event periods remain in the reference cohort.
    """
    return symbol in CORE or (symbol in EXPANSION and verified_earnings)
