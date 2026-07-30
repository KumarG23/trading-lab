from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from trading_lab.data_quality import classify_evidence_quality_flags
from trading_lab.decision_features import (
    FEATURE_SCHEMA_VERSION,
    FEATURE_NAMES,
    decision_features,
    feature_coverage_diagnostics,
)


def purged_walk_forward_evaluate(
    rows: list[dict[str, Any]],
    *,
    minimum_samples: int = 1_000,
    folds: int = 5,
    embargo_sessions: int = 1,
    final_holdout_fraction: float = 0.2,
    minimum_selected: int = 25,
    minimum_sessions: int = 20,
    minimum_selected_sessions: int = 30,
) -> dict[str, Any]:
    disposition_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        disposition_counts[str(row.get("disposition") or "unknown")] += 1
    eligible_rows = [row for row in rows if _policy_eligible(row)]
    eligibility = {
        "input_rows": len(rows),
        "policy_eligible_rows": len(eligible_rows),
        "excluded_by_disposition": len(rows) - len(eligible_rows),
        "by_disposition": dict(sorted(disposition_counts.items())),
    }
    session_rows = [row for row in eligible_rows if _session(row)]
    quality_usable_rows: list[dict[str, Any]] = []
    quality = {
        "rows_with_sessions": len(session_rows),
        "labeled_rows": 0,
        "usable_rows": 0,
        "excluded_rows": 0,
        "warning_rows": 0,
        "fatal_rows": 0,
    }
    for row in session_rows:
        classified = classify_evidence_quality_flags((row.get("outcome") or {}).get("data_quality_flags"))
        quality["warning_rows"] += int(classified["has_warning"])
        quality["fatal_rows"] += int(classified["has_fatal"])
        if classified["has_exclusion"] or classified["has_fatal"]:
            quality["excluded_rows"] += 1
            continue
        quality_usable_rows.append(row)
    usable = [row for row in quality_usable_rows if _label(row) is not None]
    quality["labeled_rows"] = len(usable)
    quality["usable_rows"] = len(usable)
    if len(usable) < minimum_samples:
        return {
            "status": "skipped",
            "split_policy": "purged_walk_forward_no_random_split",
            "samples": len(usable),
            "blockers": [f"samples_below_{minimum_samples}:{len(usable)}"],
            "all_promotion_gates_pass": False,
        }
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        by_session[_session(row)].append(row)
    if len({_label(row) for row in usable}) < 2:
        return {
            "status": "skipped", "split_policy": "purged_walk_forward_no_random_split",
            "samples": len(usable), "blockers": ["single_class_labels"],
            "all_promotion_gates_pass": False,
        }
    coverage = feature_coverage_diagnostics(usable)
    coverage_blockers = list(coverage["blockers"])
    if _effectively_missing_decision_features(coverage):
        return {
            "status": "skipped", "split_policy": "purged_walk_forward_no_random_split",
            "samples": len(usable), "blockers": ["decision_features_missing"],
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_coverage": coverage,
            "all_promotion_gates_pass": False,
        }
    if coverage_blockers:
        return {
            "status": "skipped", "split_policy": "purged_walk_forward_no_random_split",
            "samples": len(usable), "blockers": coverage_blockers,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_coverage": coverage,
            "all_promotion_gates_pass": False,
        }
    sessions = sorted(by_session)
    if len(sessions) < minimum_sessions:
        return {
            "status": "skipped", "split_policy": "purged_walk_forward_no_random_split",
            "samples": len(usable), "sessions": len(sessions),
            "blockers": [f"sessions_below_{minimum_sessions}:{len(sessions)}"],
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_coverage": coverage,
            "all_promotion_gates_pass": False,
        }
    holdout_count = max(1, int(round(len(sessions) * final_holdout_fraction))) if final_holdout_fraction > 0 else 0
    if holdout_count >= len(sessions) - 5:
        holdout_count = max(1, len(sessions) // 5)
    walk_sessions = sessions[:-holdout_count] if holdout_count else sessions
    holdout_sessions = sessions[-holdout_count:] if holdout_count else []
    initial_train = max(5, len(walk_sessions) // 2)
    remaining = len(walk_sessions) - initial_train
    if remaining < folds:
        return {
            "status": "skipped", "split_policy": "purged_walk_forward_no_random_split",
            "samples": len(usable), "blockers": [f"sessions_below_fold_requirement:{len(sessions)}"],
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_coverage": coverage,
            "all_promotion_gates_pass": False,
        }
    fold_results = []
    fold_session_splits: list[tuple[list[str], list[str]]] = []
    edges = np.linspace(initial_train, len(walk_sessions), folds + 1, dtype=int)
    for fold_index in range(folds):
        test_start_index = int(edges[fold_index])
        test_end_index = int(edges[fold_index + 1])
        train_end_index = max(1, test_start_index - embargo_sessions)
        train_sessions = walk_sessions[:train_end_index]
        test_sessions = walk_sessions[test_start_index:test_end_index]
        fold_session_splits.append((train_sessions, test_sessions))
        train_rows = [row for session in train_sessions for row in by_session[session]]
        test_rows = [row for session in test_sessions for row in by_session[session]]
        calibration_session_index = max(1, int(len(train_sessions) * 0.8))
        fit_sessions = set(train_sessions[:calibration_session_index])
        fit_rows = [row for row in train_rows if _session(row) in fit_sessions]
        if len({_label(row) for row in fit_rows}) < 2:
            return {
                "status": "skipped", "split_policy": "purged_walk_forward_no_random_split",
                "samples": len(usable), "blockers": [f"single_class_training_fold_{fold_index + 1}"],
                "all_promotion_gates_pass": False,
            }
        fold_results.append(_evaluate_fold(
            fold_index, train_rows, test_rows, train_sessions, test_sessions, embargo_sessions,
        ))
    aggregate = _aggregate(fold_results, model_name="combined_logistic")
    model_comparison = {
        name: _aggregate(fold_results, model_name=name)
        for name in (
            "always_admit",
            "per_strategy_logistic",
            "combined_logistic",
            "gradient_boosting",
            "expected_net_r_regression",
        )
    }
    selected_model = _select_model(model_comparison, minimum_selected=minimum_selected)
    selected_aggregate = model_comparison[selected_model]
    holdout_train_sessions = (
        walk_sessions[:-embargo_sessions]
        if embargo_sessions and len(walk_sessions) > embargo_sessions
        else walk_sessions
    )
    holdout = _evaluate_fold(
        folds,
        [row for session in holdout_train_sessions for row in by_session[session]],
        [row for session in holdout_sessions for row in by_session[session]],
        holdout_train_sessions,
        holdout_sessions,
        embargo_sessions,
    ) if holdout_sessions else {"sessions": 0, "models": {}}
    holdout_selected = (holdout.get("models") or {}).get(selected_model) or _empty_metrics()
    holdout_baseline = (holdout.get("models") or {}).get("always_admit") or _empty_metrics()
    minimum_holdout_selected = max(10, minimum_selected // max(1, folds))
    no_fill_model = _no_fill_walk_forward_evaluate(
        quality_usable_rows,
        fold_session_splits=fold_session_splits,
        walk_sessions=holdout_train_sessions,
        holdout_sessions=holdout_sessions,
    )
    promotion_gates = {
        "selected_candidates": selected_aggregate["selected"] > 0,
        "minimum_samples": len(usable) >= minimum_samples,
        "minimum_sessions": len(sessions) >= minimum_sessions,
        "minimum_selected": selected_aggregate["selected"] >= minimum_selected,
        "minimum_selected_sessions": selected_aggregate["selected_sessions"] >= minimum_selected_sessions,
        "positive_session_expectancy": selected_aggregate["session_expectancy_r"] > 0,
        "positive_model_expectancy": selected_aggregate["expectancy_r"] > 0,
        "beats_always_admit": selected_aggregate["expectancy_r"] > model_comparison["always_admit"]["expectancy_r"],
        "positive_every_fold": all(fold["models"][selected_model]["expectancy_r"] > 0 for fold in fold_results),
        "holdout_not_tuned": bool(holdout_sessions),
        "positive_holdout_expectancy": holdout_selected["expectancy_r"] > 0,
        "holdout_beats_always_admit": holdout_selected["expectancy_r"] > holdout_baseline["expectancy_r"],
        "minimum_holdout_selected": holdout_selected["selected"] >= minimum_holdout_selected,
        "minimum_holdout_selected_sessions": int(holdout_selected.get("selected_sessions") or 0) >= min(10, minimum_selected_sessions),
        "positive_holdout_session_expectancy": float(holdout_selected.get("session_expectancy_r") or 0.0) > 0,
        "no_fill_model_evaluated": no_fill_model.get("status") == "evaluated",
        "no_fill_model_beats_base_rate": (
            no_fill_model.get("brier") is not None
            and no_fill_model.get("baseline_brier") is not None
            and float(no_fill_model["brier"]) < float(no_fill_model["baseline_brier"])
        ),
        "no_fill_holdout_evaluated": (no_fill_model.get("final_holdout") or {}).get("status") == "evaluated",
        "no_fill_holdout_beats_base_rate": (
            (no_fill_model.get("final_holdout") or {}).get("brier") is not None
            and (no_fill_model.get("final_holdout") or {}).get("baseline_brier") is not None
            and float(no_fill_model["final_holdout"]["brier"])
            < float(no_fill_model["final_holdout"]["baseline_brier"])
        ),
        "walk_forward_profit_factor_above_1_2": (selected_aggregate.get("profit_factor") or 0.0) > 1.2,
        "holdout_profit_factor_above_1_2": (holdout_selected.get("profit_factor") or 0.0) > 1.2,
    }
    return {
        "status": "evaluated",
        "model": selected_model,
        "models": [
            "always_admit",
            "per_strategy_logistic",
            "combined_logistic",
            "gradient_boosting",
            "expected_net_r_regression",
        ],
        "split_policy": "purged_walk_forward_no_random_split",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_coverage": coverage,
        "evidence_quality": quality,
        "eligibility": eligibility,
        "no_fill_model": no_fill_model,
        "samples": len(usable),
        "sessions": len(sessions),
        "walk_forward_sessions": len(walk_sessions),
        "folds": fold_results,
        "final_holdout": _holdout_summary(holdout, selected_model),
        "selected_model": selected_model,
        "model_comparison": model_comparison,
        "aggregate": aggregate,
        "stability": _stability(fold_results, selected_model),
        "promotion_gates": promotion_gates,
        "all_promotion_gates_pass": all(promotion_gates.values()),
        "blockers": [name for name, passed in promotion_gates.items() if not passed],
    }


def _evaluate_fold(index, train_rows, test_rows, train_sessions, test_sessions, embargo_sessions):
    if not test_rows:
        empty = _empty_metrics()
        return {
            "fold": index + 1,
            "train_start": train_sessions[0] if train_sessions else None,
            "train_end": train_sessions[-1] if train_sessions else None,
            "test_start": test_sessions[0] if test_sessions else None,
            "test_end": test_sessions[-1] if test_sessions else None,
            "sessions": len(test_sessions),
            "embargo_sessions": embargo_sessions,
            "train_samples": len(train_rows),
            "test_samples": 0,
            "models": {
                "always_admit": empty,
                "per_strategy_logistic": empty,
                "combined_logistic": empty,
                "gradient_boosting": empty,
                "expected_net_r_regression": empty,
            },
            **empty,
        }
    calibration_session_index = max(1, int(len(train_sessions) * 0.8))
    fit_sessions = set(train_sessions[:calibration_session_index])
    fit_rows = [row for row in train_rows if _session(row) in fit_sessions]
    calibration_rows = [row for row in train_rows if _session(row) not in fit_sessions]
    feature_names = list(FEATURE_NAMES)
    x_fit = _matrix(fit_rows, feature_names)
    y_fit = np.asarray([_label(row) for row in fit_rows], dtype=int)
    x_test = _matrix(test_rows, feature_names)
    y_test = np.asarray([_label(row) for row in test_rows], dtype=int)
    net_r = np.asarray([float((row.get("outcome") or {}).get("net_r") or 0.0) for row in test_rows])
    net_dollars = np.asarray([_net_dollars(row) for row in test_rows])
    model_metrics = {
        "always_admit": _selection_metrics(
            test_rows, np.ones(len(test_rows), dtype=bool), net_r, net_dollars, y_test, None, None
        ),
        "combined_logistic": _probability_model_metrics(
            kind="combined_logistic",
            fit_rows=fit_rows,
            calibration_rows=calibration_rows,
            test_rows=test_rows,
            feature_names=feature_names,
            y_test=y_test,
            net_r=net_r,
            net_dollars=net_dollars,
        ),
        "gradient_boosting": _probability_model_metrics(
            kind="gradient_boosting",
            fit_rows=fit_rows,
            calibration_rows=calibration_rows,
            test_rows=test_rows,
            feature_names=feature_names,
            y_test=y_test,
            net_r=net_r,
            net_dollars=net_dollars,
        ),
        "expected_net_r_regression": _regression_model_metrics(
            fit_rows=fit_rows,
            calibration_rows=calibration_rows,
            test_rows=test_rows,
            feature_names=feature_names,
            y_test=y_test,
            net_r=net_r,
            net_dollars=net_dollars,
        ),
        "per_strategy_logistic": _per_strategy_model_metrics(
            fit_rows=fit_rows,
            calibration_rows=calibration_rows,
            test_rows=test_rows,
            feature_names=feature_names,
            y_test=y_test,
            net_r=net_r,
            net_dollars=net_dollars,
        ),
    }
    selected = model_metrics["combined_logistic"]["_selected_mask"]
    combined = {
        key: value
        for key, value in model_metrics["combined_logistic"].items()
        if not key.startswith("_")
    }
    public_models = {
        name: {key: value for key, value in metrics.items() if not key.startswith("_")}
        for name, metrics in model_metrics.items()
    }
    return {
        "fold": index + 1,
        "train_start": train_sessions[0],
        "train_end": train_sessions[-1],
        "test_start": test_sessions[0],
        "test_end": test_sessions[-1],
        "sessions": len(test_sessions),
        "embargo_sessions": embargo_sessions,
        "train_samples": len(train_rows),
        "base_train_end": train_sessions[calibration_session_index - 1],
        "calibration_start": train_sessions[calibration_session_index] if calibration_session_index < len(train_sessions) else None,
        "test_samples": len(test_rows),
        "models": public_models,
        "brier": combined["brier"],
        "log_loss": combined["log_loss"],
        "roc_auc": combined["roc_auc"],
        "always_admit_expectancy_r": model_metrics["always_admit"]["expectancy_r"],
        "model_expectancy_r": combined["expectancy_r"],
        "always_admit_expectancy_dollars": model_metrics["always_admit"]["expectancy_dollars"],
        "model_expectancy_dollars": combined["expectancy_dollars"],
        "selected": combined["selected"],
        "by_strategy": _slice_metrics(test_rows, selected, net_r, net_dollars, "strategy"),
        "by_regime": _slice_metrics(test_rows, selected, net_r, net_dollars, "regime"),
    }


def _no_fill_walk_forward_evaluate(
    rows: list[dict[str, Any]],
    *,
    fold_session_splits: list[tuple[list[str], list[str]]],
    walk_sessions: list[str],
    holdout_sessions: list[str],
) -> dict[str, Any]:
    eligible = [row for row in rows if _no_fill_label(row) is not None]
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        by_session[_session(row)].append(row)

    def evaluate_split(train_sessions: list[str], test_sessions: list[str]) -> dict[str, Any]:
        train = [row for session in train_sessions for row in by_session.get(session, [])]
        test = [row for session in test_sessions for row in by_session.get(session, [])]
        y_train = np.asarray([_no_fill_label(row) for row in train], dtype=int)
        y_test = np.asarray([_no_fill_label(row) for row in test], dtype=int)
        if not train or not test or len(set(y_train)) < 2:
            return {
                "status": "skipped",
                "samples": len(test),
                "no_fills": int(y_test.sum()) if len(y_test) else 0,
                "warning": "no_fill_training_requires_both_classes",
            }
        model = Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=1_000, random_state=17)),
        ])
        try:
            model.fit(_matrix(train, list(FEATURE_NAMES)), y_train)
            probabilities = np.clip(model.predict_proba(_matrix(test, list(FEATURE_NAMES)))[:, 1], 1e-6, 1 - 1e-6)
        except (ValueError, FloatingPointError) as exc:
            return {
                "status": "skipped",
                "samples": len(test),
                "no_fills": int(y_test.sum()),
                "warning": f"no_fill_fit_failed:{type(exc).__name__}",
            }
        return {
            "status": "evaluated",
            "samples": len(test),
            "no_fills": int(y_test.sum()),
            "observed_no_fill_rate": round(float(y_test.mean()), 6),
            "predicted_no_fill_rate": round(float(probabilities.mean()), 6),
            "brier": round(float(brier_score_loss(y_test, probabilities)), 6),
            "baseline_brier": round(float(brier_score_loss(y_test, np.full(len(y_test), float(y_train.mean())))), 6),
            "log_loss": round(float(log_loss(y_test, probabilities, labels=[0, 1])), 6),
            "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 6) if len(set(y_test)) == 2 else None,
        }

    fold_metrics = [evaluate_split(train, test) for train, test in fold_session_splits]
    evaluated = [item for item in fold_metrics if item["status"] == "evaluated"]
    total = sum(int(item["samples"]) for item in evaluated)

    def weighted(name: str) -> float | None:
        values = [(item.get(name), int(item["samples"])) for item in evaluated if item.get(name) is not None]
        return sum(float(value) * weight for value, weight in values) / sum(weight for _value, weight in values) if values else None

    return {
        "status": "evaluated" if evaluated else "skipped",
        "target": "probability_of_no_fill",
        "model": "logistic_base_rate_preserving",
        "split_policy": "purged_walk_forward_no_random_split",
        "samples": total,
        "no_fills": sum(int(item.get("no_fills") or 0) for item in evaluated),
        "brier": round(weighted("brier"), 6) if weighted("brier") is not None else None,
        "baseline_brier": round(weighted("baseline_brier"), 6) if weighted("baseline_brier") is not None else None,
        "log_loss": round(weighted("log_loss"), 6) if weighted("log_loss") is not None else None,
        "roc_auc": round(weighted("roc_auc"), 6) if weighted("roc_auc") is not None else None,
        "folds": fold_metrics,
        "final_holdout": evaluate_split(walk_sessions, holdout_sessions) if holdout_sessions else {"status": "skipped"},
    }


