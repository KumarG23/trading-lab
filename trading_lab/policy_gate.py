from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class PolicyViolation(str, Enum):
    BANNED_ASSET = "banned_asset"
    BANNED_TICKER = "banned_ticker"
    MISSING_ENTRY = "missing_entry"
    MISSING_STOP = "missing_stop"
    MISSING_TARGET = "missing_target"
    INVALID_DIRECTION = "invalid_direction"
    MISSING_STRATEGY = "missing_strategy"
    SHORTING_DISABLED = "shorting_disabled"
    INVALID_RISK = "invalid_risk"
    RISK_TOO_HIGH = "risk_too_high"
    REWARD_RISK_TOO_LOW = "reward_risk_too_low"
    POSITION_TOO_LARGE = "position_too_large"
    STOP_TOO_TIGHT = "stop_too_tight"
    DAILY_TRADE_LIMIT = "daily_trade_limit"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    WEEKLY_LOSS_LIMIT = "weekly_loss_limit"


@dataclass
class PolicyResult:
    ok: bool
    violations: list[str] = field(default_factory=list)
    position_size: float | None = None
    planned_r_multiple: float | None = None
    risk_pct_account: float | None = None
    position_notional: float | None = None
    stop_distance_pct: float | None = None


class PolicyGate:
    def __init__(
        self,
        *,
        account_equity: float,
        max_risk_pct: float = 0.01,
        max_daily_loss_pct: float = 0.05,
        max_weekly_loss_pct: float = 0.12,
        max_trades_per_day: int = 20,
        min_reward_risk: float = 1.5,
        max_position_notional_pct: float = 2.0,
        min_stop_distance_pct: float = 0.001,
        allow_short: bool = False,
    ) -> None:
        self.account_equity = float(account_equity)
        self.max_risk_pct = max_risk_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_weekly_loss_pct = max_weekly_loss_pct
        self.max_trades_per_day = max_trades_per_day
        self.min_reward_risk = min_reward_risk
        self.max_position_notional_pct = max_position_notional_pct
        self.min_stop_distance_pct = min_stop_distance_pct
        self.allow_short = allow_short

    def validate(
        self,
        proposal: Mapping[str, Any],
        *,
        trades_today: int = 0,
        daily_realized_loss: float = 0.0,
        weekly_realized_loss: float = 0.0,
    ) -> PolicyResult:
        violations: list[PolicyViolation] = []
        asset_class = str(proposal.get("asset_class") or "").lower()
        ticker = str(proposal.get("ticker") or "").upper()
        direction = str(proposal.get("direction") or "").lower()
        entry = _maybe_float(proposal.get("planned_entry"))
        stop = _maybe_float(proposal.get("stop"))
        target = _maybe_float(proposal.get("target"))
        risk_dollars = _maybe_float(proposal.get("risk_dollars"))

        if asset_class not in {"stock", "etf"}:
            violations.append(PolicyViolation.BANNED_ASSET)
        if _is_banned_ticker(ticker):
            violations.append(PolicyViolation.BANNED_TICKER)
        if direction not in {"long", "short"}:
            violations.append(PolicyViolation.INVALID_DIRECTION)
        if not str(proposal.get("strategy_id") or "").strip():
            violations.append(PolicyViolation.MISSING_STRATEGY)
        if direction == "short" and not self.allow_short:
            violations.append(PolicyViolation.SHORTING_DISABLED)
        if entry is None:
            violations.append(PolicyViolation.MISSING_ENTRY)
        if stop is None:
            violations.append(PolicyViolation.MISSING_STOP)
        if target is None:
            violations.append(PolicyViolation.MISSING_TARGET)
        if risk_dollars is None or risk_dollars <= 0:
            violations.append(PolicyViolation.INVALID_RISK)
        if trades_today >= self.max_trades_per_day:
            violations.append(PolicyViolation.DAILY_TRADE_LIMIT)
        if abs(daily_realized_loss) >= self.account_equity * self.max_daily_loss_pct:
            violations.append(PolicyViolation.DAILY_LOSS_LIMIT)
        if abs(weekly_realized_loss) >= self.account_equity * self.max_weekly_loss_pct:
            violations.append(PolicyViolation.WEEKLY_LOSS_LIMIT)

        planned_r = None
        position_size = None
        risk_pct = None
        position_notional = None
        stop_distance_pct = None
        if entry is not None and stop is not None and target is not None and risk_dollars and direction in {"long", "short"}:
            risk_per_share = abs(entry - stop)
            stop_distance_pct = round(risk_per_share / entry, 6) if entry else None
            reward_per_share = (target - entry) if direction == "long" else (entry - target)
            if risk_per_share <= 0 or reward_per_share <= 0:
                violations.append(PolicyViolation.REWARD_RISK_TOO_LOW)
            else:
                planned_r = round(reward_per_share / risk_per_share, 4)
                position_size = round(risk_dollars / risk_per_share, 4)
                risk_pct = round(risk_dollars / self.account_equity, 4) if self.account_equity else None
                position_notional = round(position_size * entry, 2)
                if planned_r < self.min_reward_risk:
                    violations.append(PolicyViolation.REWARD_RISK_TOO_LOW)
                if stop_distance_pct is not None and stop_distance_pct < self.min_stop_distance_pct:
                    violations.append(PolicyViolation.STOP_TOO_TIGHT)
                if position_notional > self.account_equity * self.max_position_notional_pct:
                    violations.append(PolicyViolation.POSITION_TOO_LARGE)
        if risk_dollars and risk_dollars > self.account_equity * self.max_risk_pct:
            violations.append(PolicyViolation.RISK_TOO_HIGH)

        unique = list(dict.fromkeys(v.value for v in violations))
        return PolicyResult(
            ok=not unique,
            violations=unique,
            position_size=position_size,
            planned_r_multiple=planned_r,
            risk_pct_account=risk_pct,
            position_notional=position_notional,
            stop_distance_pct=stop_distance_pct,
        )


def _maybe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_banned_ticker(ticker: str) -> bool:
    if not ticker:
        return True
    if "-USD" in ticker or "/USD" in ticker:
        return True
    if len(ticker) > 5 and ticker not in {"BRK.B", "BRK.A"}:
        return True
    return False
