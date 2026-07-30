import math
from datetime import date, timedelta

from trading_lab.decision_features import (
    FEATURE_SCHEMA_VERSION,
    build_feature_contract,
    decision_features,
    feature_coverage_diagnostics,
)
from trading_lab.model_evaluation import purged_walk_forward_evaluate


def test_v5_decision_features_are_normalized_leakage_safe_and_alias_aware():
    row = {
        "candidate": {
            "ticker": "AAPL",
            "strategy_id": "opening-range-breakout",
            "direction": "long",
            "planned_entry": 101,
            "stop": 100,
            "target": 103,
            "risk_dollars": 2,
            "market_context": {
                "relative_volume": 1.5,
                "signal_timestamp": "2026-07-20T13:35:00Z",
                "opening_range_high": 100,
                "opening_range_low": 98,
                "distance_from_vwap_pct": 0.012,
                "previous_vwap": 99.5,
                "vwap": 100.5,
                "pullback_vwap": 99.75,
                "market_return": -0.003,
                "regime": "bull",
                "volume": 200_000,
                "previous_close": 100,
                "close_5_bars_ago": 98,
            },
        },
        "outcome": {"net_r": 99, "actual_exit": 200, "mfe_r": 100},
    }

    features = decision_features(row)

    assert FEATURE_SCHEMA_VERSION == "candidate-decision-features-v5"
    assert features["strategy.opening-range-breakout"] == 1.0
    assert features["direction.long"] == 1.0
    assert features["minutes_since_open"] == 5.0
    assert features["time_bucket.opening_range"] == 1.0
    assert features["volume_ratio"] == 1.5
    assert features["dollar_volume_log"] > 0
    assert features["stop_distance_pct"] == round(1 / 101, 8)
    assert features["planned_reward_risk"] == 2.0
    assert features["opening_range_width_pct"] == round(2 / 101, 8)
    assert features["opening_range_breakout_distance_pct"] == round(1 / 101, 8)
    assert features["vwap_distance_pct"] == 0.012
    assert features["vwap_slope_pct"] == round(1.0 / 101, 8)
    assert features["pullback_depth_pct"] == round((101 - 99.75) / 101, 8)
    assert features["short_momentum_1bar_pct"] == round(1 / 100, 8)
    assert features["short_momentum_5bar_pct"] == round(3 / 98, 8)
    assert features["regime.bullish"] == 1.0
    assert "planned_entry" not in features
    assert all("outcome" not in key and "exit" not in key and "mfe" not in key for key in features)
    row["candidate"]["market_context"]["signal_timestamp"] = "2026-07-20T09:35:00-04:00"
    assert decision_features(row)["minutes_since_open"] == 5.0
    row["candidate"]["market_context"]["signal_timestamp"] = "2026-01-20T14:35:00Z"
    row["candidate"]["market_context"]["regime"] = "bullish"
    winter = decision_features(row)
    assert winter["minutes_since_open"] == 5.0
    assert winter["regime.bullish"] == 1.0


def test_feature_contract_preserves_missing_values_and_reports_required_coverage():
    rows = [
        {
            "candidate": {
                "strategy_id": "opening-range-breakout",
                "direction": "long",
                "planned_entry": 100,
                "stop": 99,
                "target": 102,
                "market_context": {"signal_timestamp": "2026-07-20T13:31:00Z"},
            },
            "outcome": {"exit_reason": "target", "net_r": 2.0},
        },
        {
            "candidate": {
                "strategy_id": "vwap-trend-imbalance",
                "direction": "long",
                "planned_entry": 50,
                "stop": 49,
                "target": 52,
                "market_context": {
                    "signal_timestamp": "2026-07-21T15:05:00Z",
                    "volume_ratio": 2.0,
                    "distance_from_vwap": 0.5,
                    "vwap": 49.5,
                    "previous_vwap": 49.0,
                },
            },
            "outcome": {"exit_reason": "stop", "net_r": -1.0},
        },
    ]

    contract = build_feature_contract(rows)
    coverage = feature_coverage_diagnostics(rows)

    assert contract["schema_version"] == FEATURE_SCHEMA_VERSION
    assert len(contract["feature_names"]) >= 25
    assert math.isnan(contract["matrix"][0][contract["feature_names"].index("vwap_distance_pct")])
    assert contract["matrix"][1][contract["feature_names"].index("vwap_distance_pct")] == 0.01
    assert coverage["schema_version"] == FEATURE_SCHEMA_VERSION
    assert coverage["samples"] == 2
    assert coverage["required"]["volume_ratio"]["present"] == 1
    assert coverage["required"]["volume_ratio"]["coverage"] == 0.5
    assert "required_feature_coverage_low:volume_ratio:0.5000<0.8000" in coverage["blockers"]


