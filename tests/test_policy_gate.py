from trading_lab.policy_gate import PolicyGate, PolicyViolation


def test_policy_gate_accepts_valid_stock_proposal_inside_limits():
    gate = PolicyGate(account_equity=1000, max_risk_pct=0.01, max_trades_per_day=3)

    result = gate.validate(
        {
            "ticker": "AAPL",
            "asset_class": "stock",
            "direction": "long",
            "planned_entry": 101.0,
            "stop": 100.0,
            "target": 103.0,
            "risk_dollars": 10.0,
            "strategy_id": "opening-range-breakout",
        }
    )

    assert result.ok is True
    assert result.position_size == 10
    assert result.position_notional == 1010
    assert result.planned_r_multiple == 2.0


def test_policy_gate_rejects_banned_asset_and_missing_stop():
    gate = PolicyGate(account_equity=1000)

    result = gate.validate(
        {
            "ticker": "BTC-USD",
            "asset_class": "crypto",
            "direction": "long",
            "planned_entry": 101.0,
            "target": 103.0,
            "risk_dollars": 10.0,
            "strategy_id": "opening-range-breakout",
        }
    )

    assert result.ok is False
    assert PolicyViolation.BANNED_ASSET.value in result.violations
    assert PolicyViolation.MISSING_STOP.value in result.violations


def test_policy_gate_rejects_bad_reward_to_risk_and_excess_daily_trades():
    gate = PolicyGate(account_equity=1000, max_trades_per_day=1)

    result = gate.validate(
        {
            "ticker": "MSFT",
            "asset_class": "stock",
            "direction": "long",
            "planned_entry": 100.0,
            "stop": 99.0,
            "target": 100.5,
            "risk_dollars": 5.0,
            "strategy_id": "vwap-reclaim-rejection",
        },
        trades_today=1,
    )

    assert result.ok is False
    assert PolicyViolation.REWARD_RISK_TOO_LOW.value in result.violations
    assert PolicyViolation.DAILY_TRADE_LIMIT.value in result.violations


def test_policy_gate_rejects_tiny_stop_that_creates_absurd_notional():
    gate = PolicyGate(account_equity=1000)

    result = gate.validate(
        {
            "ticker": "MSFT",
            "asset_class": "stock",
            "direction": "short",
            "planned_entry": 375.29,
            "stop": 375.35,
            "target": 375.17,
            "risk_dollars": 10.0,
            "strategy_id": "opening-range-breakout",
        }
    )

    assert result.ok is False
    assert PolicyViolation.STOP_TOO_TIGHT.value in result.violations
    assert PolicyViolation.POSITION_TOO_LARGE.value in result.violations
    assert result.position_notional > 2000
