import pytest
from datetime import date, timedelta

from scripts.run_research_experiments import (
    build_research_experiment_report,
    validate_research_evidence_integrity,
)
from trading_lab.research_experiments import (
    cost_aware_ranking_experiment,
    cost_scenario_net_r,
    ensemble_diversity_experiment,
    liquidity_drift_experiment,
    multiple_testing_experiment,
    stocks_in_play_experiment,
    _holdout_evidence_status,
    _metrics,
)


def test_cost_scenarios_separate_commission_from_execution_friction():
    row = {
        "candidate": {"risk_dollars": 10.0},
        "outcome": {
            "net_dollars": 5.0,
            "net_r": 0.5,
            "fees": 1.0,
            "entry_slippage_dollars": 2.0,
            "exit_slippage_dollars": 3.0,
        },
    }

    assert cost_scenario_net_r(row, "v5_conservative") == pytest.approx(0.5)
    assert cost_scenario_net_r(row, "robinhood_small_equity") == pytest.approx(0.6)
    assert cost_scenario_net_r(row, "zero_friction_upper_bound") == pytest.approx(1.1)
    assert cost_scenario_net_r(row, "double_slippage_stress") == pytest.approx(0.0)


def test_cost_scenarios_keep_no_fills_at_zero_utility():
    row = {
        "candidate": {"risk_dollars": 10.0},
        "outcome": {"fill_status": "no_fill", "net_dollars": 0.0, "net_r": 0.0},
    }
    assert cost_scenario_net_r(row, "zero_friction_upper_bound") == 0.0


def test_metrics_drawdown_is_chronological_session_clustered_and_order_independent():
    def row(session, value):
        return {
            "disposition": "policy_approved",
            "candidate": {
                "risk_dollars": 10.0,
                "market_context": {"signal_timestamp": f"{session}T14:00:00Z"},
            },
            "outcome": {"fill_status": "filled", "net_dollars": value * 10.0, "net_r": value},
        }

    chronological = [row("2026-01-01", 1.0), row("2026-01-01", 1.0), row("2026-01-02", -1.0), row("2026-01-02", -1.0), row("2026-01-03", 1.0)]
    shuffled = [chronological[3], chronological[4], chronological[0], chronological[2], chronological[1]]

    assert _metrics(chronological, "v5_conservative")["max_drawdown_r"] == -2.0
    assert _metrics(shuffled, "v5_conservative")["max_drawdown_r"] == -2.0


def test_metrics_excludes_and_reports_rows_without_a_valid_session():
    valid = {
        "candidate": {"risk_dollars": 10.0, "market_context": {"signal_timestamp": "2026-01-01T14:00:00Z"}},
        "outcome": {"fill_status": "filled", "net_dollars": 10.0, "net_r": 1.0},
    }
    missing = {
        "candidate": {"risk_dollars": 10.0, "market_context": {}},
        "outcome": {"fill_status": "filled", "net_dollars": -1000.0, "net_r": -100.0},
    }

    result = _metrics([missing, valid], "v5_conservative")

    assert result["selected"] == 1
    assert result["selected_sessions"] == 1
    assert result["excluded_missing_session"] == 1
    assert result["expectancy_r"] == 1.0


def test_holdout_status_requires_independent_sample_and_session_minimums():
    assert _holdout_evidence_status(25, 20, minimum_selected=25, minimum_sessions=20) == {
        "status": "scored_once",
        "meets_minimum_evidence": True,
    }
    assert _holdout_evidence_status(4, 3, minimum_selected=25, minimum_sessions=20) == {
        "status": "scored_once_insufficient_evidence",
        "meets_minimum_evidence": False,
    }


def test_liquidity_drift_attributes_chronological_universe_shift():
    rows = []
    start = date(2026, 1, 1)
    for index in range(20):
        early = index < 10
        rows.append({
            "disposition": "policy_approved",
            "candidate": {
                "ticker": "AAA" if early else "BBB",
                "strategy_id": "opening-range-breakout",
                "direction": "long",
                "planned_entry": 100.0,
                "stop": 99.0,
                "target": 102.0,
                "risk_dollars": 10.0,
                "market_context": {
                    "signal_timestamp": f"{(start + timedelta(days=index)).isoformat()}T14:00:00Z",
                    "volume_ratio": 2.0,
                    "dollar_volume": 1_000_000 if early else 100_000_000,
                },
            },
            "outcome": {"fill_status": "filled", "net_r": 1.0, "data_quality_flags": []},
        })

    result = liquidity_drift_experiment(rows, window_fraction=0.5)

    assert result["status"] == "evaluated"
    assert result["early_sessions"] == 10
    assert result["recent_sessions"] == 10
    assert result["dollar_volume_log"]["early_median"] == 6.0
    assert result["dollar_volume_log"]["recent_median"] == 8.0
    assert result["dollar_volume_log"]["psi"] > 0.25
    assert result["early_top_tickers"][0]["ticker"] == "AAA"
    assert result["recent_top_tickers"][0]["ticker"] == "BBB"
    assert result["ticker_composition_changed"] is True


