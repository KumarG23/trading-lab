import os
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from scripts import scan_universe as scanner
from scripts import trading_lab_progress_report as report
from trading_lab.journal_store import SCHEMA

ET = ZoneInfo("America/New_York")


@pytest.mark.parametrize("name", ["trading_lab_daily_close_summary.sh", "trading_lab_progress_report.sh", "trading_lab_universe_scan.sh"])
def test_cron_wrappers_use_project_calendar_environment(name):
    wrapper = Path(__file__).resolve().parents[1] / "scripts" / "cron" / name
    assert "exec .venv/bin/python scripts/" in wrapper.read_text()


@pytest.mark.parametrize("day", ["2026-09-08", "2026-11-27", "2026-03-09"])
def test_premarket_scanner_does_not_skip_valid_sessions(monkeypatch, tmp_path, capsys, day):
    freeze_clock(monkeypatch, scanner, datetime.fromisoformat(day + "T09:05:00").replace(tzinfo=ET))
    monkeypatch.setattr("sys.argv", ["scanner", "--output", str(tmp_path / "out.json")])
    monkeypatch.setattr(scanner.LabConfig, "from_env_file", lambda path: SimpleNamespace(alpaca_configured=False))
    assert scanner.main() == 2
    assert "alpaca_not_configured" in capsys.readouterr().out


@pytest.mark.parametrize("day,last_scan,healthy", [
    ("2026-11-27", "12:59", True),
    ("2026-11-27", "12:40", False),
    ("2026-09-08", "15:59", True),
    ("2026-09-08", "15:40", False),
    ("2026-09-08", "17:00", False),
])
def test_close_report_health_uses_actual_session_close(monkeypatch, tmp_path, capsys, day, last_scan, healthy):
    now = datetime.fromisoformat(day + "T16:05:00").replace(tzinfo=ET)
    freeze_clock(monkeypatch, report, now)
    db = tmp_path / "journal.db"
    with sqlite3.connect(db) as con:
        con.executescript(SCHEMA)
    runtime = tmp_path / "runtime.json"
    runtime.write_text('{"ok": true, "broker_orders": 0}')
    stamp = datetime.fromisoformat(day + "T" + last_scan).replace(tzinfo=ET).timestamp()
    os.utime(runtime, (stamp, stamp))
    monkeypatch.setattr(report, "DB", db)
    monkeypatch.setattr(report, "RUNTIME", runtime)
    monkeypatch.setattr(report, "SCANNER", tmp_path / "missing-scanner.json")
    monkeypatch.setattr("sys.argv", ["report", "--succinct"])
    assert report.main() == 0
    text = capsys.readouterr().out
    assert ("Health: OK" in text) is healthy
    assert ("Health: ERROR" in text) is not healthy


@pytest.mark.parametrize("instant", ["2026-09-07T09:05:00-04:00", "2026-07-03T09:05:00-04:00", "2026-09-08T00:05:00+00:00"])
def test_closed_session_scanner_skips_before_config_or_output(monkeypatch, tmp_path, capsys, instant):
    freeze_clock(monkeypatch, scanner, datetime.fromisoformat(instant))
    output = tmp_path / "watchlist.json"
    output.write_text("previous watchlist")
    monkeypatch.setattr("sys.argv", ["scanner", "--output", str(output)])

    def forbidden(*args, **kwargs):
        pytest.fail("closed-session scanner must not read config or fetch data")

    monkeypatch.setattr(scanner.LabConfig, "from_env_file", forbidden)
    assert scanner.main() == 0
    assert '"skipped": "market_closed"' in capsys.readouterr().out
    assert output.read_text() == "previous watchlist"

def freeze_clock(monkeypatch, module, instant):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)

    monkeypatch.setattr(module, "datetime", Clock)


@pytest.mark.parametrize("day", ["2026-09-07", "2027-09-06", "2026-07-03", "2026-11-26", "2026-09-05"])
@pytest.mark.parametrize("succinct", [False, True])
def test_closed_session_report_skips_metrics_and_health(monkeypatch, tmp_path, capsys, day, succinct):
    freeze_clock(monkeypatch, report, datetime.fromisoformat(day + "T16:05:00").replace(tzinfo=ET))
    monkeypatch.setattr(report, "DB", tmp_path / "absent.db")
    monkeypatch.setattr("sys.argv", ["report"] + (["--succinct"] if succinct else []))

    assert report.main() == 0
    text = capsys.readouterr().out
    assert f"Market closed — {day}" in text
    assert "No trading session" in text
    assert "scanner failure" in text
    assert "PnL" not in text
    assert "Health: ERROR" not in text
    assert not (tmp_path / "absent.db").exists()
