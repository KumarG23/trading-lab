#!/usr/bin/env bash
set -euo pipefail
cd /home/neal/trading-lab
exec .venv/bin/python scripts/scan_universe.py --days 6 --max-symbols 30
