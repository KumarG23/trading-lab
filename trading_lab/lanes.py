from __future__ import annotations

from typing import Any, Mapping


def is_portfolio_admitted(
    proposal: Mapping[str, Any] | None,
    *,
    unknown_counts_as_admitted: bool = False,
) -> bool:
    """Resolve portfolio admission with an explicit unknown-row policy.

    Rows created before lane attribution existed are research evidence, not
    proof that the constrained portfolio would have admitted them. Reporting
    therefore defaults unknown rows to research-only. Risk and slot accounting
    can opt into the conservative opposite so legacy state never weakens a
    breaker or silently frees capacity.
    """
    if not proposal:
        return unknown_counts_as_admitted
    checklist = proposal.get("rule_checklist") or {}
    marker = checklist.get("portfolio_admitted")
    if marker is None:
        return unknown_counts_as_admitted
    return marker is True