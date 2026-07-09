from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from trading_lab.journal_store import JournalStore
from trading_lab.policy_gate import PolicyGate


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
        dedupe_minutes: int = 390,
        create_paper_positions: bool = True,
        max_reviews_per_run: int | None = None,
        max_active_positions: int | None = 2,
    ) -> None:
        self.store = store
        self.worker = worker or DeterministicWorker()
        self.gate = PolicyGate(account_equity=account_equity, max_risk_pct=max_risk_pct)
        self.dedupe_minutes = dedupe_minutes
        self.create_paper_positions = create_paper_positions
        self.max_reviews_per_run = max_reviews_per_run
        self.max_active_positions = max_active_positions

    def process_candidates(self, candidates: list[dict[str, Any]]) -> list[int]:
        proposal_ids: list[int] = []
        review_attempts = 0
        active_slots = None
        if self.create_paper_positions and self.max_active_positions is not None:
            active_slots = max(0, self.max_active_positions - len(self.store.list_active_paper_positions()))
        for candidate in candidates:
            decision = self.gate.validate(candidate)
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
            if active_slots is not None and active_slots <= 0:
                break
            if self.max_reviews_per_run is not None and review_attempts >= self.max_reviews_per_run:
                break
            review_attempts += 1
            review = self.worker.review(candidate)
            if not review.get("approved", False):
                continue
            checklist = dict(candidate.get("rule_checklist") or {})
            checklist.update(
                {
                    "policy_approved": True,
                    "planned_r_multiple": decision.planned_r_multiple,
                    "risk_pct_account": decision.risk_pct_account,
                    "position_size": decision.position_size,
                    "position_notional": decision.position_notional,
                    "stop_distance_pct": decision.stop_distance_pct,
                    "local_worker_reviewed": review.get("model_used") not in {None, "deterministic"},
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
                thesis=str(review.get("thesis") or candidate.get("thesis") or ""),
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
                if active_slots is not None:
                    active_slots -= 1
            proposal_ids.append(proposal_id)
        return proposal_ids


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