def test_liquidity_drift_psi_counts_missingness_as_a_bucket():
    rows = []
    start = date(2026, 1, 1)
    for index in range(20):
        context = {
            "signal_timestamp": f"{(start + timedelta(days=index)).isoformat()}T14:00:00Z",
            "volume_ratio": 2.0,
        }
        if index >= 10 or index % 2 == 0:
            context["dollar_volume"] = 1_000_000
        rows.append({
            "disposition": "policy_approved",
            "candidate": {
                "ticker": "AAA",
                "strategy_id": "opening-range-breakout",
                "direction": "long",
                "planned_entry": 100.0,
                "stop": 99.0,
                "target": 102.0,
                "risk_dollars": 10.0,
                "market_context": context,
            },
            "outcome": {"fill_status": "filled", "net_r": 1.0, "data_quality_flags": []},
        })

    result = liquidity_drift_experiment(rows, window_fraction=0.5)

    assert result["dollar_volume_log"]["early_missing_rate"] == 0.5
    assert result["dollar_volume_log"]["recent_missing_rate"] == 0.0
    assert result["dollar_volume_log"]["psi"] > 0.25


def test_cost_aware_ranking_selects_policy_before_untouched_holdout():
    rows = []
    start = date(2026, 1, 1)
    for day in range(40):
        session = start + timedelta(days=day)
        for rank in range(3):
            wins = rank == 0
            rows.append({
                "disposition": "policy_approved",
                "candidate": {
                    "ticker": f"T{rank}",
                    "strategy_id": "opening-range-breakout",
                    "direction": "long",
                    "planned_entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                    "risk_dollars": 10.0,
                    "market_context": {
                        "signal_timestamp": f"{session.isoformat()}T14:00:00Z",
                        "volume_ratio": 3.0 - rank,
                        "dollar_volume": 10_000_000,
                    },
                },
                "outcome": {
                    "fill_status": "filled",
                    "net_r": 1.0 if wins else -1.0,
                    "net_dollars": 10.0 if wins else -10.0,
                    "fees": 0.1,
                    "entry_slippage_dollars": 0.2,
                    "exit_slippage_dollars": 0.3,
                    "data_quality_flags": [],
                },
            })

    result = cost_aware_ranking_experiment(
        rows, folds=3, final_holdout_fraction=0.2, minimum_selected=5, minimum_selected_sessions=5,
    )

    assert result["status"] == "evaluated"
    assert result["selection_basis"] == "development_walk_forward_v5_conservative"
    assert result["final_holdout"]["untouched_during_policy_selection"] is True
    assert result["final_holdout"]["sessions"] == 8
    assert result["selected_policy"] in result["development_policies"]
    assert set(result["final_holdout"]["cost_scenarios"]) == {
        "v5_conservative",
        "robinhood_small_equity",
        "zero_friction_upper_bound",
        "double_slippage_stress",
    }


def test_cost_aware_ranking_keeps_holdout_closed_when_development_is_negative():
    rows = []
    start = date(2026, 1, 1)
    for day in range(30):
        rows.append({
            "disposition": "policy_approved",
            "candidate": {
                "ticker": "BAD", "strategy_id": "opening-range-breakout", "direction": "long",
                "planned_entry": 100.0, "stop": 99.0, "target": 102.0, "risk_dollars": 10.0,
                "market_context": {
                    "signal_timestamp": f"{(start + timedelta(days=day)).isoformat()}T14:00:00Z",
                    "volume_ratio": 2.0, "dollar_volume": 10_000_000,
                },
            },
            "outcome": {
                "fill_status": "filled", "net_r": -1.0, "net_dollars": -10.0,
                "fees": 0.1, "entry_slippage_dollars": 0.2, "exit_slippage_dollars": 0.3,
                "data_quality_flags": [],
            },
        })

    result = cost_aware_ranking_experiment(
        rows, folds=3, minimum_selected=5, minimum_selected_sessions=5,
    )

    assert result["selected_policy"] is None
    assert result["final_holdout"]["status"] == "not_scored_no_positive_development_policy"
    assert result["final_holdout"]["cost_scenarios"] == {}