def _matrix(rows, names):
    return np.asarray([[decision_features(row).get(name, np.nan) for name in names] for row in rows], dtype=float)


def _effectively_missing_decision_features(coverage: dict[str, Any]) -> bool:
    required = coverage.get("required") or {}
    core = ("stop_distance_pct", "planned_reward_risk")
    return all(int((required.get(name) or {}).get("present") or 0) == 0 for name in core)


def _session(row):
    signal = str(((row.get("candidate") or {}).get("market_context") or {}).get("signal_timestamp") or "")
    return signal[:10] if len(signal) >= 10 else ""


def _policy_eligible(row: dict[str, Any]) -> bool:
    return str(row.get("disposition") or "") in {
        "policy_approved",
        "admitted_portfolio",
        "admitted_research",
        "slot_blocked",
    }


def _label(row):
    outcome = row.get("outcome") or {}
    if str(outcome.get("fill_status") or "") == "no_fill":
        return 0
    reason = outcome.get("exit_reason")
    if reason == "target":
        return 1
    if reason == "stop":
        return 0
    if outcome.get("fill_status") == "filled":
        return int(float(outcome.get("net_r") or 0.0) > 0)
    return None


def _no_fill_label(row: dict[str, Any]) -> int | None:
    fill_status = str((row.get("outcome") or {}).get("fill_status") or "")
    if fill_status == "filled":
        return 0
    if fill_status == "no_fill":
        return 1
    return None


