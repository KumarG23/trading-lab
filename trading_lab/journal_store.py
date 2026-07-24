from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    ticker TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('long', 'short')),
    status TEXT NOT NULL DEFAULT 'proposed',
    trigger TEXT NOT NULL,
    planned_entry REAL,
    stop REAL,
    target REAL,
    thesis TEXT NOT NULL,
    risk_officer_objection TEXT,
    reason_to_skip TEXT,
    rule_checklist_json TEXT NOT NULL DEFAULT '{}',
    model_used TEXT,
    data_sources_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS candidate_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    candidate_key TEXT NOT NULL,
    ticker TEXT,
    strategy_id TEXT,
    direction TEXT,
    disposition TEXT NOT NULL,
    disposition_reason_json TEXT NOT NULL DEFAULT '{}',
    candidate_json TEXT NOT NULL,
    proposal_id INTEGER REFERENCES proposals(id) ON DELETE SET NULL,
    run_id TEXT NOT NULL DEFAULT '',
    decision_at TEXT NOT NULL DEFAULT '',
    data_cutoff_at TEXT,
    code_sha TEXT NOT NULL DEFAULT 'unknown',
    config_hash TEXT NOT NULL DEFAULT 'unknown',
    feature_schema_version TEXT NOT NULL DEFAULT '',
    strategy_version TEXT NOT NULL DEFAULT 'unknown',
    strategy_hash TEXT NOT NULL DEFAULT '',
    features_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    actual_entry REAL,
    actual_exit REAL,
    position_size REAL,
    pnl REAL,
    actual_r_multiple REAL,
    fees REAL NOT NULL DEFAULT 0.0,
    rule_adherent INTEGER NOT NULL CHECK(rule_adherent IN (0, 1)),
    mistake_category TEXT,
    exit_reason TEXT,
    postmortem TEXT
);

