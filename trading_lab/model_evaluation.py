from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

_BASE_FIELDS = ("planned_entry", "stop", "target", "risk_dollars")
_CONTEXT_FIELDS = (
    "relative_volume", "volume_ratio", "scanner_score", "regime_score", "atr",
    "vwap", "distance_from_vwap", "range_pct", "gap_pct", "market_return",
)


def decision_features(row: dict[str, Any]) -> dict[str, float]:
    """Extract an explicit decision-time allowlist. Outcome data never enters X."""
    candidate = row.get("candidate") or {}
    features: dict[str, float] = {}
    for field in _BASE_FIELDS:
        value = candidate.get(field)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            features[field] = float(value)
    context = candidate.get("market_context") or {}
    for field in _CONTEXT_FIELDS:
        value = context.get(field)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            features[f"market_context.{field}"] = float(value)
    if "planned_entry" in features and "stop" in features and features["planned_entry"]:
        features["stop_distance_pct"] = abs(features["planned_entry"] - features["stop"]) / abs(features["planned_entry"])
    return features


def purged_walk_forward_evaluate(
    rows: list[dict[str, Any]],
    *,
    minimum_samples: int = 1_000,
    folds: int = 5,
    embargo_sessions: int = 1,
) -> dict[str, Any]:
    usable = [row for row in rows if _session(row) and _label(row) is not None]
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
    if not any(decision_features(row) for row in usable):
        return {
            "status": "skipped", "split_policy": "purged_walk_forward_no_random_split",
            "samples": len(usable), "blockers": ["decision_features_missing"],
            "all_promotion_gates_pass": False,
        }
    sessions = sorted(by_session)
    initial_train = max(5, len(sessions) // 2)
    remaining = len(sessions) - initial_train
    if remaining < folds:
        return {
            "status": "skipped", "split_policy": "purged_walk_forward_no_random_split",
            "samples": len(usable), "blockers": [f"sessions_below_fold_requirement:{len(sessions)}"],
            "all_promotion_gates_pass": False,
        }
    fold_results = []
    edges = np.linspace(initial_train, len(sessions), folds + 1, dtype=int)
    for fold_index in range(folds):
        test_start_index = int(edges[fold_index])
        test_end_index = int(edges[fold_index + 1])
        train_end_index = max(1, test_start_index - embargo_sessions)
        train_sessions = sessions[:train_end_index]
        test_sessions = sessions[test_start_index:test_end_index]
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
    aggregate = _aggregate(fold_results)
    promotion_gates = {
        "selected_candidates": aggregate["selected"] > 0,
        "positive_model_expectancy": aggregate["model_expectancy_r"] > 0,
        "beats_always_admit": aggregate["model_expectancy_r"] > aggregate["always_admit_expectancy_r"],
        "positive_every_fold": all(fold["model_expectancy_r"] > 0 for fold in fold_results),
    }
    return {
        "status": "evaluated",
        "model": "logistic_regression_with_fold_local_sigmoid_calibration",
        "split_policy": "purged_walk_forward_no_random_split",
        "samples": len(usable),
        "sessions": len(sessions),
        "folds": fold_results,
        "aggregate": aggregate,
        "promotion_gates": promotion_gates,
        "all_promotion_gates_pass": all(promotion_gates.values()),
        "blockers": [name for name, passed in promotion_gates.items() if not passed],
    }


def _evaluate_fold(index, train_rows, test_rows, train_sessions, test_sessions, embargo_sessions):
    calibration_session_index = max(1, int(len(train_sessions) * 0.8))
    fit_sessions = set(train_sessions[:calibration_session_index])
    fit_rows = [row for row in train_rows if _session(row) in fit_sessions]
    calibration_rows = [row for row in train_rows if _session(row) not in fit_sessions]
    feature_names = sorted({key for row in fit_rows for key in decision_features(row)})
    x_fit = _matrix(fit_rows, feature_names)
    y_fit = np.asarray([_label(row) for row in fit_rows], dtype=int)
    x_test = _matrix(test_rows, feature_names)
    y_test = np.asarray([_label(row) for row in test_rows], dtype=int)
    base = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=1_000)),
    ])
    base.fit(x_fit, y_fit)
    calibration_labels = np.asarray([_label(row) for row in calibration_rows], dtype=int)
    if calibration_rows and len(set(calibration_labels)) == 2:
        raw_cal = _logit(base.predict_proba(_matrix(calibration_rows, feature_names))[:, 1]).reshape(-1, 1)
        calibrator = LogisticRegression(max_iter=1_000).fit(raw_cal, calibration_labels)
        probabilities = calibrator.predict_proba(_logit(base.predict_proba(x_test)[:, 1]).reshape(-1, 1))[:, 1]
    else:
        probabilities = base.predict_proba(x_test)[:, 1]
    net_r = np.asarray([float((row.get("outcome") or {}).get("net_r") or 0.0) for row in test_rows])
    net_dollars = np.asarray([_net_dollars(row) for row in test_rows])
    selected = probabilities >= 0.5
    return {
        "fold": index + 1,
        "train_start": train_sessions[0],
        "train_end": train_sessions[-1],
        "test_start": test_sessions[0],
        "test_end": test_sessions[-1],
        "embargo_sessions": embargo_sessions,
        "train_samples": len(train_rows),
        "base_train_end": train_sessions[calibration_session_index - 1],
        "calibration_start": train_sessions[calibration_session_index] if calibration_session_index < len(train_sessions) else None,
        "test_samples": len(test_rows),
        "brier": round(float(brier_score_loss(y_test, probabilities)), 6),
        "log_loss": round(float(log_loss(y_test, probabilities, labels=[0, 1])), 6),
        "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 6) if len(set(y_test)) == 2 else None,
        "always_admit_expectancy_r": round(float(net_r.mean()), 6),
        "model_expectancy_r": round(float(net_r[selected].mean()), 6) if selected.any() else 0.0,
        "always_admit_expectancy_dollars": round(float(net_dollars.mean()), 6),
        "model_expectancy_dollars": round(float(net_dollars[selected].mean()), 6) if selected.any() else 0.0,
        "selected": int(selected.sum()),
        "by_strategy": _slice_metrics(test_rows, selected, net_r, net_dollars, "strategy"),
        "by_regime": _slice_metrics(test_rows, selected, net_r, net_dollars, "regime"),
    }


