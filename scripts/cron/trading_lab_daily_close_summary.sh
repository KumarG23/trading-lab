#!/usr/bin/env bash
set -euo pipefail
cd /home/neal/trading-lab
exec .venv/bin/python scripts/trading_lab_progress_report.py --succinct
