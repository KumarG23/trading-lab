from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from trading_lab.journal_store import JournalStore
from trading_lab.lanes import is_portfolio_admitted
from trading_lab.policy_gate import PolicyGate

ET = ZoneInfo("America/New_York")


class ProposalWorker(Protocol):
    def review(self, proposal: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class DeterministicWorker:
    """No-token fallback worker used until local model review is wired in."""

    model_used: str = "deterministic"

    def review(self, proposal: dict[str, Any]) -> dict[str, Any]:
        return {
            "approved": True,
            "thesis": proposal.get("thesis") or f"{proposal['strategy_id']} deterministic setup candidate",
            "risk_officer_objection": "none",
            "model_used": self.model_used,
        }


class AutonomousRunner:
    def __init__(
        self,
        *,
        store: JournalStore,
        worker: ProposalWorker | None = None,
        account_equity: float,
        max_risk_pct: float = 0.01,
        dedupe_minutes: int = 30,
        create_paper_positions: bool = True,
        max_reviews_per_run: int | None = None,
        max_active_positions: int | None = 2,
        max_trades_per_day: int = 50,
    ) -> None:
        self.store = store
        self.worker = worker or DeterministicWorker()
        self.gate = PolicyGate(
            account_equity=account_equity,
            max_risk_pct=max_risk_pct,
            max_trades_per_day=max_trades_per_day,
        )
        self.dedupe_minutes = dedupe_minutes
        self.create_paper_positions = create_paper_positions
        self.max_reviews_per_run = max_reviews_per_run
        self.max_active_positions = max_active_positions

    def process_candidates(self, candidates: list[dict[str, Any]]) -> list[int]:
        proposal_ids: list[int] = []
        review_attempts = 0
        strategy_counts: dict[str, int] = {}
        for proposal in self.store.list_proposals():
            strategy = str(proposal.get("strategy_id") or "unknown")
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        candidates = sorted(
            candidates,
            key=lambda candidate: (
                strategy_counts.get(str(candidate.get("strategy_id") or "unknown"), 0),
                str(candidate.get("strategy_id") or ""),
                str(candidate.get("ticker") or ""),
            ),
        )
        research_proposals_today = self._research_proposals_today()
        portfolio_trades_today, portfolio_daily_loss, portfolio_weekly_loss = self._risk_state(portfolio_only=True)
        active_slots = None
        if self.create_paper_positions and self.max_active_positions is not None:
            active_slots = max(0, self.max_active_positions - self._active_portfolio_count())
        for candidate in candidates:
            decision = self.gate.validate(
                candidate,
                trades_today=research_proposals_today,
                daily_realized_loss=0.0,
                weekly_realized_loss=0.0,
            )
            if not decision.ok:
                continue
            if self.store.recent_duplicate_proposal(
                ticker=str(candidate["ticker"]),
                strategy_id=str(candidate["strategy_id"]),
                direction=str(candidate["direction"]),
                planned_entry=_float_or_none(candidate.get("planned_entry")),
                stop=_float_or_none(candidate.get("stop")),
                target=_float_or_none(candidate.get("target")),
                within_minutes=self.dedupe_minutes,
            ):
                continue
            if self.max_reviews_per_run is not None and review_attempts >= self.max_reviews_per_run:
                review = {
                    "approved": False,
                    "thesis": "",
                    "risk_officer_objection": "",
                    "model_used": "deterministic",
                    "shadow_status": "not_reviewed_cap",
                }
            else:
                review_attempts += 1
                try:
                    review = self.worker.review(candidate)
                    review["shadow_status"] = "reviewed"
                except Exception as exc:
                    review = {
                        "approved": False,
                        "thesis": "",
                        "risk_officer_objection": f"shadow review error: {type(exc).__name__}",
                        "model_used": "deterministic",
                        "shadow_status": "error",
                    }
            checklist = dict(candidate.get("rule_checklist") or {})
            portfolio_decision = self.gate.validate(
                candidate,
                trades_today=portfolio_trades_today,
                daily_realized_loss=portfolio_daily_loss,
                weekly_realized_loss=portfolio_weekly_loss,
            )
            portfolio_admitted = (active_slots is None or active_slots > 0) and portfolio_decision.ok
            checklist.update(
                {
                    "policy_approved": True,
                    "planned_r_multiple": decision.planned_r_multiple,
                    "risk_pct_account": decision.risk_pct_account,
                    "position_size": decision.position_size,
                    "position_notional": decision.position_notional,
                    "stop_distance_pct": decision.stop_distance_pct,
                    "local_worker_reviewed": review.get("model_used") not in {None, "deterministic"},
                    "local_worker_shadow_approved": bool(review.get("approved", False)),
                    "local_worker_shadow_thesis": str(review.get("thesis") or ""),
                    "local_worker_shadow_status": str(review.get("shadow_status") or "unknown"),
                    "portfolio_admitted": portfolio_admitted,
                }
            )
            proposal_id = self.store.log_proposal(
                ticker=str(candidate["ticker"]),
                strategy_id=str(candidate["strategy_id"]),
                direction=str(candidate["direction"]),
                trigger=str(candidate.get("trigger") or "deterministic candidate"),
                planned_entry=_float_or_none(candidate.get("planned_entry")),
                stop=_float_or_none(candidate.get("stop")),
                target=_float_or_none(candidate.get("target")),
                thesis=str(candidate.get("thesis") or ""),
                rule_checklist=checklist,
                risk_officer_objection=str(review.get("risk_officer_objection") or ""),
                model_used=str(review.get("model_used") or "unknown"),
                data_sources=list(candidate.get("data_sources") or []),
            )
            if self.create_paper_positions:
                self.store.create_paper_position(
                    proposal_id=proposal_id,
                    ticker=str(candidate["ticker"]),
                    strategy_id=str(candidate["strategy_id"]),
                    direction=str(candidate["direction"]),
                    entry=float(candidate["planned_entry"]),
                    stop=float(candidate["stop"]),
                    target=float(candidate["target"]),
                    position_size=float(decision.position_size or 0.0),
                    risk_dollars=float(candidate["risk_dollars"]),
                    status="pending_entry",
                )
                if active_slots is not None and portfolio_admitted:
                    active_slots -= 1
            proposal_ids.append(proposal_id)
            research_proposals_today += 1
        return proposal_ids

    def _research_proposals_today(self) -> int:
        today = datetime.now(ET).date()
        count = 0
        for proposal in self.store.list_proposals():
            try:
                proposal_date = datetime.fromisoformat(str(proposal["created_at"])).astimezone(ET).date()
            except (TypeError, ValueError):
                continue
            if proposal_date == today:
                count += 1
        return count

    def _active_portfolio_count(self) -> int:
        proposals = {int(row["id"]): row for row in self.store.list_proposals()}
        count = 0
        for position in self.store.list_active_paper_positions():
            proposal = proposals.get(int(position["proposal_id"]), {})
            if is_portfolio_admitted(proposal, unknown_counts_as_admitted=True):
                count += 1
        return count

    def _risk_state(self, *, portfolio_only: bool = False) -> tuple[int, float, float]:
        now = datetime.now(ET)
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        trades_today = 0
        daily_loss = 0.0
        weekly_loss = 0.0
        proposals = {int(row["id"]): row for row in self.store.list_proposals()} if portfolio_only else {}
        for trade in self.store.list_paper_trades():
            if portfolio_only:
                proposal = proposals.get(int(trade["proposal_id"]), {})
                if not is_portfolio_admitted(proposal, unknown_counts_as_admitted=True):
                    continue
            try:
                trade_date = datetime.fromisoformat(str(trade["created_at"])).astimezone(ET).date()
            except (TypeError, ValueError):
                continue
            pnl = float(trade.get("pnl") or 0.0)
            if trade_date == today:
                trades_today += 1
                daily_loss += pnl
            if week_start <= trade_date <= today:
                weekly_loss += pnl
        return trades_today, min(0.0, daily_loss), min(0.0, weekly_loss)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
