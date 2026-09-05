from __future__ import annotations

from collections import Counter, defaultdict
import math
from statistics import median
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer

from trading_lab.data_quality import classify_evidence_quality_flags
from trading_lab.decision_features import FEATURE_NAMES, decision_features


COST_SCENARIOS = (
    "v5_conservative",
    "robinhood_small_equity",
    "zero_friction_upper_bound",
    "double_slippage_stress",
)


def cost_scenario_net_r(row: dict[str, Any], scenario: str) -> float:
    """Reprice an existing v5 outcome without changing its observed fill path."""
    if scenario not in COST_SCENARIOS:
        raise ValueError(f"unknown cost scenario: {scenario}")
    outcome = row.get("outcome") or {}
    if str(outcome.get("fill_status") or "") == "no_fill":
        return 0.0
    risk = float((row.get("candidate") or {}).get("risk_dollars") or 0.0)
    if risk <= 0:
        return 0.0
    net = float(outcome.get("net_dollars") or 0.0)
    fees = float(outcome.get("fees") or 0.0)
    entry_slippage = float(outcome.get("entry_slippage_dollars") or 0.0)
    exit_slippage = float(outcome.get("exit_slippage_dollars") or 0.0)
    if scenario == "robinhood_small_equity":
        net += fees
    elif scenario == "zero_friction_upper_bound":
        net += fees + entry_slippage + exit_slippage
    elif scenario == "double_slippage_stress":
        net -= entry_slippage + exit_slippage
    return net / risk


