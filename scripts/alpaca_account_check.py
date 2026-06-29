#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_lab.alpaca_client import AlpacaClient  # noqa: E402
from trading_lab.config import LabConfig  # noqa: E402


def main() -> int:
    cfg = LabConfig.from_env_file(ROOT / ".env")
    if not cfg.alpaca_configured:
        print(json.dumps({"alpaca_configured": False}, indent=2))
        return 2
    client = AlpacaClient(
        base_url=cfg.alpaca_base_url,
        api_key=cfg.alpaca_api_key or "",
        secret_key=cfg.alpaca_secret_key or "",
        allow_live=cfg.live_trading_enabled,
    )
    print(json.dumps({"alpaca_configured": True, "account": client.get_account_summary()}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