def test_purged_walk_forward_uses_ordered_sessions_and_reports_calibration_metrics():
    rows = []
    for day in range(1, 31):
        for index in range(2):
            win = (day + index) % 3 != 0
            rows.append({
                "disposition": "policy_approved",
                "candidate": {
                    "strategy_id": "opening-range-breakout",
                    "direction": "long",
                    "planned_entry": 100 + day / 10,
                    "stop": 99 + day / 10,
                    "target": 102 + day / 10,
                    "risk_dollars": 2,
                    "market_context": {
                        "signal_timestamp": f"2026-06-{day:02d}T13:35:00Z",
                        "relative_volume": 2.0 if win else 0.5,
                        "regime_score": 1 if win else -1,
                    },
                },
                "outcome": {"exit_reason": "target" if win else "stop", "net_r": 2.0 if win else -1.0},
            })

    result = purged_walk_forward_evaluate(rows, minimum_samples=40, folds=3, embargo_sessions=1)

    assert result["status"] == "evaluated"
    assert len(result["folds"]) == 3
    assert all(fold["train_end"] < fold["test_start"] for fold in result["folds"])
    assert all(fold["embargo_sessions"] == 1 for fold in result["folds"])
    assert all(fold["base_train_end"] < fold["calibration_start"] < fold["test_start"] for fold in result["folds"])
    assert all(0 <= fold["brier"] <= 1 for fold in result["folds"])
    assert all(fold["log_loss"] >= 0 for fold in result["folds"])
    assert all("opening-range-breakout" in fold["by_strategy"] for fold in result["folds"])
    assert all("unknown" in fold["by_regime"] for fold in result["folds"])
    assert "always_admit_expectancy_r" in result["aggregate"]
    assert "always_admit_expectancy_dollars" in result["aggregate"]
    assert "model_expectancy_dollars" in result["aggregate"]
    assert {
        "selected_candidates",
        "minimum_samples",
        "minimum_sessions",
        "minimum_selected",
        "positive_model_expectancy",
        "beats_always_admit",
        "positive_every_fold",
        "holdout_not_tuned",
    }.issubset(result["promotion_gates"])
    assert result["split_policy"] == "purged_walk_forward_no_random_split"