CREATE TABLE IF NOT EXISTS paper_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('long', 'short')),
    status TEXT NOT NULL CHECK(status IN ('pending_entry', 'open', 'closed', 'expired')),
    created_at TEXT NOT NULL,
    entered_at TEXT,
    closed_at TEXT,
    entry REAL NOT NULL,
    stop REAL NOT NULL,
    target REAL NOT NULL,
    position_size REAL NOT NULL,
    risk_dollars REAL NOT NULL,
    exit_price REAL,
    exit_reason TEXT,
    pnl REAL,
    r_multiple REAL,
    fees REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    review_type TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS model_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    task TEXT NOT NULL,
    prompt_chars INTEGER NOT NULL DEFAULT 0,
    response_chars INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
    local INTEGER NOT NULL DEFAULT 0 CHECK(local IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_proposals_created ON proposals(created_at);
CREATE INDEX IF NOT EXISTS idx_proposals_strategy ON proposals(strategy_id);
CREATE INDEX IF NOT EXISTS idx_proposals_dedupe ON proposals(ticker, strategy_id, direction, created_at);
CREATE INDEX IF NOT EXISTS idx_paper_trades_proposal ON paper_trades(proposal_id);
CREATE INDEX IF NOT EXISTS idx_paper_positions_status ON paper_positions(status, ticker);
CREATE INDEX IF NOT EXISTS idx_model_usage_created ON model_usage(created_at);
CREATE INDEX IF NOT EXISTS idx_candidate_events_key ON candidate_events(candidate_key);
CREATE INDEX IF NOT EXISTS idx_candidate_events_disposition ON candidate_events(disposition, created_at);
"""


def now_et() -> str:
    return datetime.now(ET).isoformat(timespec="seconds")


def init_db(path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        _ensure_column(conn, "paper_trades", "fees", "REAL NOT NULL DEFAULT 0.0")
        _ensure_column(conn, "paper_positions", "fees", "REAL NOT NULL DEFAULT 0.0")
        _ensure_column(conn, "candidate_events", "proposal_id", "INTEGER REFERENCES proposals(id) ON DELETE SET NULL")
        for column, definition in {
            "run_id": "TEXT NOT NULL DEFAULT ''",
            "decision_at": "TEXT NOT NULL DEFAULT ''",
            "data_cutoff_at": "TEXT",
            "code_sha": "TEXT NOT NULL DEFAULT 'unknown'",
            "config_hash": "TEXT NOT NULL DEFAULT 'unknown'",
            "feature_schema_version": "TEXT NOT NULL DEFAULT ''",
            "strategy_version": "TEXT NOT NULL DEFAULT 'unknown'",
            "strategy_hash": "TEXT NOT NULL DEFAULT ''",
            "features_json": "TEXT NOT NULL DEFAULT '{}'",
        }.items():
            _ensure_column(conn, "candidate_events", column, definition)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


class JournalStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        init_db(self.db_path)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def log_proposal(
        self,
        *,
        ticker: str,
        strategy_id: str,
        direction: str,
        trigger: str,
        planned_entry: float | None,
        stop: float | None,
        target: float | None,
        thesis: str,
        rule_checklist: dict[str, Any] | None = None,
        status: str = "proposed",
        risk_officer_objection: str | None = None,
        reason_to_skip: str | None = None,
        model_used: str | None = None,
        data_sources: list[str] | None = None,
        candidate_event: dict[str, Any] | None = None,
        candidate_disposition: str | None = None,
        candidate_disposition_reason: dict[str, Any] | None = None,
        candidate_provenance: dict[str, Any] | None = None,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO proposals (
                    created_at, ticker, strategy_id, direction, status, trigger,
                    planned_entry, stop, target, thesis, risk_officer_objection,
                    reason_to_skip, rule_checklist_json, model_used, data_sources_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_et(), ticker.upper(), strategy_id, direction, status, trigger,
                    planned_entry, stop, target, thesis, risk_officer_objection,
                    reason_to_skip, json.dumps(rule_checklist or {}, sort_keys=True),
                    model_used, json.dumps(data_sources or [], sort_keys=True),
                ),
            )
            proposal_id = int(cur.lastrowid)
            if candidate_event is not None and candidate_disposition is not None:
                _insert_candidate_event(
                    conn,
                    candidate_event,
                    disposition=candidate_disposition,
                    disposition_reason=candidate_disposition_reason,
                    proposal_id=proposal_id,
                    provenance=candidate_provenance,
                )
            return proposal_id

    def log_candidate_event(
        self,
        candidate: dict[str, Any],
        *,
        disposition: str,
        disposition_reason: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> int:
        with self._conn() as conn:
            return _insert_candidate_event(
                conn,
                candidate,
                disposition=disposition,
                disposition_reason=disposition_reason,
                proposal_id=None,
                provenance=provenance,
            )

    def list_candidate_events(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM candidate_events ORDER BY id").fetchall()
        return [_decode(row) for row in rows]

    def recent_duplicate_proposal(
        self,
        *,
        ticker: str,
        strategy_id: str,
        direction: str,
        planned_entry: float | None,
        stop: float | None,
        target: float | None,
        within_minutes: int = 390,
    ) -> dict[str, Any] | None:
        cutoff = (datetime.now(ET) - timedelta(minutes=within_minutes)).isoformat(timespec="seconds")
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM proposals
                WHERE ticker = ? AND strategy_id = ? AND direction = ? AND created_at >= ?
                  AND status NOT LIKE 'dry_run%'
                ORDER BY id DESC
                LIMIT 1
                """,
                (ticker.upper(), strategy_id, direction, cutoff),
            ).fetchone()
        if row is None:
            return None
        proposal = _decode(row)
        if _close_enough(proposal.get("planned_entry"), planned_entry) and _close_enough(proposal.get("stop"), stop) and _close_enough(proposal.get("target"), target):
            return proposal
        return None

    def log_paper_trade(
        self,
        *,
        proposal_id: int,
        actual_entry: float | None,
        actual_exit: float | None,
        position_size: float | None,
        pnl: float | None,
        actual_r_multiple: float | None,
        rule_adherent: bool,
        fees: float = 0.0,
        mistake_category: str | None = None,
        exit_reason: str | None = None,
        postmortem: str | None = None,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO paper_trades (
                    proposal_id, created_at, actual_entry, actual_exit, position_size,
                    pnl, actual_r_multiple, fees, rule_adherent, mistake_category, exit_reason, postmortem
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id, now_et(), actual_entry, actual_exit, position_size,
                    pnl, actual_r_multiple, fees, int(rule_adherent), mistake_category, exit_reason, postmortem,
                ),
            )
            return int(cur.lastrowid)

    def create_paper_position(
        self,
        *,
        proposal_id: int,
        ticker: str,
        strategy_id: str,
        direction: str,
        entry: float,
        stop: float,
        target: float,
        position_size: float,
        risk_dollars: float,
        status: str = "pending_entry",
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO paper_positions (
                    proposal_id, ticker, strategy_id, direction, status, created_at,
                    entry, stop, target, position_size, risk_dollars
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id, ticker.upper(), strategy_id, direction, status, now_et(),
                    entry, stop, target, position_size, risk_dollars,
                ),
            )
            return int(cur.lastrowid)

    def list_active_paper_positions(self, *, include_quarantined: bool = False) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if include_quarantined:
                rows = conn.execute(
                    "SELECT pp.* FROM paper_positions pp WHERE pp.status IN ('pending_entry', 'open') ORDER BY pp.id"
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT pp.* FROM paper_positions pp
                    JOIN proposals p ON p.id = pp.proposal_id
                    WHERE pp.status IN ('pending_entry', 'open')
                      AND p.status NOT LIKE '%quarantined%'
                    ORDER BY pp.id
                    """
                ).fetchall()
        return [_decode(row) for row in rows]

    def list_paper_positions(self, *, include_quarantined: bool = False) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if include_quarantined:
                rows = conn.execute("SELECT * FROM paper_positions ORDER BY id").fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT pp.* FROM paper_positions pp
                    JOIN proposals p ON p.id = pp.proposal_id
                    WHERE p.status NOT LIKE '%quarantined%'
                    ORDER BY pp.id
                    """
                ).fetchall()
        return [_decode(row) for row in rows]

    def mark_position_open(self, position_id: int, *, entered_at: str, entry_price: float | None = None) -> None:
        with self._conn() as conn:
            if entry_price is None:
                conn.execute(
                    "UPDATE paper_positions SET status = 'open', entered_at = ? WHERE id = ?",
                    (entered_at, position_id),
                )
            else:
                conn.execute(
                    "UPDATE paper_positions SET status = 'open', entered_at = ?, entry = ? WHERE id = ?",
                    (entered_at, entry_price, position_id),
                )

    def close_position(
        self,
        position_id: int,
        *,
        closed_at: str,
        exit_price: float,
        exit_reason: str,
        rule_adherent: bool = True,
        fees: float = 0.0,
    ) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM paper_positions WHERE id = ?", (position_id,)).fetchone()
            if row is None:
                raise ValueError(f"unknown paper position id: {position_id}")
            pos = dict(row)
            direction = pos["direction"]
            entry = float(pos["entry"])
            size = float(pos["position_size"])
            if direction == "long":
                pnl = (exit_price - entry) * size - fees
            else:
                pnl = (entry - exit_price) * size - fees
            planned_risk_dollars = float(pos["risk_dollars"])
            r_multiple = pnl / planned_risk_dollars if planned_risk_dollars else 0.0
            conn.execute(
                """
                UPDATE paper_positions
                SET status = 'closed', closed_at = ?, exit_price = ?, exit_reason = ?, pnl = ?, r_multiple = ?, fees = ?
                WHERE id = ?
                """,
                (closed_at, exit_price, exit_reason, round(pnl, 4), round(r_multiple, 4), round(fees, 4), position_id),
            )
            cur = conn.execute(
                """
                INSERT INTO paper_trades (
                    proposal_id, created_at, actual_entry, actual_exit, position_size,
                    pnl, actual_r_multiple, fees, rule_adherent, mistake_category, exit_reason, postmortem
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pos["proposal_id"], now_et(), entry, exit_price, size, round(pnl, 4),
                    round(r_multiple, 4), round(fees, 4), int(rule_adherent), None, exit_reason,
                    f"simulated paper close via {exit_reason}",
                ),
            )
            return int(cur.lastrowid)

    def expire_position(self, position_id: int, *, closed_at: str, reason: str = "expired_without_entry") -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE paper_positions SET status = 'expired', closed_at = ?, exit_reason = ? WHERE id = ?",
                (closed_at, reason, position_id),
            )

    def list_proposals(self, *, include_quarantined: bool = False) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if include_quarantined:
                rows = conn.execute("SELECT * FROM proposals ORDER BY id").fetchall()
            else:
                rows = conn.execute("SELECT * FROM proposals WHERE status NOT LIKE '%quarantined%' ORDER BY id").fetchall()
        return [_decode(row) for row in rows]

    def list_paper_trades(self, *, include_quarantined: bool = False) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if include_quarantined:
                rows = conn.execute("SELECT * FROM paper_trades ORDER BY id").fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT pt.* FROM paper_trades pt
                    JOIN proposals p ON p.id = pt.proposal_id
                    WHERE p.status NOT LIKE '%quarantined%'
                      AND COALESCE(pt.mistake_category, '') NOT LIKE '%quarantined%'
                    ORDER BY pt.id
                    """
                ).fetchall()
        return [_decode(row) for row in rows]


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    if "rule_checklist_json" in data:
        data["rule_checklist"] = json.loads(data.pop("rule_checklist_json") or "{}")
    if "data_sources_json" in data:
        data["data_sources"] = json.loads(data.pop("data_sources_json") or "[]")
    if "disposition_reason_json" in data:
        data["disposition_reason"] = json.loads(data.pop("disposition_reason_json") or "{}")
    if "candidate_json" in data:
        data["candidate"] = json.loads(data.pop("candidate_json") or "{}")
    if "features_json" in data:
        data["features"] = json.loads(data.pop("features_json") or "{}")
    if "rule_adherent" in data:
        data["rule_adherent"] = bool(data["rule_adherent"])
    return data


