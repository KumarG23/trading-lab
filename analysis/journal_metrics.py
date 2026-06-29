#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.journal_store import JournalStore  # noqa: E402
from trading_lab.metrics import summarize_trades  # noqa: E402

DB_PATH = ROOT / "journal" / "trading-lab.db"

if __name__ == "__main__":
    store = JournalStore(DB_PATH)
    summary = summarize_trades(store.list_paper_trades())
    print(json.dumps(summary, indent=2, sort_keys=True))