def _net_dollars(row):
    outcome = row.get("outcome") or {}
    if outcome.get("net_dollars") is not None:
        return float(outcome["net_dollars"])
    return float(outcome.get("net_r") or 0.0) * float((row.get("candidate") or {}).get("risk_dollars") or 0.0)


def _logit(values):
    clipped = np.clip(values, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped))


def _make_model(kind: str) -> Pipeline:
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    if kind == "gradient_boosting":
        return Pipeline([
            ("imputer", imputer),
            ("model", GradientBoostingClassifier(random_state=17, n_estimators=40, max_depth=2)),
        ])
    return Pipeline([
        ("imputer", imputer),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=1_000, random_state=17)),
    ])


def _probability_model_metrics(
    *,
    kind: str,
    fit_rows: list[dict[str, Any]],
    calibration_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    feature_names: list[str],
    y_test: np.ndarray,
    net_r: np.ndarray,
    net_dollars: np.ndarray,
) -> dict[str, Any]:
    y_fit = np.asarray([_label(row) for row in fit_rows], dtype=int)
    if len(set(y_fit)) < 2:
        return _fit_closed_metrics(test_rows, net_r, net_dollars, y_test, f"{kind}_single_class_fit")
    try:
        model = _make_model(kind)
        model.fit(_matrix(fit_rows, feature_names), y_fit)
        probabilities = model.predict_proba(_matrix(test_rows, feature_names))[:, 1]
        cal_probabilities = model.predict_proba(_matrix(calibration_rows, feature_names))[:, 1] if calibration_rows else np.asarray([])
    except (ValueError, FloatingPointError) as exc:
        return _fit_closed_metrics(test_rows, net_r, net_dollars, y_test, f"{kind}_fit_failed:{type(exc).__name__}")
    threshold_info = _select_threshold(calibration_rows, cal_probabilities)
    selected = probabilities >= threshold_info["threshold"]
    return _selection_metrics(
        test_rows, selected, net_r, net_dollars, y_test, probabilities, threshold_info
    )


