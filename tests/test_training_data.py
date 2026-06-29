import sqlite3

from trading_lab.training_data import export_claude_bot_examples


def test_export_claude_bot_examples_sanitizes_and_labels_hold_heavy_data(tmp_path):
    source = tmp_path / "old.db"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY,
            created_at TEXT,
            symbol TEXT,
            asset_class TEXT,
            action TEXT,
            confidence REAL,
            reasoning TEXT,
            outcome TEXT,
            pnl_pct REAL,
            strategy_used TEXT,
            session_type TEXT,
            full_prompt TEXT,
            full_response TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO decisions VALUES (1,'2026-04-01T10:00:00Z','AAPL','stock','hold',0.51,'No confirmation yet','none',0,'opening_range','open','SECRET PROMPT','SECRET RESPONSE')"
    )
    conn.execute(
        "INSERT INTO decisions VALUES (2,'2026-04-01T10:05:00Z','MSFT','stock','buy',0.72,'VWAP reclaim with volume','win',0.02,'vwap','open','SECRET PROMPT','SECRET RESPONSE')"
    )
    conn.commit()
    conn.close()

    out = tmp_path / "examples.jsonl"
    count = export_claude_bot_examples(source, out, limit=10)

    lines = out.read_text().strip().splitlines()
    assert count == 2
    assert len(lines) == 2
    assert "SECRET" not in out.read_text()
    assert '"symbol": "AAPL"' in lines[0]
    assert '"lesson_label": "hold_filter"' in lines[0]
    assert '"lesson_label": "candidate_setup"' in lines[1]