def _matrix(rows, names):
    return np.asarray([[decision_features(row).get(name, np.nan) for name in names] for row in rows], dtype=float)


def _session(row):
    signal = str(((row.get("candidate") or {}).get("market_context") or {}).get("signal_timestamp") or "")
    return signal[:10] if len(signal) >= 10 else ""


def _label(row):
    outcome = row.get("outcome") or {}
    reason = outcome.get("exit_reason")
    if reason == "target":
        return 1
    if reason == "stop":
        return 0
    if outcome.get("fill_status") == "filled":
        return int(float(outcome.get("net_r") or 0.0) > 0)
    return None


def _net_dollars(row):
    outcome = row.get("outcome") or {}
    if outcome.get("net_dollars") is not None:
        return float(outcome["net_dollars"])
    return float(outcome.get("net_r") or 0.0) * float((row.get("candidate") or {}).get("risk_dollars") or 0.0)


def _logit(values):
    clipped = np.clip(values, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped))


def _slice_metrics(rows, selected, net_r, net_dollars, kind):
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        candidate = row.get("candidate") or {}
        if kind == "strategy":
            key = str(candidate.get("strategy_id") or "unknown")
        else:
            key = str((candidate.get("market_context") or {}).get("regime") or "unknown")
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
            "always_admit_expectancy_dollars": round(float(dollars.mean()), 6),
            "model_expectancy_dollars": round(float(dollars[chosen].mean()), 6) if chosen.any() else 0.0,
        }
    return result


def _aggregate(folds):
    total = sum(fold["test_samples"] for fold in folds)
    selected = sum(fold["selected"] for fold in folds)

    def weighted(key):
        return sum(fold[key] * fold["test_samples"] for fold in folds) / total

    model_expectancy = (
        sum(fold["model_expectancy_r"] * fold["selected"] for fold in folds) / selected if selected else 0.0
    )
    model_expectancy_dollars = (
        sum(fold["model_expectancy_dollars"] * fold["selected"] for fold in folds) / selected
        if selected else 0.0
    )
    return {
        "test_samples": total,
        "selected": selected,
        "brier": round(weighted("brier"), 6),
        "log_loss": round(weighted("log_loss"), 6),
        "always_admit_expectancy_r": round(weighted("always_admit_expectancy_r"), 6),
        "model_expectancy_r": round(model_expectancy, 6),
        "always_admit_expectancy_dollars": round(weighted("always_admit_expectancy_dollars"), 6),
        "model_expectancy_dollars": round(model_expectancy_dollars, 6),
    }