def _regression_model_metrics(
    *,
    fit_rows: list[dict[str, Any]],
    calibration_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    feature_names: list[str],
    y_test: np.ndarray,
    net_r: np.ndarray,
    net_dollars: np.ndarray,
) -> dict[str, Any]:
    target = np.asarray([float((row.get("outcome") or {}).get("net_r") or 0.0) for row in fit_rows])
    try:
        model = Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("model", GradientBoostingRegressor(random_state=17, n_estimators=40, max_depth=2)),
        ])
        model.fit(_matrix(fit_rows, feature_names), target)
        predictions = model.predict(_matrix(test_rows, feature_names))
        calibration_predictions = (
            model.predict(_matrix(calibration_rows, feature_names))
            if calibration_rows else np.asarray([])
        )
    except (ValueError, FloatingPointError) as exc:
        return _fit_closed_metrics(
            test_rows, net_r, net_dollars, y_test,
            f"expected_net_r_regression_fit_failed:{type(exc).__name__}",
        )
    threshold_info = _select_threshold(calibration_rows, calibration_predictions)
    selected = predictions >= threshold_info["threshold"]
    metrics = _selection_metrics(
        test_rows, selected, net_r, net_dollars, y_test, None, threshold_info
    )
    errors = predictions - net_r
    metrics.update({
        "prediction_target": "net_r_after_costs",
        "prediction_rmse": round(float(np.sqrt(np.mean(errors ** 2))), 6),
        "prediction_mae": round(float(np.mean(np.abs(errors))), 6),
    })
    return metrics


