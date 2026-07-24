from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from trading_lab.journal_store import JournalStore


_ARTIFACT_HASH_FIELDS = ("period", "sha256", "candidate_count", "bars", "data_quality")


def dataset_artifact_digest(artifacts: list[dict[str, Any]]) -> str:
    """Hash evidence identity and coverage, excluding host-local artifact paths."""
    canonical_artifacts = [
        {key: artifact[key] for key in _ARTIFACT_HASH_FIELDS if key in artifact}
        for artifact in artifacts
    ]
    canonical_artifacts.sort(key=lambda item: str(item.get("period") or ""))
    canonical = json.dumps(canonical_artifacts, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_dataset_manifest(
    *,
    bars: list[dict[str, Any]],
    records: list[dict[str, Any]],
    source: str,
    code_sha: str,
    schema_version: str,
) -> dict[str, Any]:
    ordered_bars = sorted(bars, key=lambda row: (str(row["timestamp"]), str(row["symbol"])))
    ordered_records = sorted(records, key=lambda row: int(row["candidate_event_id"]))
    payload = {
        "source": source,
        "code_sha": code_sha,
        "schema_version": schema_version,
        "bars": ordered_bars,
        "records": ordered_records,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    timestamps = [str(row["timestamp"]) for row in ordered_bars]
    return {
        "manifest_version": "trading-lab-dataset-manifest-v1",
        "source": source,
        "code_sha": code_sha,
        "schema_version": schema_version,
        "dataset_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "coverage": {
            "bar_count": len(ordered_bars),
            "candidate_count": len(ordered_records),
            "start": min(timestamps) if timestamps else None,
            "end": max(timestamps) if timestamps else None,
            "sessions": len({stamp[:10] for stamp in timestamps}),
            "symbols": sorted({str(row["symbol"]).upper() for row in ordered_bars}),
        },
    }


def build_readiness(
    store: JournalStore,
    *,
    dataset_manifest: dict[str, Any] | None,
    model_evaluation: dict[str, Any] | None,
    minimum_candidates: int = 10_000,
    evidence_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    events = {int(row["id"]): row for row in store.list_candidate_events()}
    outcomes = store.list_candidate_outcomes()
    if evidence_rows is None:
        resolved_events = [events[int(row["candidate_event_id"])] for row in outcomes if int(row["candidate_event_id"]) in events]
        outcome_rows = outcomes
        event_count = len(events)
    else:
        resolved_events = evidence_rows
        outcome_rows = [row.get("outcome") or {} for row in evidence_rows]
        event_count = len(evidence_rows)
    dispositions = Counter(str(row.get("disposition") or "unknown") for row in resolved_events)
    strategies = Counter(str((row.get("candidate") or {}).get("strategy_id") or "unknown") for row in resolved_events)
    sessions: Counter[str] = Counter()
    regimes: Counter[str] = Counter()
    for row in resolved_events:
        candidate = row.get("candidate") or {}
        context = candidate.get("market_context") or {}
        signal = str(context.get("signal_timestamp") or row.get("decision_at") or "unknown")
        sessions[signal[:10] if len(signal) >= 10 else "unknown"] += 1
        regimes[str(context.get("regime") or (row.get("features") or {}).get("regime") or "unknown")] += 1
    blockers: list[str] = []
    resolved_count = len(outcome_rows)
    if resolved_count < minimum_candidates:
        blockers.append(f"resolved_candidates_below_{minimum_candidates}:{resolved_count}")
    if dataset_manifest is None:
        blockers.append("dataset_manifest_missing")
    else:
        code_sha = str(dataset_manifest.get("code_sha") or "unknown")
        if len(code_sha) != 40 or any(character not in "0123456789abcdef" for character in code_sha.lower()):
            blockers.append(f"dataset_code_sha_not_clean:{code_sha}")
        dataset_sha = str(dataset_manifest.get("dataset_sha256") or "")
        if len(dataset_sha) != 64 or any(character not in "0123456789abcdef" for character in dataset_sha.lower()):
            blockers.append("dataset_sha256_invalid")
        if not dataset_manifest.get("schema_version"):
            blockers.append("dataset_schema_version_missing")
        if not dataset_manifest.get("source"):
            blockers.append("dataset_source_missing")
    if model_evaluation is None:
        blockers.append("model_evaluation_missing")
    else:
        if model_evaluation.get("status") != "evaluated":
            blockers.append("model_evaluation_not_evaluated")
        if model_evaluation.get("split_policy") != "purged_walk_forward_no_random_split":
            blockers.append("model_evaluation_split_policy_invalid")
        if not bool(model_evaluation.get("all_promotion_gates_pass")):
            blockers.append("model_evaluation_gates_failed")
    quality_failures = sum(1 for row in outcome_rows if row.get("data_quality_flags"))
    if quality_failures:
        blockers.append(f"candidate_outcome_quality_flags:{quality_failures}")
    blockers.append("human_promotion_not_granted")
    return {
        "readiness_version": "trading-lab-readiness-v1",
        "promotion_ready": False,
        "mode": "paper_proposal_only_no_orders",
        "broker_orders_enabled": False,
        "live_trading_enabled": False,
        "counts": {
            "candidate_events": event_count,
            "resolved_candidates": resolved_count,
            "unresolved_candidates": event_count - resolved_count,
            "outcome_quality_failures": quality_failures,
            "by_disposition": dict(sorted(dispositions.items())),
            "by_strategy": dict(sorted(strategies.items())),
            "by_session": dict(sorted(sessions.items())),
            "by_regime": dict(sorted(regimes.items())),
        },
        "dataset_manifest": dataset_manifest,
        "model_evaluation": model_evaluation,
        "blockers": blockers,
    }
