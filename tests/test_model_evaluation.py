from trading_lab.model_evaluation import decision_features, purged_walk_forward_evaluate


def test_decision_features_exclude_outcome_and_fill_fields():
    row = {
        "candidate": {
            "planned_entry": 101, "stop": 100, "target": 103, "risk_dollars": 2,
            "market_context": {"relative_volume": 1.5, "signal_timestamp": "2026-07-20T13:35:00Z"},
        },
        "outcome": {"net_r": 99, "actual_exit": 200, "mfe_r": 100},
    }

    features = decision_features(row)

    assert features["planned_entry"] == 101
    assert features["market_context.relative_volume"] == 1.5
    assert all("outcome" not in key and "exit" not in key and "mfe" not in key for key in features)


def test_purged_walk_forward_uses_ordered_sessions_and_reports_calibration_metrics():
    rows = []
    for day in range(1, 31):
        for index in range(2):
            win = (day + index) % 3 != 0
            rows.append({
                "candidate": {
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
    assert all("orb" not in fold["by_strategy"] for fold in result["folds"])
    assert all("unknown" in fold["by_strategy"] for fold in result["folds"])
    assert all("unknown" in fold["by_regime"] for fold in result["folds"])
    assert "always_admit_expectancy_r" in result["aggregate"]
    assert "always_admit_expectancy_dollars" in result["aggregate"]
    assert "model_expectancy_dollars" in result["aggregate"]
    assert set(result["promotion_gates"]) == {
        "selected_candidates", "positive_model_expectancy", "beats_always_admit", "positive_every_fold"
    }
    assert result["split_policy"] == "purged_walk_forward_no_random_split"


def test_model_evaluation_skips_when_sample_gate_is_not_met():
    result = purged_walk_forward_evaluate([], minimum_samples=100)

    assert result["status"] == "skipped"
    assert result["blockers"] == ["samples_below_100:0"]


def test_model_evaluation_fails_closed_on_single_class_training_data():
    rows = []
    for day in range(1, 21):
        rows.append({
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
            "candidate": {"planned_entry": 100, "stop": 99, "target": 102, "risk_dollars": 2,
                          "market_context": {"signal_timestamp": f"2026-06-{day:02d}T13:35:00Z"}},
            "outcome": {"exit_reason": "target" if win else "stop", "net_r": 2.0 if win else -1.0},
        })

    result = purged_walk_forward_evaluate(rows, minimum_samples=20, folds=2)

    assert result["status"] == "skipped"
    assert result["blockers"] == ["single_class_training_fold_1"]


def test_model_evaluation_fails_closed_when_decision_features_are_absent():
    rows = []
    for day in range(1, 21):
        rows.append({
            "candidate": {"market_context": {"signal_timestamp": f"2026-06-{day:02d}T13:35:00Z"}},
            "outcome": {"exit_reason": "target" if day % 2 else "stop", "net_r": 2.0 if day % 2 else -1.0},
        })

    result = purged_walk_forward_evaluate(rows, minimum_samples=10, folds=2)

    assert result["status"] == "skipped"
    assert result["blockers"] == ["decision_features_missing"]