def _per_strategy_model_metrics(
    *,
    fit_rows: list[dict[str, Any]],
    calibration_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    feature_names: list[str],
    y_test: np.ndarray,
    net_r: np.ndarray,
    net_dollars: np.ndarray,
) -> dict[str, Any]:
    probabilities = np.zeros(len(test_rows), dtype=float)
    selected = np.zeros(len(test_rows), dtype=bool)
    thresholds = []
    warnings = []
    for strategy in sorted({_strategy(row) for row in test_rows}):
        fit_slice = [row for row in fit_rows if _strategy(row) == strategy]
        cal_slice = [row for row in calibration_rows if _strategy(row) == strategy]
        test_indexes = [index for index, row in enumerate(test_rows) if _strategy(row) == strategy]
        y_fit = np.asarray([_label(row) for row in fit_slice], dtype=int)
        if len(fit_slice) < 4 or len(set(y_fit)) < 2:
            warnings.append(f"per_strategy_fit_closed:{strategy}")
            continue
        try:
            model = _make_model("combined_logistic")
            model.fit(_matrix(fit_slice, feature_names), y_fit)
            strategy_probabilities = model.predict_proba(_matrix([test_rows[index] for index in test_indexes], feature_names))[:, 1]
            cal_probabilities = model.predict_proba(_matrix(cal_slice, feature_names))[:, 1] if cal_slice else np.asarray([])
        except (ValueError, FloatingPointError) as exc:
            warnings.append(f"per_strategy_fit_failed:{strategy}:{type(exc).__name__}")
            continue
        threshold_info = _select_threshold(cal_slice, cal_probabilities)
        thresholds.append({"strategy": strategy, **threshold_info})
        for offset, row_index in enumerate(test_indexes):
            probabilities[row_index] = strategy_probabilities[offset]
            selected[row_index] = strategy_probabilities[offset] >= threshold_info["threshold"]
    metrics = _selection_metrics(test_rows, selected, net_r, net_dollars, y_test, probabilities, None)
    metrics["selected_thresholds"] = thresholds
    metrics["threshold_selection"] = "calibration_expected_net_r_after_costs"
    metrics["warnings"] = warnings
    return metrics


