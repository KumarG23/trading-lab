from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
from typing import Any

from trading_lab.decision_features import (
    FEATURE_SCHEMA_SHA256,
    FEATURE_SCHEMA_VERSION,
    decision_features,
    feature_coverage_diagnostics,
)
STRATEGY_VERSIONS = {
    "opening-range-breakout": "1",
    "vwap-trend-imbalance": "1",
    "vwap-reclaim": "1",
    "momentum-pullback": "1",
}
STRATEGY_MODULES = {
    "opening-range-breakout": "opening_range_breakout.py",
    "vwap-trend-imbalance": "vwap_trend_imbalance.py",
    "vwap-reclaim": "vwap_reclaim.py",
    "momentum-pullback": "momentum_pullback.py",
}


def candidate_event_provenance(candidate: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    strategy_id = str(candidate.get("strategy_id") or "unknown")
    context = _safe_mapping(candidate.get("market_context"), "market_context")
    source_name = STRATEGY_MODULES.get(strategy_id)
    source_path = Path(__file__).with_name(source_name) if source_name else None
    if source_path is not None and source_path.exists():
        source_bytes = source_path.read_bytes() + Path(__file__).with_name("strategy_suite.py").read_bytes()
        strategy_hash = hashlib.sha256(source_bytes).hexdigest()
    else:
        strategy_hash = f"source-missing:{strategy_id}"
    features = {
        "planned_entry": candidate.get("planned_entry"),
        "stop": candidate.get("stop"),
        "target": candidate.get("target"),
        "risk_dollars": candidate.get("risk_dollars"),
        "market_context": context,
        "rule_checklist": _safe_mapping(candidate.get("rule_checklist"), "rule_checklist"),
        "decision_feature_schema_sha256": FEATURE_SCHEMA_SHA256,
        "decision_feature_coverage": feature_coverage_diagnostics([{"candidate": candidate}]),
        "normalized_decision_features": _finite_features(decision_features({"candidate": candidate})),
    }
    return {
        "run_id": str(run.get("run_id") or ""),
        "decision_at": str(run.get("decision_at") or ""),
        "data_cutoff_at": _bar_end(context.get("signal_timestamp")),
        "code_sha": str(run.get("code_sha") or "unknown"),
        "config_hash": str(run.get("config_hash") or "unknown"),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "strategy_version": STRATEGY_VERSIONS.get(strategy_id, "unknown"),
        "strategy_hash": strategy_hash,
        "features": features,
    }


def stable_config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def repository_code_sha(root: Path) -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    sha = result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unknown"
    return f"{sha}-dirty" if dirty.returncode == 0 and dirty.stdout.strip() else sha


def _safe_mapping(value: Any, field: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value in (None, ""):
        return {}
    return {"_malformed_field": field, "_raw_type": f"{type(value).__module__}.{type(value).__qualname__}"}


def _bar_end(value: Any) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")) + timedelta(minutes=1)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def _finite_features(features: dict[str, Any]) -> dict[str, float | None]:
    normalized: dict[str, float | None] = {}
    for key, value in sorted(features.items()):
        try:
            number = float(value)
        except (TypeError, ValueError):
            normalized[key] = None
            continue
        normalized[key] = number if number == number and abs(number) != float("inf") else None
    return normalized