def test_stocks_in_play_uses_point_in_time_proxies_and_reports_missing_catalysts():
    rows = []
    start = date(2026, 1, 1)
    for day in range(30):
        high_activity = day % 2 == 0
        rows.append({
            "disposition": "policy_approved",
            "candidate": {
                "ticker": "AAA",
                "strategy_id": "momentum-pullback",
                "direction": "long",
                "planned_entry": 100.0,
                "stop": 99.0,
                "target": 102.0,
                "risk_dollars": 10.0,
                "market_context": {
                    "signal_timestamp": f"{(start + timedelta(days=day)).isoformat()}T14:00:00Z",
                    "volume_ratio": 2.5 if high_activity else 0.8,
                    "dollar_volume": 20_000_000,
                    "range_pct": 0.03 if high_activity else 0.005,
                },
            },
            "outcome": {
                "fill_status": "filled",
                "net_r": 1.0 if high_activity else -1.0,
                "net_dollars": 10.0 if high_activity else -10.0,
                "fees": 0.1,
                "entry_slippage_dollars": 0.2,
                "exit_slippage_dollars": 0.3,
                "data_quality_flags": [],
            },
        })

    result = stocks_in_play_experiment(
        rows, final_holdout_fraction=0.2, minimum_selected=5, minimum_selected_sessions=5,
    )

    assert result["status"] == "evaluated"
    assert result["feature_coverage"]["volume_ratio"] == 1.0
    assert result["feature_coverage"]["gap_pct"] == 0.0
    assert "historical_point_in_time_catalyst_feed_missing" in result["blocked_components"]
    assert result["final_holdout"]["untouched_during_variant_selection"] is True
    assert result["selected_variant"] in result["development_variants"]


def test_stocks_in_play_keeps_holdout_closed_when_every_variant_loses():
    rows = []
    start = date(2026, 1, 1)
    for day in range(20):
        rows.append({
            "disposition": "policy_approved",
            "candidate": {
                "ticker": "BAD", "strategy_id": "momentum-pullback", "direction": "long",
                "planned_entry": 100.0, "stop": 99.0, "target": 102.0, "risk_dollars": 10.0,
                "market_context": {
                    "signal_timestamp": f"{(start + timedelta(days=day)).isoformat()}T14:00:00Z",
                    "volume_ratio": 2.0, "range_pct": 0.02, "dollar_volume": 10_000_000,
                },
            },
            "outcome": {
                "fill_status": "filled", "net_r": -1.0, "net_dollars": -10.0,
                "fees": 0.1, "entry_slippage_dollars": 0.2, "exit_slippage_dollars": 0.3,
                "data_quality_flags": [],
            },
        })

    result = stocks_in_play_experiment(rows, minimum_selected=5, minimum_selected_sessions=5)

    assert result["selected_variant"] is None
    assert result["final_holdout"]["status"] == "not_scored_no_positive_development_variant"
    assert result["final_holdout"]["cost_scenarios"] == {}


def test_ensemble_diversity_measures_overlap_and_incremental_strategy_information():
    rows = []
    start = date(2026, 1, 1)
    for day in range(20):
        session = start + timedelta(days=day)
        a_value = 1.0 if day % 2 == 0 else -1.0
        for strategy, value in (("alpha", a_value), ("beta", -a_value), ("clone", a_value)):
            rows.append({
                "disposition": "policy_approved",
                "candidate": {
                    "ticker": "AAA",
                    "strategy_id": strategy,
                    "direction": "long",
                    "planned_entry": 100.0,
                    "stop": 99.0,
                    "target": 102.0,
                    "risk_dollars": 10.0,
                    "market_context": {"signal_timestamp": f"{session.isoformat()}T14:00:00Z"},
                },
                "outcome": {
                    "fill_status": "filled",
                    "net_r": value,
                    "net_dollars": value * 10.0,
                    "fees": 0.0,
                    "entry_slippage_dollars": 0.0,
                    "exit_slippage_dollars": 0.0,
                    "data_quality_flags": [],
                },
            })

    result = ensemble_diversity_experiment(rows)

    assert result["status"] == "evaluated"
    assert result["pairwise_correlations"]["alpha|beta"]["correlation"] < -0.9
    assert result["pairwise_correlations"]["alpha|clone"]["correlation"] > 0.9
    assert result["contemporaneous_overlap"]["multi_strategy_groups"] == 20
    assert set(result["leave_one_out"]) == {"alpha", "beta", "clone"}


def test_multiple_testing_registry_counts_every_variant_and_never_promotes():
    experiments = {
        "ranking": {
            "development_policies": {
                "top1": {"expectancy_r": 0.2, "selected": 20, "selected_sessions": 15},
                "top2": {"expectancy_r": -0.1, "selected": 40, "selected_sessions": 20},
            },
            "selected_policy": "top1",
            "final_holdout": {"cost_scenarios": {"v5_conservative": {"expectancy_r": -0.2}}},
        },
        "stocks_in_play": {
            "development_variants": {
                "all": {"expectancy_r": -0.3, "selected": 100, "selected_sessions": 30},
                "rvol": {"expectancy_r": 0.1, "selected": 30, "selected_sessions": 20},
            },
            "selected_variant": "rvol",
            "final_holdout": {"cost_scenarios": {"v5_conservative": {"expectancy_r": 0.05}}},
        },
        "ensemble": {
            "leave_one_out": {
                "alpha": {"expectancy_r": 0.1, "sessions": 20},
                "beta": {"expectancy_r": -0.1, "sessions": 20},
            },
        },
    }

    result = multiple_testing_experiment(experiments)

    assert result["status"] == "evaluated"
    assert result["registered_trials"] == 6
    assert result["bonferroni_alpha"] == pytest.approx(0.05 / 6)
    assert result["promotion_allowed"] is False
    assert len(result["trial_ledger"]) == 6