def _select_threshold(
    calibration_rows: list[dict[str, Any]],
    probabilities: np.ndarray,
    *,
    minimum_selected: int | None = None,
) -> dict[str, Any]:
    if not calibration_rows or len(probabilities) == 0:
        return {
            "threshold": 1.1,
            "calibration_selected": 0,
            "calibration_expectancy_r": 0.0,
            "calibration_conservative_score": 0.0,
        }
    cal_net_r = np.asarray([float((row.get("outcome") or {}).get("net_r") or 0.0) for row in calibration_rows])
    if minimum_selected is None:
        minimum_selected = max(3, min(25, int(np.ceil(len(calibration_rows) * 0.05))))
    minimum_selected = min(max(1, minimum_selected), len(calibration_rows))
    candidates = sorted({float(value) for value in probabilities})
    candidates.extend([0.0, 1.0])
    best = {
        "threshold": 1.1,
        "calibration_selected": 0,
        "calibration_expectancy_r": -float("inf"),
        "calibration_conservative_score": -float("inf"),
    }
    for threshold in candidates:
        selected = probabilities >= threshold
        selected_count = int(selected.sum())
        if selected_count < minimum_selected:
            continue
        selected_returns = cal_net_r[selected]
        expectancy = float(selected_returns.mean())
        standard_error = float(selected_returns.std(ddof=1) / np.sqrt(selected_count)) if selected_count > 1 else float("inf")
        conservative_score = expectancy - standard_error
        if (conservative_score, selected_count) > (best["calibration_conservative_score"], best["calibration_selected"]):
            best = {
                "threshold": round(float(threshold), 8),
                "calibration_selected": selected_count,
                "calibration_expectancy_r": round(expectancy, 6),
                "calibration_conservative_score": round(conservative_score, 6),
            }
    if best["calibration_expectancy_r"] == -float("inf"):
        return {
            "threshold": 1.1,
            "calibration_selected": 0,
            "calibration_expectancy_r": 0.0,
            "calibration_conservative_score": 0.0,
        }
    if best["calibration_expectancy_r"] <= 0 or best["calibration_conservative_score"] <= 0:
        return {
            "threshold": float(np.max(probabilities)) + 1e-9,
            "calibration_selected": 0,
            "calibration_expectancy_r": best["calibration_expectancy_r"],
            "calibration_conservative_score": best["calibration_conservative_score"],
        }
    return best


def _selection_metrics(
    rows: list[dict[str, Any]],
    selected: np.ndarray,
    net_r: np.ndarray,
    net_dollars: np.ndarray,
    y_true: np.ndarray,
    probabilities: np.ndarray | None,
    threshold_info: dict[str, Any] | None,
) -> dict[str, Any]:
    selected_count = int(selected.sum())
    selected_returns = net_r[selected]
    equity = np.cumsum(selected_returns) if selected_count else np.asarray([], dtype=float)
    session_totals: dict[str, float] = defaultdict(float)
    session_counts: dict[str, int] = defaultdict(int)
    for index, row in enumerate(rows):
        if selected[index]:
            session_totals[_session(row)] += float(net_r[index])
            session_counts[_session(row)] += 1
    selected_sessions = len(session_totals)
    positive_sessions = sum(value > 0 for value in session_totals.values())
    metrics = {
        "threshold_selection": (
            "always_admit"
            if probabilities is None and threshold_info is None
            else "calibration_expected_net_r_after_costs"
        ),
        "selected_thresholds": [] if threshold_info is None else [threshold_info],
        "test_samples": len(rows),
        "selected": selected_count,
        "selection_rate": round(selected_count / len(rows), 6) if rows else 0.0,
        "selected_sessions": selected_sessions,
        "session_total_r": round(sum(session_totals.values()), 6),
        "session_expectancy_r": round(sum(session_totals.values()) / selected_sessions, 6) if selected_sessions else 0.0,
        "positive_session_rate": round(positive_sessions / selected_sessions, 6) if selected_sessions else 0.0,
        "positive_session_count": positive_sessions,
        "max_candidates_per_session": max(session_counts.values(), default=0),
        "expectancy_r": round(float(selected_returns.mean()), 6) if selected.any() else 0.0,
        "expectancy_dollars": round(float(net_dollars[selected].mean()), 6) if selected.any() else 0.0,
        "profit_factor": _profit_factor(selected_returns) if selected.any() else None,
        "gross_profit_r": round(float(selected_returns[selected_returns > 0].sum()), 6) if selected.any() else 0.0,
        "gross_loss_r": round(abs(float(selected_returns[selected_returns < 0].sum())), 6) if selected.any() else 0.0,
        "total_r": round(float(selected_returns.sum()), 6) if selected.any() else 0.0,
        "max_equity_r": round(float(max(0.0, equity.max())), 6) if selected.any() else 0.0,
        "min_equity_r": round(float(min(0.0, equity.min())), 6) if selected.any() else 0.0,
        "max_drawdown_r": _max_drawdown(selected_returns) if selected.any() else 0.0,
        "exposure_rate": round(selected_count / len(rows), 6) if rows else 0.0,
        "by_strategy": _slice_metrics(rows, selected, net_r, net_dollars, "strategy"),
        "by_regime": _slice_metrics(rows, selected, net_r, net_dollars, "regime"),
        "by_time_bucket": _slice_metrics(rows, selected, net_r, net_dollars, "time_bucket"),
        "_selected_mask": selected,
        "_selected_net_r": [float(value) for value in net_r[selected]],
    }
    if probabilities is not None and len(probabilities) == len(y_true):
        clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
        metrics.update({
            "brier": round(float(brier_score_loss(y_true, clipped)), 6),
            "log_loss": round(float(log_loss(y_true, clipped, labels=[0, 1])), 6),
            "roc_auc": round(float(roc_auc_score(y_true, clipped)), 6) if len(set(y_true)) == 2 else None,
        })
    else:
        metrics.update({"brier": None, "log_loss": None, "roc_auc": None})
    return metrics


