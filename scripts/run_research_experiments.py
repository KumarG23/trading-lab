#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_evidence import load_rows  # noqa: E402
from trading_lab.decision_features import FEATURE_SCHEMA_SHA256, FEATURE_SCHEMA_VERSION  # noqa: E402
from trading_lab.evidence import CANDIDATE_OUTCOME_SCHEMA_VERSION, verify_replay_evidence_manifest  # noqa: E402
from trading_lab.research_experiments import (  # noqa: E402
    cost_aware_ranking_experiment,
    cost_sensitivity_report,
    ensemble_diversity_experiment,
    liquidity_drift_experiment,
    multiple_testing_experiment,
    stocks_in_play_experiment,
)


def validate_research_evidence_integrity(
    integrity: dict[str, Any], *, rows_count: int, manifest: dict[str, Any],
) -> None:
    errors: list[str] = []
    if not bool(integrity.get("verified")):
        errors.append("integrity_not_verified")
    if int(integrity.get("artifacts") or 0) <= 0:
        errors.append("no_artifacts")
    expected_rows = int((manifest.get("coverage") or {}).get("candidate_count") or 0)
    if expected_rows <= 0:
        errors.append("non_positive_candidate_count")
    if rows_count != expected_rows:
        errors.append(f"row_count_mismatch:{rows_count}!={expected_rows}")
    if str(manifest.get("schema_version") or "") != CANDIDATE_OUTCOME_SCHEMA_VERSION:
        errors.append("schema_version_mismatch")
    if str(manifest.get("feature_schema_version") or "") != FEATURE_SCHEMA_VERSION:
        errors.append("feature_schema_version_mismatch")
    if str(manifest.get("feature_schema_sha256") or "") != FEATURE_SCHEMA_SHA256:
        errors.append("feature_schema_sha256_mismatch")
    code_sha = str(manifest.get("code_sha") or "")
    if len(code_sha) != 40 or any(character not in "0123456789abcdef" for character in code_sha.lower()):
        errors.append("code_sha_invalid")
    if not str(manifest.get("source") or "").strip():
        errors.append("source_missing")
    if errors:
        raise ValueError("research evidence rejected: " + ",".join(errors))


def build_research_experiment_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    experiments: dict[str, Any] = {
        "liquidity_drift": liquidity_drift_experiment(rows),
        "ranking": cost_aware_ranking_experiment(rows),
        "stocks_in_play": stocks_in_play_experiment(rows),
        "ensemble": ensemble_diversity_experiment(rows),
    }
    experiments["multiple_testing"] = multiple_testing_experiment(experiments)
    return {
        "ok": True,
        "mode": "offline_research_no_orders",
        "broker_orders": 0,
        "live_trading_enabled": False,
        "promotion_allowed": False,
        "input_rows": len(rows),
        "cost_sensitivity": cost_sensitivity_report(rows),
        "cost_model": {
            "v5_conservative": {
                "entry_slippage_bps": 5.0,
                "exit_slippage_bps": 10.0,
                "fee_per_share_each_side": 0.005,
            },
            "robinhood_small_equity": {
                "commission": 0.0,
                "preserves_v5_observed_slippage": True,
                "removes_v5_per_share_fee": True,
                "scope": "small US equity trades only; excludes ADRs, options, crypto, margin interest, and subscriptions",
            },
            "zero_friction_upper_bound": {
                "commission": 0.0,
                "slippage": 0.0,
                "preserves_gap_aware_fill_path": True,
                "purpose": "diagnostic upper bound, not an execution forecast",
            },
            "double_slippage_stress": {
                "entry_slippage_bps_equivalent": 10.0,
                "exit_slippage_bps_equivalent": 20.0,
                "fee_per_share_each_side": 0.005,
            },
        },
        "experiments": experiments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run five offline Trading Lab research experiments. Places no orders.")
    parser.add_argument("--evidence-root", type=Path, default=ROOT / "data" / "evidence" / "candidate-outcomes-v5")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "processed" / "evidence-manifest-v5.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "research-experiments" / "report.json")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    integrity = verify_replay_evidence_manifest(manifest, args.evidence_root)
    rows = load_rows(args.evidence_root)
    validate_research_evidence_integrity(integrity, rows_count=len(rows), manifest=manifest)
    report = build_research_experiment_report(rows)
    report["evidence_integrity"] = integrity
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({
        "ok": True,
        "output": str(args.output),
        "input_rows": report["input_rows"],
        "registered_trials": report["experiments"]["multiple_testing"]["registered_trials"],
        "broker_orders": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