def test_evaluation_compares_baselines_uses_holdout_and_ev_thresholds():
    rows = []
    strategies = ["opening-range-breakout", "vwap-trend-imbalance"]
    start = date(2026, 5, 1)
    for day in range(1, 61):
        session = start + timedelta(days=day - 1)
        for index, strategy in enumerate(strategies):
            strong = (day + index) % 4 != 0
            rows.append({
                "disposition": "policy_approved",
                "candidate": {
                    "strategy_id": strategy,
                    "direction": "long",
                    "planned_entry": 100,
                    "stop": 99,
                    "target": 103 if strong else 101.8,
                    "risk_dollars": 10,
                    "market_context": {
                        "signal_timestamp": f"{session.isoformat()}T{13 + (day % 3):02d}:35:00Z",
                        "volume_ratio": 2.0 if strong else 0.8,
                        "regime": "bull" if day % 2 else "neutral",
                        "distance_from_vwap_pct": 0.01 if strong else -0.002,
                        "previous_vwap": 99.0,
                        "vwap": 100.0 if strong else 99.1,
                    },
                },
                "outcome": {
                    "exit_reason": "target" if strong else "stop",
                    "net_r": 3.0 if strong else -1.0,
                    "net_dollars": 30.0 if strong else -10.0,
                },
            })

    result = purged_walk_forward_evaluate(
        rows,
        minimum_samples=100,
        folds=4,
        embargo_sessions=1,
        final_holdout_fraction=0.2,
        minimum_selected=5,
        minimum_sessions=40,
    )

    assert result["status"] == "evaluated"
    assert result["final_holdout"]["sessions"] == 12
    assert result["final_holdout"]["test_start"] > result["folds"][-1]["test_end"]
    assert result["final_holdout"]["train_end"] < result["final_holdout"]["test_start"]
    assert result["final_holdout"]["embargo_sessions"] == 1
    assert set(result["models"]) == {
        "always_admit",
        "per_strategy_logistic",
        "combined_logistic",
        "gradient_boosting",
        "expected_net_r_regression",
    }
    assert result["selected_model"] in {
        "per_strategy_logistic",
        "combined_logistic",
        "gradient_boosting",
        "expected_net_r_regression",
    }
    selected = result["model_comparison"][result["selected_model"]]
    assert selected["threshold_selection"] == "calibration_expected_net_r_after_costs"
    assert selected["selected"] >= 5
    assert selected["selected_sessions"] >= 20
    assert selected["session_expectancy_r"] > 0
    assert 0 < selected["selection_rate"] <= 1
    assert selected["profit_factor"] is not None
    assert "max_drawdown_r" in selected
    assert selected["selected_thresholds"]
    assert any(abs(item["threshold"] - 0.5) > 0.001 for item in selected["selected_thresholds"])
    assert "stability" in result
    assert "by_time_bucket" in result["folds"][0]["models"][result["selected_model"]]
    assert {
        "positive_holdout_expectancy",
        "holdout_beats_always_admit",
        "minimum_holdout_selected",
        "minimum_selected_sessions",
        "positive_session_expectancy",
        "minimum_holdout_selected_sessions",
    }.issubset(result["promotion_gates"])


def test_threshold_selection_requires_a_representative_calibration_sample():
    from trading_lab.model_evaluation import _select_threshold

    rows = []
    probabilities = []
    for index in range(20):
        rows.append({"outcome": {"net_r": 8.0 if index == 19 else -1.0}})
        probabilities.append(0.99 if index == 19 else 0.4 + index / 100)

    threshold = _select_threshold(rows, __import__("numpy").asarray(probabilities), minimum_selected=5)

    assert threshold["calibration_selected"] >= 5


def test_model_evaluation_skips_when_sample_gate_is_not_met():
    result = purged_walk_forward_evaluate([], minimum_samples=100)

    assert result["status"] == "skipped"
    assert result["blockers"] == ["samples_below_100:0"]


def test_model_evaluation_fails_closed_on_single_class_training_data():
    rows = []
    for day in range(1, 21):
        rows.append({
            "disposition": "policy_approved",
            "candidate": {"planned_entry": 100, "stop": 99, "target": 102, "risk_dollars": 2,
                          "market_context": {"signal_timestamp": f"2026-06-{day:02d}T13:35:00Z"}},
            "outcome": {"exit_reason": "target", "net_r": 2.0},
        })

    result = purged_walk_forward_evaluate(rows, minimum_samples=10, folds=2)

    assert result["status"] == "skipped"
    assert result["blockers"] == ["single_class_labels"]


def test_model_evaluation_fails_closed_when_an_early_fold_is_single_class():
    rows = []
    for day in range(1, 31):
        win = day <= 16
        rows.append({
            "disposition": "policy_approved",
            "candidate": {
                "strategy_id": "opening-range-breakout",
                "direction": "long",
                "planned_entry": 100,
                "stop": 99,
                "target": 102,
                "risk_dollars": 2,
                "market_context": {
                    "signal_timestamp": f"2026-06-{day:02d}T13:35:00Z",
                    "volume_ratio": 1.5,
                },
            },
            "outcome": {"exit_reason": "target" if win else "stop", "net_r": 2.0 if win else -1.0},
        })

    result = purged_walk_forward_evaluate(rows, minimum_samples=20, folds=2)

    assert result["status"] == "skipped"
    assert result["blockers"] == ["single_class_training_fold_1"]


def test_model_evaluation_fails_closed_when_decision_features_are_absent():
    rows = []
    for day in range(1, 21):
        rows.append({
            "disposition": "policy_approved",
            "candidate": {"market_context": {"signal_timestamp": f"2026-06-{day:02d}T13:35:00Z"}},
            "outcome": {"exit_reason": "target" if day % 2 else "stop", "net_r": 2.0 if day % 2 else -1.0},
        })

    result = purged_walk_forward_evaluate(rows, minimum_samples=10, folds=2)

    assert result["status"] == "skipped"
    assert result["blockers"] == ["decision_features_missing"]