def _fit_closed_metrics(rows, net_r, net_dollars, y_true, warning):
    selected = np.zeros(len(rows), dtype=bool)
    metrics = _selection_metrics(rows, selected, net_r, net_dollars, y_true, np.zeros(len(rows)), None)
    metrics["warnings"] = [warning]
    return metrics


def _empty_metrics() -> dict[str, Any]:
    return {
        "threshold_selection": "none",
        "selected_thresholds": [],
        "test_samples": 0,
        "selected": 0,
        "selection_rate": 0.0,
        "selected_sessions": 0,
        "session_total_r": 0.0,
        "session_expectancy_r": 0.0,
        "positive_session_rate": 0.0,
        "positive_session_count": 0,
        "max_candidates_per_session": 0,
        "expectancy_r": 0.0,
        "expectancy_dollars": 0.0,
        "profit_factor": None,
        "gross_profit_r": 0.0,
        "gross_loss_r": 0.0,
        "total_r": 0.0,
        "max_equity_r": 0.0,
        "min_equity_r": 0.0,
        "max_drawdown_r": 0.0,
        "exposure_rate": 0.0,
        "brier": None,
        "log_loss": None,
        "roc_auc": None,
        "by_strategy": {},
        "by_regime": {},
        "by_time_bucket": {},
        "_selected_mask": np.asarray([], dtype=bool),
        "_selected_net_r": [],
    }


def _slice_metrics(rows, selected, net_r, net_dollars, kind):
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        if kind == "strategy":
            key = _strategy(row)
        elif kind == "time_bucket":
            key = _bucket(row)
        else:
            key = _regime(row)
        groups[key].append(index)
    result = {}
    for key, indexes in sorted(groups.items()):
        values = net_r[indexes]
        dollars = net_dollars[indexes]
        chosen = np.asarray([selected[index] for index in indexes], dtype=bool)
        result[key] = {
            "samples": len(indexes),
            "selected": int(chosen.sum()),
            "always_admit_expectancy_r": round(float(values.mean()), 6),
            "model_expectancy_r": round(float(values[chosen].mean()), 6) if chosen.any() else 0.0,
            "expectancy_r": round(float(values[chosen].mean()), 6) if chosen.any() else 0.0,
            "always_admit_expectancy_dollars": round(float(dollars.mean()), 6),
            "model_expectancy_dollars": round(float(dollars[chosen].mean()), 6) if chosen.any() else 0.0,
            "expectancy_dollars": round(float(dollars[chosen].mean()), 6) if chosen.any() else 0.0,
        }
    return result


def _aggregate(folds, *, model_name: str):
    total = sum((fold["models"][model_name])["test_samples"] for fold in folds)
    selected = sum((fold["models"][model_name])["selected"] for fold in folds)

    def weighted(key):
        values = [
            ((fold["models"][model_name]).get(key), (fold["models"][model_name])["test_samples"])
            for fold in folds
        ]
        numeric = [(value, weight) for value, weight in values if value is not None]
        return sum(value * weight for value, weight in numeric) / sum(weight for _value, weight in numeric) if numeric else None

    model_expectancy = (
        sum(fold["models"][model_name]["expectancy_r"] * fold["models"][model_name]["selected"] for fold in folds) / selected
        if selected else 0.0
    )
    model_expectancy_dollars = (
        sum(fold["models"][model_name]["expectancy_dollars"] * fold["models"][model_name]["selected"] for fold in folds) / selected
        if selected else 0.0
    )
    thresholds = []
    for fold in folds:
        for item in fold["models"][model_name].get("selected_thresholds") or []:
            thresholds.append({"fold": fold["fold"], **item})
    selected_sessions = sum(int(fold["models"][model_name].get("selected_sessions") or 0) for fold in folds)
    session_total_r = sum(float(fold["models"][model_name].get("session_total_r") or 0.0) for fold in folds)
    positive_sessions = sum(int(fold["models"][model_name].get("positive_session_count") or 0) for fold in folds)
    return {
        "test_samples": total,
        "selected": selected,
        "selection_rate": round(selected / total, 6) if total else 0.0,
        "selected_sessions": selected_sessions,
        "session_total_r": round(session_total_r, 6),
        "session_expectancy_r": round(session_total_r / selected_sessions, 6) if selected_sessions else 0.0,
        "positive_session_rate": round(positive_sessions / selected_sessions, 6) if selected_sessions else 0.0,
        "positive_session_count": positive_sessions,
        "max_candidates_per_session": max(
            (int(fold["models"][model_name].get("max_candidates_per_session") or 0) for fold in folds),
            default=0,
        ),
        "brier": round(float(weighted("brier")), 6) if weighted("brier") is not None else None,
        "log_loss": round(float(weighted("log_loss")), 6) if weighted("log_loss") is not None else None,
        "roc_auc": round(float(weighted("roc_auc")), 6) if weighted("roc_auc") is not None else None,
        "expectancy_r": round(model_expectancy, 6),
        "model_expectancy_r": round(model_expectancy, 6),
        "expectancy_dollars": round(model_expectancy_dollars, 6),
        "model_expectancy_dollars": round(model_expectancy_dollars, 6),
        "always_admit_expectancy_r": round(model_expectancy, 6) if model_name == "always_admit" else None,
        "always_admit_expectancy_dollars": round(model_expectancy_dollars, 6) if model_name == "always_admit" else None,
        "profit_factor": _aggregate_profit_factor(folds, model_name),
        "max_drawdown_r": _aggregate_drawdown(folds, model_name),
        "exposure_rate": round(selected / total, 6) if total else 0.0,
        "threshold_selection": "always_admit" if model_name == "always_admit" else "calibration_expected_net_r_after_costs",
        "selected_thresholds": thresholds,
    }


