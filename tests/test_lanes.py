from trading_lab.lanes import is_portfolio_admitted


def test_unmarked_legacy_row_is_research_only_for_reporting():
    assert is_portfolio_admitted({"rule_checklist": {}}) is False


def test_unmarked_legacy_row_counts_as_admitted_for_risk_accounting():
    assert is_portfolio_admitted(
        {"rule_checklist": {}}, unknown_counts_as_admitted=True
    ) is True


def test_explicit_lane_marker_always_wins():
    assert is_portfolio_admitted(
        {"rule_checklist": {"portfolio_admitted": False}},
        unknown_counts_as_admitted=True,
    ) is False