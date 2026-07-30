import gzip
import hashlib
import json
from datetime import date, timedelta

from scripts.weekly_evidence_review import collect_weekly_review
from trading_lab.decision_features import FEATURE_SCHEMA_SHA256, FEATURE_SCHEMA_VERSION
from trading_lab.evidence import CANDIDATE_OUTCOME_SCHEMA_VERSION, dataset_artifact_digest
from trading_lab.model_card import build_model_card, render_model_card_markdown


def _row(session: date, *, win: bool, strategy: str = "opening-range-breakout"):
    return {
        "candidate": {
            "strategy_id": strategy,
            "direction": "long",
            "planned_entry": 100,
            "stop": 99,
            "target": 103,
            "risk_dollars": 10,
            "market_context": {
                "signal_timestamp": f"{session.isoformat()}T13:35:00Z",
                "volume_ratio": 2.0 if win else 0.8,
                "regime": "bull" if win else "neutral",
            },
        },
        "disposition": "policy_approved",
        "outcome": {
            "exit_reason": "target" if win else "stop",
            "fill_status": "filled",
            "net_r": 3.0 if win else -1.0,
            "net_dollars": 30.0 if win else -10.0,
            "data_quality_flags": ["entry_bar_path_unknown"] if win else [],
        },
    }


def test_model_card_contains_plain_english_and_json_sections():
    evaluation = {
        "status": "evaluated",
        "feature_schema_version": "candidate-decision-features-v5",
        "feature_coverage": {"required": {"volume_ratio": {"coverage": 0.95}}, "blockers": []},
        "model_comparison": {
            "always_admit": {"selected": 10, "expectancy_r": 0.1},
            "combined_logistic": {"selected": 5, "expectancy_r": 0.3},
        },
        "selected_model": "combined_logistic",
        "no_fill_model": {"status": "evaluated", "target": "probability_of_no_fill", "samples": 10, "roc_auc": 0.7},
        "blockers": ["human_promotion_not_granted"],
    }
    readiness = {
        "promotion_ready": False,
        "blockers": ["human_promotion_not_granted"],
        "quality": {"warning_flags": {"entry_bar_path_unknown": 10}, "exclusion_flags": {}, "fatal_flags": {}},
        "counts": {"by_strategy": {"opening-range-breakout": 10}},
    }

    card = build_model_card(evaluation=evaluation, readiness=readiness, dataset_manifest={"schema_version": "counterfactual-candidate-v5"})
    markdown = render_model_card_markdown(card)

    assert card["no_order_safety"] == {
        "mode": "paper_proposal_only_no_orders",
        "broker_orders_enabled": False,
        "live_trading_enabled": False,
    }
    assert "Feature coverage" in markdown
    assert "No-order safety" in markdown
    assert "No-fill risk model" in markdown
    assert "human_promotion_not_granted" in markdown
    assert card["recommendations"]


def test_weekly_review_collects_deterministic_artifacts_and_sol_commands(tmp_path):
    evidence_root = tmp_path / "candidate-outcomes-v5"
    evidence_root.mkdir()
    rows = []
    start = date(2026, 6, 1)
    for day in range(30):
        rows.append(_row(start + timedelta(days=day), win=day % 4 != 0))
        rows.append(_row(start + timedelta(days=day), win=day % 5 != 0, strategy="vwap-trend-imbalance"))
    raw = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode("utf-8")
    artifact_path = evidence_root / "2026-06.jsonl.gz"
    artifact_path.write_bytes(gzip.compress(raw, mtime=0))
    artifact = {
        "path": artifact_path.name,
        "period": "2026-06",
        "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        "candidate_count": len(rows),
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "source": "test",
        "code_sha": "a" * 40,
        "schema_version": CANDIDATE_OUTCOME_SCHEMA_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_schema_sha256": FEATURE_SCHEMA_SHA256,
        "dataset_sha256": dataset_artifact_digest([artifact]),
        "coverage": {"candidate_count": len(rows)},
        "artifacts": [artifact],
    }))

    review = collect_weekly_review(
        evidence_root=evidence_root,
        output_dir=tmp_path / "processed",
        dataset_manifest_path=manifest_path,
        minimum_samples=40,
        folds=3,
        minimum_selected=2,
        minimum_sessions=20,
    )

    assert review["ok"] is True
    assert review["mode"] == "offline_weekly_review_no_orders"
    assert review["broker_orders"] == 0
    assert review["evidence_integrity"]["verified"] is True
    assert review["selected_model"]
    assert review["walk_forward_expectancy_r"] is not None
    assert isinstance(review["blockers"], list)
    assert review["artifacts"]["model_card_json"].endswith("model-card.json")
    assert (tmp_path / "processed" / "model-card.md").exists()
    assert ".venv/bin/python -m pytest tests -q" in review["sol_commands"]
    assert ".venv/bin/python -m compileall trading_lab scripts tests" in review["sol_commands"]