def test_research_report_runs_all_five_experiments_without_order_authority():
    rows = []
    start = date(2026, 1, 1)
    for day in range(20):
        session = start + timedelta(days=day)
        for index, strategy in enumerate(("opening-range-breakout", "momentum-pullback")):
            value = 1.0 if (day + index) % 3 == 0 else -1.0
            rows.append({
                "disposition": "policy_approved",
                "candidate": {
                    "ticker": f"T{index}", "strategy_id": strategy, "direction": "long",
                    "planned_entry": 100.0, "stop": 99.0, "target": 102.0, "risk_dollars": 10.0,
                    "market_context": {
                        "signal_timestamp": f"{session.isoformat()}T14:00:00Z",
                        "volume_ratio": 2.0, "dollar_volume": 10_000_000, "range_pct": 0.02,
                    },
                },
                "outcome": {
                    "fill_status": "filled", "net_r": value, "net_dollars": value * 10,
                    "fees": 0.1, "entry_slippage_dollars": 0.2, "exit_slippage_dollars": 0.3,
                    "data_quality_flags": [],
                },
            })
    rows.append({
        "disposition": "policy_approved",
        "candidate": {
            "ticker": "MISSING", "strategy_id": "opening-range-breakout", "direction": "long",
            "planned_entry": 100.0, "stop": 99.0, "target": 102.0, "risk_dollars": 10.0,
            "market_context": {},
        },
        "outcome": {
            "fill_status": "filled", "net_r": 1.0, "net_dollars": 10.0,
            "fees": 0.0, "entry_slippage_dollars": 0.0, "exit_slippage_dollars": 0.0,
            "data_quality_flags": [],
        },
    })

    report = build_research_experiment_report(rows)

    assert report["mode"] == "offline_research_no_orders"
    assert report["broker_orders"] == 0
    assert report["live_trading_enabled"] is False
    assert report["cost_sensitivity"]["excluded_missing_session"] == 1
    assert report["experiments"]["liquidity_drift"]["excluded_missing_session"] == 1
    assert report["experiments"]["ranking"]["excluded_missing_session"] == 1
    assert report["experiments"]["stocks_in_play"]["excluded_missing_session"] == 1
    assert report["experiments"]["ensemble"]["excluded_missing_session"] == 1
    assert set(report["cost_sensitivity"]["all_filled"]) == {
        "v5_conservative", "robinhood_small_equity", "zero_friction_upper_bound", "double_slippage_stress"
    }
    assert report["cost_sensitivity"]["all_filled"]["v5_conservative"]["filled"] == 40
    assert set(report["experiments"]) == {
        "liquidity_drift", "ranking", "stocks_in_play", "ensemble", "multiple_testing"
    }
    assert report["experiments"]["multiple_testing"]["promotion_allowed"] is False


def test_research_runner_rejects_empty_mismatched_or_wrong_schema_evidence():
    valid_manifest = {
        "source": "test",
        "code_sha": "a" * 40,
        "schema_version": "counterfactual-candidate-v5",
        "feature_schema_version": "candidate-decision-features-v5",
        "feature_schema_sha256": "c4a7c60ac54263c08cad864244c037351a7602787b3b1f1986dfc79b73b60227",
        "coverage": {"candidate_count": 10},
    }
    validate_research_evidence_integrity(
        {"verified": True, "errors": [], "artifacts": 1}, rows_count=10, manifest=valid_manifest,
    )

    with pytest.raises(ValueError, match="no_artifacts"):
        validate_research_evidence_integrity(
            {"verified": True, "errors": [], "artifacts": 0}, rows_count=0,
            manifest={**valid_manifest, "coverage": {"candidate_count": 0}},
        )
    with pytest.raises(ValueError, match="row_count_mismatch"):
        validate_research_evidence_integrity(
            {"verified": True, "errors": [], "artifacts": 1}, rows_count=9, manifest=valid_manifest,
        )
    with pytest.raises(ValueError, match="schema_version_mismatch"):
        validate_research_evidence_integrity(
            {"verified": True, "errors": [], "artifacts": 1}, rows_count=10,
            manifest={**valid_manifest, "schema_version": "wrong"},
        )
