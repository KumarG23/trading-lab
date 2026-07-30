from __future__ import annotations

import math
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

FEATURE_SCHEMA_VERSION = "candidate-decision-features-v5"

STRATEGIES = (
    "opening-range-breakout",
    "vwap-trend-imbalance",
    "vwap-reclaim",
    "momentum-pullback",
    "unknown",
)
DIRECTIONS = ("long", "short", "unknown")
REGIMES = ("bullish", "not_bullish", "neutral", "unknown")
ET = ZoneInfo("America/New_York")
TIME_BUCKETS = ("opening_range", "morning", "midday", "afternoon", "power_hour", "unknown")

NUMERIC_FEATURES = (
    "minutes_since_open",
    "volume_ratio",
    "dollar_volume_log",
    "atr_pct",
    "range_pct",
    "gap_pct",
    "market_return",
    "regime_score",
    "stop_distance_pct",
    "planned_reward_risk",
    "risk_dollars_log",
    "opening_range_width_pct",
    "opening_range_breakout_distance_pct",
    "vwap_distance_pct",
    "vwap_slope_pct",
    "pullback_depth_pct",
    "short_momentum_1bar_pct",
    "short_momentum_3bar_pct",
    "short_momentum_5bar_pct",
    "scanner_score",
)

FEATURE_NAMES = (
    tuple(f"strategy.{item}" for item in STRATEGIES)
    + tuple(f"direction.{item}" for item in DIRECTIONS)
    + tuple(f"regime.{item}" for item in REGIMES)
    + tuple(f"time_bucket.{item}" for item in TIME_BUCKETS)
    + NUMERIC_FEATURES
)
FEATURE_SCHEMA_SHA256 = hashlib.sha256(
    json.dumps(
        {"schema_version": FEATURE_SCHEMA_VERSION, "feature_names": list(FEATURE_NAMES)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()

REQUIRED_FEATURES = (
    "strategy_identity",
    "minutes_since_open",
    "stop_distance_pct",
    "planned_reward_risk",
    "volume_ratio",
)


def decision_features(row: dict[str, Any]) -> dict[str, float]:
    """Return v5 decision-time features only.

    The contract intentionally excludes realized outcome, fill, and path fields.
    Missing numeric values are represented as NaN so downstream imputers and
    coverage diagnostics see absence instead of a synthetic zero.
    """
    candidate = _candidate(row)
    context = _mapping(candidate.get("market_context"))
    entry = _number(candidate.get("planned_entry"))
    stop = _number(candidate.get("stop"))
    target = _number(candidate.get("target"))
    direction = _category(candidate.get("direction"), DIRECTIONS)
    strategy = _category(candidate.get("strategy_id"), STRATEGIES)
    regime = _regime(context.get("regime") or _mapping(row.get("features")).get("regime"))
    minutes = _minutes_since_open(context.get("signal_timestamp") or row.get("decision_at"))
    features: dict[str, float] = {}
    for value in STRATEGIES:
        features[f"strategy.{value}"] = 1.0 if strategy == value else 0.0
    for value in DIRECTIONS:
        features[f"direction.{value}"] = 1.0 if direction == value else 0.0
    for value in REGIMES:
        features[f"regime.{value}"] = 1.0 if regime == value else 0.0
    bucket = _time_bucket(minutes)
    for value in TIME_BUCKETS:
        features[f"time_bucket.{value}"] = 1.0 if bucket == value else 0.0

    volume_ratio = _first_number(context, "relative_volume", "volume_ratio", "rel_volume")
    current_volume = _first_number(context, "volume", "current_volume", "bar_volume")
    dollar_volume = _first_number(context, "dollar_volume", "dollar_volume_proxy")
    if dollar_volume is None and entry is not None and current_volume is not None:
        dollar_volume = entry * current_volume

    atr = _first_number(context, "atr", "atr_dollars")
    high = _first_number(context, "high", "current_high")
    low = _first_number(context, "low", "current_low")
    opening_range_high = _number(context.get("opening_range_high"))
    opening_range_low = _number(context.get("opening_range_low"))
    vwap = _number(context.get("vwap"))
    previous_vwap = _number(context.get("previous_vwap"))
    pullback_vwap = _number(context.get("pullback_vwap"))
    previous_close = _number(context.get("previous_close"))
    close_3 = _first_number(context, "close_3_bars_ago", "close_3m_ago")
    close_5 = _first_number(context, "close_5_bars_ago", "close_5m_ago")

    features.update(
        {
            "minutes_since_open": _round(minutes),
            "volume_ratio": _round(volume_ratio),
            "dollar_volume_log": _round(math.log10(dollar_volume)) if dollar_volume and dollar_volume > 0 else np.nan,
            "atr_pct": _pct(atr, entry),
            "range_pct": _range_pct(context, high, low, entry),
            "gap_pct": _round(_first_number(context, "gap_pct", "gap_percent")),
            "market_return": _round(_first_number(context, "market_return", "spy_return", "qqq_return")),
            "regime_score": _round(_number(context.get("regime_score"))),
            "stop_distance_pct": _stop_distance(entry, stop),
            "planned_reward_risk": _reward_risk(entry, stop, target),
            "risk_dollars_log": _log_amount(_number(candidate.get("risk_dollars"))),
            "opening_range_width_pct": _opening_range_width(entry, opening_range_high, opening_range_low),
            "opening_range_breakout_distance_pct": _opening_range_breakout_distance(
                direction, entry, opening_range_high, opening_range_low
            ),
            "vwap_distance_pct": _vwap_distance(context, entry),
            "vwap_slope_pct": _signed_pct_delta(vwap, previous_vwap, entry),
            "pullback_depth_pct": _signed_pct_delta(entry, pullback_vwap, entry),
            "short_momentum_1bar_pct": _signed_pct_delta(entry, previous_close, previous_close),
            "short_momentum_3bar_pct": _signed_pct_delta(entry, close_3, close_3),
            "short_momentum_5bar_pct": _signed_pct_delta(entry, close_5, close_5),
            "scanner_score": _round(_number(context.get("scanner_score"))),
        }
    )
    return features


def build_feature_contract(rows: list[dict[str, Any]]) -> dict[str, Any]:
    names = list(FEATURE_NAMES)
    matrix = [
        [float(decision_features(row).get(name, np.nan)) for name in names]
        for row in rows
    ]
    return {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": names,
        "matrix": matrix,
        "rows": len(rows),
    }


def feature_coverage_diagnostics(
    rows: list[dict[str, Any]],
    *,
    required_min_coverage: float = 0.8,
) -> dict[str, Any]:
    features_by_row = [decision_features(row) for row in rows]
    samples = len(rows)
    required = {
        "strategy_identity": [not _candidate(row).get("strategy_id") in (None, "", "unknown") for row in rows],
        "minutes_since_open": [_finite(features.get("minutes_since_open")) for features in features_by_row],
        "stop_distance_pct": [_finite(features.get("stop_distance_pct")) for features in features_by_row],
        "planned_reward_risk": [_finite(features.get("planned_reward_risk")) for features in features_by_row],
        "volume_ratio": [_finite(features.get("volume_ratio")) for features in features_by_row],
    }
    diagnostics: dict[str, Any] = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "samples": samples,
        "required": {},
        "features": {},
        "blockers": [],
        "warnings": [],
    }
    for name, values in required.items():
        present = sum(bool(value) for value in values)
        coverage = present / samples if samples else 0.0
        diagnostics["required"][name] = {
            "present": present,
            "missing": samples - present,
            "coverage": round(coverage, 6),
        }
        if coverage < required_min_coverage:
            diagnostics["blockers"].append(
                f"required_feature_coverage_low:{name}:{coverage:.4f}<{required_min_coverage:.4f}"
            )
    for name in FEATURE_NAMES:
        present = sum(_finite(features.get(name)) for features in features_by_row)
        diagnostics["features"][name] = {
            "present": present,
            "missing": samples - present,
            "coverage": round(present / samples, 6) if samples else 0.0,
        }
    return diagnostics


def _candidate(row: dict[str, Any]) -> dict[str, Any]:
    candidate = row.get("candidate") if isinstance(row, dict) else None
    return candidate if isinstance(candidate, dict) else {}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _category(value: Any, allowed: tuple[str, ...]) -> str:
    normalized = str(value or "unknown").strip().lower()
    return normalized if normalized in allowed else "unknown"


def _regime(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    aliases = {"bull": "bullish", "bear": "not_bullish", "not-bullish": "not_bullish"}
    return _category(aliases.get(normalized, normalized), REGIMES)


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first_number(mapping: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        number = _number(mapping.get(key))
        if number is not None:
            return number
    return None


def _round(value: float | None) -> float:
    return round(value, 8) if value is not None and math.isfinite(value) else np.nan


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _pct(value: float | None, denominator: float | None) -> float:
    if value is None or denominator in (None, 0):
        return np.nan
    return round(value / abs(denominator), 8)


def _signed_pct_delta(value: float | None, base: float | None, denominator: float | None) -> float:
    if value is None or base is None or denominator in (None, 0):
        return np.nan
    return round((value - base) / abs(denominator), 8)


def _stop_distance(entry: float | None, stop: float | None) -> float:
    if entry in (None, 0) or stop is None:
        return np.nan
    return round(abs(entry - stop) / abs(entry), 8)


def _reward_risk(entry: float | None, stop: float | None, target: float | None) -> float:
    if entry is None or stop is None or target is None:
        return np.nan
    risk = abs(entry - stop)
    if risk <= 0:
        return np.nan
    return round(abs(target - entry) / risk, 8)


def _log_amount(value: float | None) -> float:
    return round(math.log10(value), 8) if value and value > 0 else np.nan


def _opening_range_width(entry: float | None, high: float | None, low: float | None) -> float:
    if entry in (None, 0) or high is None or low is None:
        return np.nan
    return round(abs(high - low) / abs(entry), 8)


def _opening_range_breakout_distance(
    direction: str,
    entry: float | None,
    high: float | None,
    low: float | None,
) -> float:
    if entry in (None, 0):
        return np.nan
    if direction == "short" and low is not None:
        return round((low - entry) / abs(entry), 8)
    if high is not None:
        return round((entry - high) / abs(entry), 8)
    return np.nan


def _vwap_distance(context: dict[str, Any], entry: float | None) -> float:
    alias = _first_number(context, "distance_from_vwap_pct", "vwap_distance_pct")
    if alias is not None:
        return round(alias, 8)
    raw = _number(context.get("distance_from_vwap"))
    if raw is None:
        return np.nan
    if abs(raw) <= 1:
        return round(raw / abs(entry), 8) if entry else round(raw, 8)
    return round(raw / abs(entry), 8) if entry else np.nan


def _range_pct(context: dict[str, Any], high: float | None, low: float | None, entry: float | None) -> float:
    alias = _first_number(context, "range_pct", "range_percent")
    if alias is not None:
        return round(alias, 8)
    if high is not None and low is not None and entry not in (None, 0):
        return round((high - low) / abs(entry), 8)
    return np.nan


def _minutes_since_open(value: Any) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(ET)
    return float(parsed.hour * 60 + parsed.minute - (9 * 60 + 30))


def _time_bucket(minutes: float | None) -> str:
    if minutes is None or not math.isfinite(minutes):
        return "unknown"
    if minutes < 10:
        return "opening_range"
    if minutes < 90:
        return "morning"
    if minutes < 270:
        return "midday"
    if minutes < 330:
        return "afternoon"
    return "power_hour"