def _select_model(model_comparison: dict[str, dict[str, Any]], *, minimum_selected: int) -> str:
    candidates = {
        name: metrics for name, metrics in model_comparison.items()
        if name != "always_admit" and metrics["selected"] >= minimum_selected
    }
    if not candidates:
        candidates = {name: metrics for name, metrics in model_comparison.items() if name != "always_admit"}
    return max(candidates, key=lambda name: (candidates[name]["expectancy_r"], candidates[name]["selected"]))


def _holdout_summary(fold: dict[str, Any], selected_model: str) -> dict[str, Any]:
    metrics = dict((fold.get("models") or {}).get(selected_model) or {})
    metrics = {key: value for key, value in metrics.items() if not key.startswith("_")}
    metrics.update({
        "sessions": int(fold.get("sessions") or 0),
        "train_end": fold.get("train_end"),
        "test_start": fold.get("test_start"),
        "test_end": fold.get("test_end"),
        "embargo_sessions": int(fold.get("embargo_sessions") or 0),
        "selected_model": selected_model,
    })
    return metrics


def _stability(folds: list[dict[str, Any]], selected_model: str) -> dict[str, Any]:
    expectancies = [fold["models"][selected_model]["expectancy_r"] for fold in folds]
    selected = [fold["models"][selected_model]["selected"] for fold in folds]
    return {
        "folds": len(folds),
        "positive_fold_count": sum(value > 0 for value in expectancies),
        "expectancy_r_min": round(min(expectancies), 6) if expectancies else 0.0,
        "expectancy_r_max": round(max(expectancies), 6) if expectancies else 0.0,
        "expectancy_r_std": round(float(np.std(expectancies)), 6) if expectancies else 0.0,
        "selected_min": min(selected) if selected else 0,
        "selected_max": max(selected) if selected else 0,
    }


def _strategy(row: dict[str, Any]) -> str:
    return str((row.get("candidate") or {}).get("strategy_id") or "unknown")


def _regime(row: dict[str, Any]) -> str:
    return str(((row.get("candidate") or {}).get("market_context") or {}).get("regime") or "unknown")


def _bucket(row: dict[str, Any]) -> str:
    features = decision_features(row)
    buckets = [name.removeprefix("time_bucket.") for name, value in features.items() if name.startswith("time_bucket.") and value == 1.0]
    return buckets[0] if buckets else "unknown"


def _profit_factor(values: np.ndarray) -> float | None:
    wins = float(values[values > 0].sum())
    losses = abs(float(values[values < 0].sum()))
    if losses == 0:
        return None if wins == 0 else 999999.0
    return round(wins / losses, 6)


def _max_drawdown(values: np.ndarray) -> float:
    peak = 0.0
    max_drawdown = 0.0
    cumulative = 0.0
    for value in values:
        cumulative += float(value)
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative - peak)
    return round(max_drawdown, 6)


def _aggregate_profit_factor(folds: list[dict[str, Any]], model_name: str) -> float | None:
    gains = sum(float(fold["models"][model_name].get("gross_profit_r") or 0.0) for fold in folds)
    losses = sum(float(fold["models"][model_name].get("gross_loss_r") or 0.0) for fold in folds)
    if losses == 0:
        return None if gains == 0 else 999999.0
    return round(gains / losses, 6)


def _aggregate_drawdown(folds: list[dict[str, Any]], model_name: str) -> float:
    cumulative = 0.0
    peak = 0.0
    worst = 0.0
    for fold in folds:
        metrics = fold["models"][model_name]
        fold_min = float(metrics.get("min_equity_r") or 0.0)
        fold_max = float(metrics.get("max_equity_r") or 0.0)
        worst = min(worst, float(metrics.get("max_drawdown_r") or 0.0), cumulative + fold_min - peak)
        peak = max(peak, cumulative + fold_max)
        cumulative += float(metrics.get("total_r") or 0.0)
    return round(worst, 6)
