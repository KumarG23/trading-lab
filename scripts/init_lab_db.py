#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.journal_store import init_db  # noqa: E402

DB_PATH = ROOT / "journal" / "trading-lab.db"

if __name__ == "__main__":
    init_db(DB_PATH)
    print(f"initialized {DB_PATH}")