def liquidity_drift_experiment(
    rows: list[dict[str, Any]], *, window_fraction: float = 0.2,
) -> dict[str, Any]:
    usable, excluded_missing_session = _usable_session_rows(rows, require_label=False)
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        by_session[_session(row)].append(row)
    sessions = sorted(by_session)
    if len(sessions) < 2:
        return {
            "status": "skipped", "warning": "multiple_sessions_required",
            "excluded_missing_session": excluded_missing_session,
        }
    window = max(1, min(len(sessions) // 2, int(round(len(sessions) * window_fraction))))
    early = [row for session in sessions[:window] for row in by_session[session]]
    recent = [row for session in sessions[-window:] for row in by_session[session]]
    early_all_values = _feature_values(early, "dollar_volume_log")
    recent_all_values = _feature_values(recent, "dollar_volume_log")
    early_values = _finite_values(early_all_values)
    recent_values = _finite_values(recent_all_values)
    early_top = _top_tickers(early)
    recent_top = _top_tickers(recent)
    return {
        "status": "evaluated",
        "excluded_missing_session": excluded_missing_session,
        "early_sessions": window,
        "recent_sessions": window,
        "early_rows": len(early),
        "recent_rows": len(recent),
        "dollar_volume_log": {
            "early_median": round(float(median(early_values)), 6) if early_values else None,
            "recent_median": round(float(median(recent_values)), 6) if recent_values else None,
            "early_missing_rate": _missing_rate(early_all_values),
            "recent_missing_rate": _missing_rate(recent_all_values),
            "psi": _psi(early_all_values, recent_all_values),
        },
        "early_top_tickers": early_top,
        "recent_top_tickers": recent_top,
        "ticker_composition_changed": bool(early_top and recent_top and early_top[0]["ticker"] != recent_top[0]["ticker"]),
        "by_strategy": _liquidity_by_strategy(early, recent),
    }


def cost_sensitivity_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable, excluded_missing_session = _usable_session_rows(rows)
    filled = [
        row for row in usable
        if str((row.get("outcome") or {}).get("fill_status") or "") == "filled"
    ]
    strategies = sorted({str((row.get("candidate") or {}).get("strategy_id") or "unknown") for row in filled})
    all_filled = {}
    for scenario in COST_SCENARIOS:
        metrics = _metrics(filled, scenario)
        all_filled[scenario] = {
            "filled": metrics["selected"],
            "sessions": metrics["selected_sessions"],
            "expectancy_r": metrics["expectancy_r"],
            "profit_factor": metrics["profit_factor"],
        }
    by_strategy = {}
    for strategy in strategies:
        strategy_rows = [row for row in filled if str((row.get("candidate") or {}).get("strategy_id") or "unknown") == strategy]
        by_strategy[strategy] = {
            scenario: _metrics(strategy_rows, scenario) for scenario in COST_SCENARIOS
        }
    return {
        "excluded_missing_session": excluded_missing_session,
        "all_filled": all_filled,
        "by_strategy": by_strategy,
    }


def cost_aware_ranking_experiment(
    rows: list[dict[str, Any]], *, folds: int = 4, final_holdout_fraction: float = 0.2,
    embargo_sessions: int = 1, minimum_selected: int = 25, minimum_selected_sessions: int = 20,
) -> dict[str, Any]:
    usable, excluded_missing_session = _usable_session_rows(rows)
    sessions = sorted({_session(row) for row in usable})
    if len(sessions) < max(12, folds * 2):
        return {
            "status": "skipped", "warning": "insufficient_sessions",
            "excluded_missing_session": excluded_missing_session,
        }
    holdout_count = max(1, int(round(len(sessions) * final_holdout_fraction)))
    development_sessions = sessions[:-holdout_count]
    holdout_sessions = sessions[-holdout_count:]
    initial_train = max(5, len(development_sessions) // 2)
    edges = np.linspace(initial_train, len(development_sessions), folds + 1, dtype=int)
    development_scored: list[tuple[dict[str, Any], float]] = []
    for fold in range(folds):
        test_start = int(edges[fold])
        test_end = int(edges[fold + 1])
        train_end = max(1, test_start - embargo_sessions)
        train_set = set(development_sessions[:train_end])
        test_set = set(development_sessions[test_start:test_end])
        train_rows = [row for row in usable if _session(row) in train_set]
        test_rows = [row for row in usable if _session(row) in test_set]
        if train_rows and test_rows:
            predictions = _fit_predict_expected_r(train_rows, test_rows)
            development_scored.extend(zip(test_rows, predictions, strict=True))
    if not development_scored:
        return {"status": "skipped", "warning": "no_walk_forward_predictions"}
    policy_names = (
        "positive_expected_utility",
        "top1_per_signal_time",
        "top2_per_signal_time",
        "top1_per_session",
    )
    development_policies = {
        name: _metrics([row for row, _ in _apply_ranking_policy(development_scored, name)], "v5_conservative")
        for name in policy_names
    }
    viable = [
        name for name in policy_names
        if development_policies[name]["selected"] >= minimum_selected
        and development_policies[name]["selected_sessions"] >= minimum_selected_sessions
    ]
    selected_policy = max(
        viable,
        key=lambda name: (development_policies[name]["expectancy_r"], development_policies[name]["selected_sessions"]),
    ) if viable else None
    if selected_policy is None or development_policies[selected_policy]["expectancy_r"] <= 0:
        selected_policy = None
        final_holdout = {
            "status": "not_scored_no_positive_development_policy",
            "untouched_during_policy_selection": True,
            "sessions": len(holdout_sessions),
            "selected": 0,
            "cost_scenarios": {},
        }
    else:
        fit_session_list = development_sessions[:-embargo_sessions] if embargo_sessions else development_sessions
        fit_sessions = set(fit_session_list)
        train_rows = [row for row in usable if _session(row) in fit_sessions]
        holdout_rows = [row for row in usable if _session(row) in set(holdout_sessions)]
        holdout_predictions = _fit_predict_expected_r(train_rows, holdout_rows)
        holdout_scored = list(zip(holdout_rows, holdout_predictions, strict=True))
        selected_holdout_rows = [row for row, _ in _apply_ranking_policy(holdout_scored, selected_policy)]
        selected_count = len(selected_holdout_rows)
        selected_sessions = len({_session(row) for row in selected_holdout_rows})
        evidence_status = _holdout_evidence_status(
            selected_count, selected_sessions,
            minimum_selected=minimum_selected, minimum_sessions=minimum_selected_sessions,
        )
        final_holdout = {
            **evidence_status,
            "untouched_during_policy_selection": True,
            "sessions": len(holdout_sessions),
            "selected": selected_count,
            "selected_sessions": selected_sessions,
            "minimum_selected": minimum_selected,
            "minimum_selected_sessions": minimum_selected_sessions,
            "cost_scenarios": {
                scenario: _metrics(selected_holdout_rows, scenario) for scenario in COST_SCENARIOS
            },
        }
    return {
        "status": "evaluated",
        "excluded_missing_session": excluded_missing_session,
        "selection_basis": "development_walk_forward_v5_conservative",
        "minimum_selected": minimum_selected,
        "minimum_selected_sessions": minimum_selected_sessions,
        "policies_tested": len(policy_names),
        "selected_policy": selected_policy,
        "development_sessions": len(development_sessions),
        "development_policies": development_policies,
        "final_holdout": final_holdout,
    }


def multiple_testing_experiment(experiments: dict[str, Any], *, familywise_alpha: float = 0.05) -> dict[str, Any]:
    ledger: list[dict[str, Any]] = []
    ranking = experiments.get("ranking") or {}
    ranking_holdout = (((ranking.get("final_holdout") or {}).get("cost_scenarios") or {}).get("v5_conservative") or {})
    for variant, metrics in (ranking.get("development_policies") or {}).items():
        selected = variant == ranking.get("selected_policy")
        ledger.append(_trial_record(
            "ranking", variant, metrics,
            ranking_holdout.get("expectancy_r") if selected else None,
            selected,
        ))
    stocks = experiments.get("stocks_in_play") or {}
    stocks_holdout = (((stocks.get("final_holdout") or {}).get("cost_scenarios") or {}).get("v5_conservative") or {})
    for variant, metrics in (stocks.get("development_variants") or {}).items():
        selected = variant == stocks.get("selected_variant")
        ledger.append(_trial_record(
            "stocks_in_play", variant, metrics,
            stocks_holdout.get("expectancy_r") if selected else None,
            selected,
        ))
    ensemble = experiments.get("ensemble") or {}
    for variant, metrics in (ensemble.get("leave_one_out") or {}).items():
        ledger.append(_trial_record("ensemble_leave_one_out", variant, metrics, None, False))
    trial_count = len(ledger)
    return {
        "status": "evaluated",
        "registered_trials": trial_count,
        "familywise_alpha": familywise_alpha,
        "bonferroni_alpha": familywise_alpha / trial_count if trial_count else None,
        "positive_development_trials": sum(float(item.get("development_expectancy_r") or 0.0) > 0 for item in ledger),
        "selected_trials_with_positive_holdout": sum(
            item["selected_for_holdout"] and item.get("holdout_expectancy_r") is not None
            and float(item["holdout_expectancy_r"]) > 0 for item in ledger
        ),
        "selection_bias_warning": "variant-level returns are correlated; Bonferroni threshold is conservative and descriptive",
        "promotion_allowed": False,
        "trial_ledger": ledger,
    }


def _trial_record(
    experiment: str, variant: str, metrics: dict[str, Any], holdout_expectancy: Any, selected: bool,
) -> dict[str, Any]:
    return {
        "experiment": experiment,
        "variant": variant,
        "development_expectancy_r": metrics.get("expectancy_r"),
        "development_samples": metrics.get("selected", metrics.get("sessions")),
        "development_sessions": metrics.get("selected_sessions", metrics.get("sessions")),
        "selected_for_holdout": selected,
        "holdout_expectancy_r": holdout_expectancy,
    }


def ensemble_diversity_experiment(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable, excluded_missing_session = _usable_session_rows(rows)
    strategies = sorted({str((row.get("candidate") or {}).get("strategy_id") or "unknown") for row in usable})
    if len(strategies) < 2:
        return {
            "status": "skipped", "warning": "multiple_strategies_required",
            "excluded_missing_session": excluded_missing_session,
        }
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    overlap_groups: dict[str, set[str]] = defaultdict(set)
    for row in usable:
        strategy = str((row.get("candidate") or {}).get("strategy_id") or "unknown")
        buckets[_session(row)][strategy].append(cost_scenario_net_r(row, "v5_conservative"))
        ticker = str((row.get("candidate") or {}).get("ticker") or "unknown").upper()
        overlap_groups[f"{_signal_timestamp(row)}|{ticker}"].add(strategy)
    session_strategy = {
        session: {strategy: float(np.mean(values)) for strategy, values in by_strategy.items()}
        for session, by_strategy in buckets.items()
    }
    pairwise = {}
    for left_index, left in enumerate(strategies):
        for right in strategies[left_index + 1:]:
            overlap = [
                (values[left], values[right]) for values in session_strategy.values()
                if left in values and right in values
            ]
            if len(overlap) >= 2:
                correlation = float(np.corrcoef(
                    np.asarray([item[0] for item in overlap]), np.asarray([item[1] for item in overlap])
                )[0, 1])
                correlation_value = round(correlation, 6) if math.isfinite(correlation) else None
            else:
                correlation_value = None
            pairwise[f"{left}|{right}"] = {
                "overlap_sessions": len(overlap),
                "correlation": correlation_value,
            }
    ensemble_series = [float(np.mean(list(values.values()))) for _, values in sorted(session_strategy.items())]
    leave_one_out = {}
    for excluded in strategies:
        series = [
            float(np.mean([value for strategy, value in values.items() if strategy != excluded]))
            for _, values in sorted(session_strategy.items()) if any(strategy != excluded for strategy in values)
        ]
        leave_one_out[excluded] = _series_metrics(series)
    group_sizes = [len(values) for values in overlap_groups.values()]
    return {
        "status": "evaluated",
        "excluded_missing_session": excluded_missing_session,
        "strategies": strategies,
        "sessions": len(session_strategy),
        "pairwise_correlations": pairwise,
        "contemporaneous_overlap": {
            "groups": len(overlap_groups),
            "multi_strategy_groups": sum(size > 1 for size in group_sizes),
            "maximum_strategies_in_group": max(group_sizes, default=0),
        },
        "equal_weight_session_ensemble": _series_metrics(ensemble_series),
        "leave_one_out": leave_one_out,
    }


def _series_metrics(values: list[float]) -> dict[str, Any]:
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    return {
        "sessions": len(values),
        "expectancy_r": round(float(np.mean(values)), 6) if values else 0.0,
        "profit_factor": round(gains / losses, 6) if losses > 0 else None,
    }


def stocks_in_play_experiment(
    rows: list[dict[str, Any]], *, final_holdout_fraction: float = 0.2,
    minimum_selected: int = 25, minimum_selected_sessions: int = 20,
) -> dict[str, Any]:
    usable, excluded_missing_session = _usable_session_rows(rows)
    sessions = sorted({_session(row) for row in usable})
    if len(sessions) < 10:
        return {
            "status": "skipped", "warning": "insufficient_sessions",
            "excluded_missing_session": excluded_missing_session,
        }
    holdout_count = max(1, int(round(len(sessions) * final_holdout_fraction)))
    development_session_set = set(sessions[:-holdout_count])
    holdout_session_set = set(sessions[-holdout_count:])
    development = [row for row in usable if _session(row) in development_session_set]
    holdout = [row for row in usable if _session(row) in holdout_session_set]
    feature_names = ("volume_ratio", "range_pct", "gap_pct", "dollar_volume_log")
    coverage = {
        name: round(len(_finite_feature_values(usable, name)) / len(usable), 6) if usable else 0.0
        for name in feature_names
    }
    range_values = _finite_feature_values(development, "range_pct")
    liquidity_values = _finite_feature_values(development, "dollar_volume_log")
    thresholds = {
        "volume_ratio": 1.5,
        "range_pct_q75": float(np.quantile(range_values, 0.75)) if range_values else None,
        "dollar_volume_log_median": float(np.median(liquidity_values)) if liquidity_values else None,
    }
    variants = (
        "all_candidates",
        "relative_volume_at_least_1_5",
        "high_range_development_q75",
        "relative_volume_and_high_range",
        "relative_volume_and_high_liquidity",
    )
    development_variants = {
        name: _metrics(_stocks_in_play_select(development, name, thresholds), "v5_conservative")
        for name in variants
    }
    viable = [
        name for name in variants
        if development_variants[name]["selected"] >= minimum_selected
        and development_variants[name]["selected_sessions"] >= minimum_selected_sessions
    ]
    selected_variant = max(
        viable,
        key=lambda name: (development_variants[name]["expectancy_r"], development_variants[name]["selected_sessions"]),
    ) if viable else None
    if selected_variant is None or development_variants[selected_variant]["expectancy_r"] <= 0:
        selected_variant = None
        final_holdout = {
            "status": "not_scored_no_positive_development_variant",
            "untouched_during_variant_selection": True,
            "sessions": len(holdout_session_set),
            "selected": 0,
            "cost_scenarios": {},
        }
    else:
        selected_holdout = _stocks_in_play_select(holdout, selected_variant, thresholds)
        selected_count = len(selected_holdout)
        selected_sessions = len({_session(row) for row in selected_holdout})
        evidence_status = _holdout_evidence_status(
            selected_count, selected_sessions,
            minimum_selected=minimum_selected, minimum_sessions=minimum_selected_sessions,
        )
        final_holdout = {
            **evidence_status,
            "untouched_during_variant_selection": True,
            "sessions": len(holdout_session_set),
            "selected": selected_count,
            "selected_sessions": selected_sessions,
            "minimum_selected": minimum_selected,
            "minimum_selected_sessions": minimum_selected_sessions,
            "cost_scenarios": {
                scenario: _metrics(selected_holdout, scenario) for scenario in COST_SCENARIOS
            },
        }
    blocked = []
    if coverage["gap_pct"] < 0.8:
        blocked.append("historical_point_in_time_gap_feature_incomplete")
    blocked.append("historical_point_in_time_catalyst_feed_missing")
    return {
        "status": "evaluated",
        "excluded_missing_session": excluded_missing_session,
        "variants_tested": len(variants),
        "feature_coverage": coverage,
        "thresholds_fitted_on_development_only": thresholds,
        "blocked_components": blocked,
        "minimum_selected": minimum_selected,
        "minimum_selected_sessions": minimum_selected_sessions,
        "selected_variant": selected_variant,
        "development_variants": development_variants,
        "final_holdout": final_holdout,
    }


def _stocks_in_play_select(
    rows: list[dict[str, Any]], variant: str, thresholds: dict[str, float | None],
) -> list[dict[str, Any]]:
    if variant == "all_candidates":
        return list(rows)
    selected = []
    for row in rows:
        features = decision_features(row)
        rvol = float(features.get("volume_ratio", np.nan))
        range_pct = float(features.get("range_pct", np.nan))
        liquidity = float(features.get("dollar_volume_log", np.nan))
        high_rvol = math.isfinite(rvol) and rvol >= float(thresholds["volume_ratio"] or 1.5)
        high_range = (
            math.isfinite(range_pct) and thresholds["range_pct_q75"] is not None
            and range_pct >= float(thresholds["range_pct_q75"])
        )
        high_liquidity = (
            math.isfinite(liquidity) and thresholds["dollar_volume_log_median"] is not None
            and liquidity >= float(thresholds["dollar_volume_log_median"])
        )
        keep = (
            (variant == "relative_volume_at_least_1_5" and high_rvol)
            or (variant == "high_range_development_q75" and high_range)
            or (variant == "relative_volume_and_high_range" and high_rvol and high_range)
            or (variant == "relative_volume_and_high_liquidity" and high_rvol and high_liquidity)
        )
        if keep:
            selected.append(row)
    return selected


def _fit_predict_expected_r(
    train_rows: list[dict[str, Any]], test_rows: list[dict[str, Any]],
) -> list[float]:
    train_x = np.asarray([[decision_features(row)[name] for name in FEATURE_NAMES] for row in train_rows], dtype=float)
    test_x = np.asarray([[decision_features(row)[name] for name in FEATURE_NAMES] for row in test_rows], dtype=float)
    train_y = np.asarray([cost_scenario_net_r(row, "v5_conservative") for row in train_rows], dtype=float)
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    fitted_x = imputer.fit_transform(train_x)
    model = GradientBoostingRegressor(n_estimators=50, max_depth=2, learning_rate=0.05, random_state=0)
    model.fit(fitted_x, train_y)
    return [float(value) for value in model.predict(imputer.transform(test_x))]


def _apply_ranking_policy(
    scored: list[tuple[dict[str, Any], float]], policy: str,
) -> list[tuple[dict[str, Any], float]]:
    if policy == "positive_expected_utility":
        return [item for item in scored if item[1] > 0]
    grouped: dict[str, list[tuple[dict[str, Any], float]]] = defaultdict(list)
    for item in scored:
        key = _session(item[0]) if policy == "top1_per_session" else _signal_timestamp(item[0])
        grouped[key].append(item)
    limit = 2 if policy == "top2_per_signal_time" else 1
    return [
        item for key in sorted(grouped)
        for item in sorted(grouped[key], key=lambda pair: pair[1], reverse=True)[:limit]
    ]


def _holdout_evidence_status(
    selected: int, selected_sessions: int, *, minimum_selected: int, minimum_sessions: int,
) -> dict[str, Any]:
    meets = selected >= minimum_selected and selected_sessions >= minimum_sessions
    return {
        "status": "scored_once" if meets else "scored_once_insufficient_evidence",
        "meets_minimum_evidence": meets,
    }


def _metrics(rows: list[dict[str, Any]], scenario: str) -> dict[str, Any]:
    valid_rows = [row for row in rows if _session(row)]
    excluded_missing_session = len(rows) - len(valid_rows)
    values = [cost_scenario_net_r(row, scenario) for row in valid_rows]
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    session_returns: dict[str, float] = defaultdict(float)
    for row, value in zip(valid_rows, values, strict=True):
        session_returns[_session(row)] += value
    chronological_returns = [session_returns[session] for session in sorted(session_returns)]
    equity = np.cumsum(np.asarray(chronological_returns, dtype=float))
    equity_with_origin = np.concatenate(([0.0], equity))
    peaks = np.maximum.accumulate(equity_with_origin)
    drawdown = float(np.min(equity_with_origin - peaks)) if len(equity_with_origin) else 0.0
    sessions = {_session(row) for row in valid_rows}
    return {
        "selected": len(valid_rows),
        "selected_sessions": len(sessions),
        "excluded_missing_session": excluded_missing_session,
        "expectancy_r": round(float(np.mean(values)), 6) if values else 0.0,
        "profit_factor": round(gains / losses, 6) if losses > 0 else None,
        "max_drawdown_r": round(drawdown, 6),
    }


def _usable_rows(rows: list[dict[str, Any]], *, require_label: bool = True) -> list[dict[str, Any]]:
    allowed = {"policy_approved", "admitted_portfolio", "admitted_research", "slot_blocked"}
    usable = []
    for row in rows:
        if str(row.get("disposition") or "") not in allowed:
            continue
        quality = classify_evidence_quality_flags((row.get("outcome") or {}).get("data_quality_flags"))
        if quality["has_exclusion"] or quality["has_fatal"]:
            continue
        if require_label and (row.get("outcome") or {}).get("net_r") is None:
            continue
        usable.append(row)
    return usable


def _usable_session_rows(
    rows: list[dict[str, Any]], *, require_label: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    usable = _usable_rows(rows, require_label=require_label)
    valid = [row for row in usable if _session(row)]
    return valid, len(usable) - len(valid)


def _signal_timestamp(row: dict[str, Any]) -> str:
    return str(((row.get("candidate") or {}).get("market_context") or {}).get("signal_timestamp") or "")


def _session(row: dict[str, Any]) -> str:
    signal = _signal_timestamp(row)
    return signal[:10] if len(signal) >= 10 else ""


def _finite_feature_values(rows: list[dict[str, Any]], name: str) -> list[float]:
    return _finite_values(_feature_values(rows, name))


def _feature_values(rows: list[dict[str, Any]], name: str) -> list[float]:
    values = [decision_features(row).get(name) for row in rows]
    return [float(value) if value is not None else math.nan for value in values]


def _finite_values(values: list[float]) -> list[float]:
    return [value for value in values if math.isfinite(value)]


def _missing_rate(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(not math.isfinite(value) for value in values) / len(values), 6)


def _top_tickers(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    counts = Counter(str((row.get("candidate") or {}).get("ticker") or "unknown").upper() for row in rows)
    total = sum(counts.values())
    return [
        {"ticker": ticker, "rows": count, "share": round(count / total, 6) if total else 0.0}
        for ticker, count in counts.most_common(limit)
    ]


def _liquidity_by_strategy(early: list[dict[str, Any]], recent: list[dict[str, Any]]) -> dict[str, Any]:
    strategies = sorted({str((row.get("candidate") or {}).get("strategy_id") or "unknown") for row in early + recent})
    result = {}
    for strategy in strategies:
        old_all = _feature_values([row for row in early if (row.get("candidate") or {}).get("strategy_id") == strategy], "dollar_volume_log")
        new_all = _feature_values([row for row in recent if (row.get("candidate") or {}).get("strategy_id") == strategy], "dollar_volume_log")
        old = _finite_values(old_all)
        new = _finite_values(new_all)
        result[strategy] = {
            "early_median": round(float(median(old)), 6) if old else None,
            "recent_median": round(float(median(new)), 6) if new else None,
            "early_missing_rate": _missing_rate(old_all),
            "recent_missing_rate": _missing_rate(new_all),
            "psi": _psi(old_all, new_all),
        }
    return result


def _psi(early: list[float], recent: list[float]) -> float | None:
    if not early or not recent:
        return None
    early_array = np.asarray(early, dtype=float)
    recent_array = np.asarray(recent, dtype=float)
    pooled = np.concatenate((early_array[np.isfinite(early_array)], recent_array[np.isfinite(recent_array)]))
    if not len(pooled):
        return None
    internal = np.unique(np.quantile(pooled, np.linspace(0.1, 0.9, 9)))
    edges = np.concatenate(([-np.inf], internal, [np.inf]))
    early_counts = np.histogram(early_array[np.isfinite(early_array)], bins=edges)[0].astype(float)
    recent_counts = np.histogram(recent_array[np.isfinite(recent_array)], bins=edges)[0].astype(float)
    early_rates = np.append(early_counts / len(early_array), 1.0 - np.isfinite(early_array).mean())
    recent_rates = np.append(recent_counts / len(recent_array), 1.0 - np.isfinite(recent_array).mean())
    early_rates = np.clip(early_rates, 1e-6, None)
    recent_rates = np.clip(recent_rates, 1e-6, None)
    return round(float(np.sum((recent_rates - early_rates) * np.log(recent_rates / early_rates))), 6)
