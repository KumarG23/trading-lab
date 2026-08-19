import json
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_autonomous_paper_loop_honors_portfolio_admission_freeze(tmp_path):
    candidates = [
        {
            "ticker": "SPY",
            "asset_class": "etf",
            "strategy_id": "opening-range-breakout",
            "direction": "long",
            "planned_entry": 100.0,
            "stop": 99.0,
            "target": 102.0,
            "risk_dollars": 2.0,
            "rule_checklist": {"liquidity_ok": True, "spread_ok": True},
        }
    ]
    candidates_path = tmp_path / "candidates.json"
    db_path = tmp_path / "lab.db"
    candidates_path.write_text(json.dumps(candidates), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "autonomous_paper_loop.py"),
            str(candidates_path),
            "--db",
            str(db_path),
            "--no-local-ai",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["portfolio_admission_enabled"] is False
    with sqlite3.connect(db_path) as con:
        checklist = json.loads(con.execute("SELECT rule_checklist_json FROM proposals").fetchone()[0])
    assert checklist["portfolio_admitted"] is False
    assert checklist["portfolio_admission_enabled"] is False
