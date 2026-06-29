from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def export_claude_bot_examples(source_db: str | Path, output_jsonl: str | Path, *, limit: int = 5000) -> int:
    """Export sanitized decision examples from the old Claude_Bot DB.

    This intentionally excludes `full_prompt` and `full_response`. The old bot's raw prompts
    were huge and may contain account context. We keep compact labels useful for local model
    review calibration: hold filters vs candidate setups, confidence, outcome, and reasoning.
    """
    source_db = Path(source_db)
    output_jsonl = Path(output_jsonl)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(source_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT created_at, symbol, asset_class, action, confidence, reasoning,
               outcome, pnl_pct, strategy_used, session_type
        FROM decisions
        ORDER BY created_at
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()

    with output_jsonl.open("w", encoding="utf-8") as handle:
        for row in rows:
            example = _row_to_example(dict(row))
            handle.write(json.dumps(example, sort_keys=True) + "\n")
    return len(rows)


def _row_to_example(row: dict[str, Any]) -> dict[str, Any]:
    action = str(row.get("action") or "").lower()
    confidence = _num(row.get("confidence"))
    outcome = row.get("outcome")
    pnl_pct = _num(row.get("pnl_pct")) if row.get("pnl_pct") is not None else None
    return {
        "source": "claude_bot_prior_art",
        "created_at": row.get("created_at"),
        "symbol": row.get("symbol"),
        "asset_class": row.get("asset_class"),
        "action": action,
        "confidence": confidence,
        "strategy_used": row.get("strategy_used") or "unknown",
        "session_type": row.get("session_type") or "unknown",
        "outcome": outcome,
        "pnl_pct": pnl_pct,
        "reasoning_summary": _clean_reasoning(row.get("reasoning") or ""),
        "lesson_label": _lesson_label(action, confidence, outcome, pnl_pct),
    }


def _lesson_label(action: str, confidence: float, outcome: Any, pnl_pct: float | None) -> str:
    if action == "hold":
        return "hold_filter"
    if outcome == "win" or (pnl_pct is not None and pnl_pct > 0):
        return "candidate_setup"
    if outcome == "loss" or (pnl_pct is not None and pnl_pct < 0):
        return "avoid_or_repair"
    if confidence >= 0.65:
        return "candidate_setup"
    return "uncertain"


def _clean_reasoning(text: str) -> str:
    return " ".join(text.split())[:500]


def _num(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0