def _close_enough(a: Any, b: Any, tolerance: float = 0.0025) -> bool:
    if a is None or b is None:
        return a is b
    try:
        af = float(a)
        bf = float(b)
    except (TypeError, ValueError):
        return False
    if af == bf:
        return True
    return abs(af - bf) / max(abs(af), 1.0) <= tolerance


def _text_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _insert_candidate_event(
    conn: sqlite3.Connection,
    candidate: dict[str, Any],
    *,
    disposition: str,
    disposition_reason: dict[str, Any] | None,
    proposal_id: int | None,
    provenance: dict[str, Any] | None,
) -> int:
    normalized = _json_safe(candidate)
    candidate_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)
    candidate_key = hashlib.sha256(candidate_json.encode("utf-8")).hexdigest()
    provenance = provenance or {}
    cur = conn.execute(
        """
        INSERT INTO candidate_events (
            created_at, candidate_key, ticker, strategy_id, direction,
            disposition, disposition_reason_json, candidate_json, proposal_id,
            run_id, decision_at, data_cutoff_at, code_sha, config_hash,
            feature_schema_version, strategy_version, strategy_hash, features_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_et(), candidate_key, _text_or_none(candidate.get("ticker")),
            _text_or_none(candidate.get("strategy_id")), _text_or_none(candidate.get("direction")),
            disposition, json.dumps(_json_safe(disposition_reason or {}), sort_keys=True, allow_nan=False),
            candidate_json, proposal_id, str(provenance.get("run_id") or ""),
            str(provenance.get("decision_at") or ""), _text_or_none(provenance.get("data_cutoff_at")),
            str(provenance.get("code_sha") or "unknown"), str(provenance.get("config_hash") or "unknown"),
            str(provenance.get("feature_schema_version") or ""), str(provenance.get("strategy_version") or "unknown"),
            str(provenance.get("strategy_hash") or ""),
            json.dumps(_json_safe(provenance.get("features") or {}), sort_keys=True, allow_nan=False),
        ),
    )
    if cur.lastrowid is None:
        raise RuntimeError("candidate event insert did not return an id")
    return int(cur.lastrowid)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else f"<non-finite:{value}>"
    if isinstance(value, dict):
        string_items = {key: _json_safe(item) for key, item in value.items() if isinstance(key, str)}
        other_items = [
            {
                "type": f"{type(key).__module__}.{type(key).__qualname__}",
                "key": _json_safe(key),
                "value": _json_safe(item),
            }
            for key, item in value.items()
            if not isinstance(key, str)
        ]
        result = {key: string_items[key] for key in sorted(string_items)}
        if other_items:
            special_key = "__non_string_keys__"
            while special_key in result:
                special_key = f"_{special_key}"
            result[special_key] = sorted(
                other_items,
                key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False),
            )
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_json_safe(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    return f"<{type(value).__module__}.{type(value).__qualname__}>"
