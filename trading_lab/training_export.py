from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "trading-lab-proposal-outcome-v2"


def export_training_examples(db_path: str | Path, output_path: str | Path, *, include_unclosed: bool = True) -> dict[str, Any]:
    """Export compact proposal/outcome research provenance.

    This is deliberately a derived artifact. The SQLite journal remains canonical;
    this JSONL can be regenerated after quarantines, metric fixes, or schema tweaks.
    Single-trade outcomes are not predictive-fitness labels or SFT approval.
    """
    db_path = Path(db_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = _load_rows(db_path, include_unclosed=include_unclosed)
    examples = [_example(row) for row in rows]
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(example, sort_keys=True, separators=(",", ":")) + "\n" for example in examples), encoding="utf-8")
    tmp.replace(output_path)

    counts: dict[str, int] = {}
    for example in examples:
        label = str(example["label"])
        counts[label] = counts.get(label, 0) + 1
    return {
        "ok": True,
        "path": str(output_path),
        "examples": len(examples),
        "labels": dict(sorted(counts.items())),
    }


def _load_rows(db_path: Path, *, include_unclosed: bool) -> list[sqlite3.Row]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    where_unclosed = "" if include_unclosed else "AND pt.id IS NOT NULL"
    try:
        return list(
            con.execute(
                f"""
                SELECT
                    p.id AS proposal_id,
                    p.created_at AS proposal_created_at,
                    p.ticker,
                    p.strategy_id,
                    p.direction,
                    p.status AS proposal_status,
                    p.trigger,
                    p.planned_entry,
                    p.stop,
                    p.target,
                    p.thesis,
                    p.risk_officer_objection,
                    p.rule_checklist_json,
                    p.model_used,
                    pp.id AS position_id,
                    pp.status AS position_status,
                    pp.created_at AS position_created_at,
                    pp.entered_at,
                    pp.closed_at,
                    pp.position_size,
                    pp.risk_dollars,
                    pp.exit_price AS position_exit_price,
                    pp.exit_reason AS position_exit_reason,
                    pp.pnl AS position_pnl,
                    pp.r_multiple AS position_r_multiple,
                    pt.id AS trade_id,
                    pt.created_at AS trade_created_at,
                    pt.actual_entry,
                    pt.actual_exit,
                    pt.pnl AS trade_pnl,
                    pt.actual_r_multiple,
                    pt.rule_adherent,
                    pt.mistake_category,
                    pt.exit_reason AS trade_exit_reason,
                    pt.postmortem
                FROM proposals p
                LEFT JOIN paper_positions pp ON pp.proposal_id = p.id
                LEFT JOIN paper_trades pt ON pt.proposal_id = p.id
                WHERE p.status NOT LIKE '%quarantined%'
                  AND COALESCE(pt.mistake_category, '') NOT LIKE '%quarantined%'
                  {where_unclosed}
                ORDER BY p.id
                """
            )
        )
    finally:
        con.close()


def _example(row: sqlite3.Row) -> dict[str, Any]:
    rule_checklist = json.loads(row["rule_checklist_json"] or "{}")
    outcome = _outcome(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "example_id": f"proposal-{row['proposal_id']}",
        "label": outcome["label"],
        "artifact_purpose": "research_provenance",
        "usable_for_sft": False,
        "usable_for_predictive_training": False,
        "proposal": {
            "ticker": row["ticker"],
            "strategy_id": row["strategy_id"],
            "direction": row["direction"],
            "trigger": row["trigger"],
            "planned_entry": row["planned_entry"],
            "stop": row["stop"],
            "target": row["target"],
            "risk_dollars": row["risk_dollars"],
            "position_size": row["position_size"],
            "model_used": row["model_used"],
            "thesis": row["thesis"],
            "risk_officer_objection": row["risk_officer_objection"] or "",
            "rule_checklist": rule_checklist,
        },
        "outcome": outcome,
        "timestamps": {
            "proposal_created_at": row["proposal_created_at"],
            "entered_at": row["entered_at"],
            "closed_at": row["closed_at"],
            "trade_created_at": row["trade_created_at"],
        },
    }


def _outcome(row: sqlite3.Row) -> dict[str, Any]:
    exit_reason = row["trade_exit_reason"] or row["position_exit_reason"]
    pnl = row["trade_pnl"] if row["trade_pnl"] is not None else row["position_pnl"]
    r_multiple = row["actual_r_multiple"] if row["actual_r_multiple"] is not None else row["position_r_multiple"]
    closed = row["trade_id"] is not None or row["position_status"] == "closed"
    label = _label(position_status=row["position_status"], exit_reason=exit_reason, r_multiple=r_multiple, closed=closed)
    return {
        "label": label,
        "closed": closed,
        "position_status": row["position_status"],
        "exit_reason": exit_reason,
        "actual_entry": row["actual_entry"],
        "actual_exit": row["actual_exit"] or row["position_exit_price"],
        "pnl": pnl,
        "r_multiple": r_multiple,
        "rule_adherent": bool(row["rule_adherent"]) if row["rule_adherent"] is not None else None,
        "mistake_category": row["mistake_category"],
        "postmortem": row["postmortem"],
    }


def _label(*, position_status: str | None, exit_reason: str | None, r_multiple: float | None, closed: bool) -> str:
    if not closed:
        return position_status or "proposal_only"
    if exit_reason == "target" or (r_multiple is not None and float(r_multiple) > 0):
        return "win"
    if exit_reason == "stop" or (r_multiple is not None and float(r_multiple) < 0):
        return "loss"
    if exit_reason:
        return str(exit_reason)
    return "closed"
