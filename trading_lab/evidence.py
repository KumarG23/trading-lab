from __future__ import annotations

import hashlib
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any

from trading_lab.data_quality import classify_evidence_quality_flags
from trading_lab.decision_features import FEATURE_SCHEMA_SHA256, FEATURE_SCHEMA_VERSION
from trading_lab.journal_store import JournalStore


_ARTIFACT_HASH_FIELDS = ("period", "sha256", "candidate_count", "bars", "data_quality")
CANDIDATE_OUTCOME_SCHEMA_VERSION = "counterfactual-candidate-v5"


def verify_replay_evidence_manifest(manifest: dict[str, Any], evidence_root: str | Path) -> dict[str, Any]:
    root = Path(evidence_root).resolve()
    errors: list[str] = []
    artifacts = list(manifest.get("artifacts") or [])
    listed_paths = [str(artifact.get("path") or "") for artifact in artifacts]
    if len(set(listed_paths)) != len(listed_paths):
        errors.append("duplicate_artifact_paths")
    actual_paths = {path.name for path in root.glob("*.jsonl.gz") if path.is_file()}
    unexpected = sorted(actual_paths - set(listed_paths))
    missing_from_disk = sorted(set(listed_paths) - actual_paths)
    errors.extend(f"artifact_unexpected:{name}" for name in unexpected)
    errors.extend(f"artifact_missing:{name}" for name in missing_from_disk)
    for artifact in artifacts:
        path = (root / str(artifact.get("path") or "")).resolve()
        if root not in path.parents:
            errors.append(f"artifact_path_outside_root:{path.name}")
            continue
        if not path.is_file():
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = str(artifact.get("sha256") or "")
        if actual != expected:
            errors.append(f"artifact_sha256_mismatch:{path.name}")
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                actual_count = sum(1 for line in handle if line.strip())
        except (OSError, UnicodeError):
            errors.append(f"artifact_unreadable:{path.name}")
            continue
        expected_count = int(artifact.get("candidate_count") or 0)
        if actual_count != expected_count:
            errors.append(f"artifact_candidate_count_mismatch:{path.name}:{actual_count}!={expected_count}")
    expected_dataset = str(manifest.get("dataset_sha256") or "")
    actual_dataset = dataset_artifact_digest(artifacts)
    if actual_dataset != expected_dataset:
        errors.append("dataset_artifact_digest_mismatch")
    coverage_count = int((manifest.get("coverage") or {}).get("candidate_count") or 0)
    artifact_count = sum(int(item.get("candidate_count") or 0) for item in artifacts)
    if coverage_count != artifact_count:
        errors.append(f"candidate_count_mismatch:{coverage_count}!={artifact_count}")
    return {"verified": not errors, "errors": errors, "artifacts": len(artifacts)}


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
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_schema_sha256": FEATURE_SCHEMA_SHA256,
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
        schema_version = str(dataset_manifest.get("schema_version") or "")
        if schema_version != CANDIDATE_OUTCOME_SCHEMA_VERSION:
            blockers.append(f"dataset_schema_version_mismatch:{schema_version or 'missing'}")
        feature_version = str(dataset_manifest.get("feature_schema_version") or "")
        if feature_version != FEATURE_SCHEMA_VERSION:
            blockers.append(f"dataset_feature_schema_version_mismatch:{feature_version or 'missing'}")
        feature_sha = str(dataset_manifest.get("feature_schema_sha256") or "")
        if feature_sha != FEATURE_SCHEMA_SHA256:
            blockers.append("dataset_feature_schema_sha256_mismatch")
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
    quality_warning_flags: Counter[str] = Counter()
    quality_exclusion_flags: Counter[str] = Counter()
    quality_fatal_flags: Counter[str] = Counter()
    for row in outcome_rows:
        classified = classify_evidence_quality_flags(row.get("data_quality_flags"))
        quality_warning_flags.update(classified["warning_flags"])
        quality_exclusion_flags.update(classified["exclusion_flags"])
        quality_fatal_flags.update(classified["fatal_flags"])
    quality_warnings = sum(quality_warning_flags.values())
    quality_exclusions = sum(quality_exclusion_flags.values())
    quality_fatal = sum(quality_fatal_flags.values())
    if quality_fatal:
        blockers.append(f"candidate_outcome_fatal_quality_flags:{quality_fatal}")
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
            "outcome_quality_failures": quality_fatal,
            "outcome_quality_warnings": quality_warnings,
            "outcome_quality_exclusions": quality_exclusions,
            "outcome_quality_fatal": quality_fatal,
            "by_disposition": dict(sorted(dispositions.items())),
            "by_strategy": dict(sorted(strategies.items())),
            "by_session": dict(sorted(sessions.items())),
            "by_regime": dict(sorted(regimes.items())),
        },
        "quality": {
            "warning_flags": dict(sorted(quality_warning_flags.items())),
            "exclusion_flags": dict(sorted(quality_exclusion_flags.items())),
            "fatal_flags": dict(sorted(quality_fatal_flags.items())),
        },
        "dataset_manifest": dataset_manifest,
        "model_evaluation": model_evaluation,
        "blockers": blockers,
    }