def test_evaluation_excludes_ambiguous_and_fatal_rows_but_keeps_warnings():
    rows = []
    for day in range(1, 31):
        flags = []
        if day == 1:
            flags = ["same_bar_stop_target"]
        elif day == 2:
            flags = ["stale_data"]
        elif day == 3:
            flags = ["entry_bar_path_unknown"]
        rows.append({
            "disposition": "policy_approved",
            "candidate": {
                "strategy_id": "opening-range-breakout",
                "direction": "long",
                "planned_entry": 100,
                "stop": 99,
                "target": 102,
                "risk_dollars": 10,
                "market_context": {
                    "signal_timestamp": f"2026-06-{day:02d}T13:35:00Z",
                    "volume_ratio": 1.5,
                },
            },
            "outcome": {
                "exit_reason": "target" if day % 2 else "stop",
                "net_r": 2.0 if day % 2 else -1.0,
                "data_quality_flags": flags,
            },
        })

    result = purged_walk_forward_evaluate(rows, minimum_samples=20, folds=2)

    assert result["status"] == "evaluated"
    assert result["samples"] == 28
    assert result["evidence_quality"]["excluded_rows"] == 2
    assert result["evidence_quality"]["warning_rows"] == 1
    assert result["evidence_quality"]["fatal_rows"] == 1


def test_no_fill_risk_model_is_walk_forward_and_kept_out_of_order_path():
    rows = []
    start = date(2026, 1, 1)
    for day in range(60):
        session = start + timedelta(days=day)
        for index in range(2):
            no_fill = index == 1 and day % 5 == 0
            rows.append({
                "disposition": "policy_approved",
                "candidate": {
                    "strategy_id": "opening-range-breakout",
                    "direction": "long",
                    "planned_entry": 100,
                    "stop": 99,
                    "target": 102,
                    "risk_dollars": 10,
                    "market_context": {
                        "signal_timestamp": f"{session.isoformat()}T14:35:00Z",
                        "volume_ratio": 0.7 if no_fill else 2.0,
                    },
                },
                "outcome": {
                    "fill_status": "no_fill" if no_fill else "filled",
                    "exit_reason": "expired_without_entry" if no_fill else ("target" if day % 2 else "stop"),
                    "net_r": 0.0 if no_fill else (2.0 if day % 2 else -1.0),
                },
            })

    result = purged_walk_forward_evaluate(rows, minimum_samples=100, folds=3, minimum_sessions=40)

    no_fill = result["no_fill_model"]
    assert no_fill["status"] == "evaluated"
    assert no_fill["target"] == "probability_of_no_fill"
    assert no_fill["split_policy"] == "purged_walk_forward_no_random_split"
    assert no_fill["no_fills"] > 0
    assert no_fill["final_holdout"]["status"] == "evaluated"


def test_policy_rejected_and_duplicate_rows_never_enter_admission_training():
    rows = []
    start = date(2026, 1, 1)
    for day in range(30):
        session = start + timedelta(days=day)
        for disposition in ("policy_approved", "policy_rejected", "duplicate"):
            rows.append({
                "disposition": disposition,
                "candidate": {
                    "strategy_id": "opening-range-breakout",
                    "direction": "long",
                    "planned_entry": 100,
                    "stop": 99,
                    "target": 102,
                    "risk_dollars": 10,
                    "market_context": {
                        "signal_timestamp": f"{session.isoformat()}T14:35:00Z",
                        "volume_ratio": 2.0,
                    },
                },
                "outcome": {
                    "fill_status": "filled",
                    "exit_reason": "target" if day % 2 else "stop",
                    "net_r": 2.0 if day % 2 else -1.0,
                },
            })

    result = purged_walk_forward_evaluate(rows, minimum_samples=25, folds=3, minimum_sessions=20)

    assert result["eligibility"] == {
        "input_rows": 90,
        "policy_eligible_rows": 30,
        "excluded_by_disposition": 60,
        "by_disposition": {"duplicate": 30, "policy_approved": 30, "policy_rejected": 30},
    }
    assert result["samples"] == 30
