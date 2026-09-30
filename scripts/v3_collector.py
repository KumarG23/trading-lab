"""Monitored, read-only V3 source acquisition. Never calls broker order endpoints."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from trading_lab.v3_news_history import instant, load_snapshots

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/events/collector"
SNAPSHOTS = ROOT / "data/events/news-snapshots"
SEC_CONTACT = Path.home() / ".config/trading-lab/sec-contact"
COMMANDS = {"news": "--capture-news", "sec": "--sec-eligible", "market": "--capture-market"}
MAX_AGE = {"news": timedelta(minutes=20), "sec": timedelta(minutes=90), "market": timedelta(minutes=20)}

# Only exact, reviewed diagnostic fragments may leave the source subprocess.
# Never store provider error text, URLs, article text, or response bodies.
SAFE_FAILURES = {"SEC acceptance clocks disagree": "sec_clock_mismatch",
                 "SEC document exceeds size limit": "sec_document_too_large",
                 "SEC source scan capacity exceeded": "sec_scan_cap",
                 "HTTP Error 429": "provider_rate_limited",
                 "HTTP Error 403": "provider_forbidden",
                 "news capture gap exceeds": "news_coverage_gap"}

def failure_code(stderr: str) -> str:
    return next((code for fragment, code in SAFE_FAILURES.items() if fragment in stderr), "source_command_failed")


def run_source(source: str, *, state: Path = STATE, executable: str = sys.executable,
               invoke=None, now=None) -> dict:
    """Serialize each source, persist sanitized attempt receipts, propagate failure."""
    if source not in COMMANDS:
        raise ValueError("unknown collector source")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state, 0o700)
    with (state / (source + ".lock")).open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("collector already running") from None
        began = (now or (lambda: datetime.now(timezone.utc)))()
        command = [executable, "-m", "scripts.v3_source_probe", COMMANDS[source]]
        receipt = {"schema": "v3-collector-receipt-v1", "source": source,
                   "started_at": began.astimezone(timezone.utc).isoformat(), "status": "failure"}
        try:
            env = os.environ.copy()
            if source == "sec":
                if SEC_CONTACT.stat().st_mode & 0o077:
                    raise ValueError("SEC contact file permissions are too broad")
                env["SEC_CONTACT_EMAIL"] = SEC_CONTACT.read_text(encoding="utf-8").strip()
            proc = (invoke or subprocess.run)(command, cwd=ROOT, capture_output=True, text=True,
                                               env=env, timeout=240 if source == "sec" else 60, check=False)
            if proc.returncode != 0:
                # Never persist stdout/stderr: external errors may contain credentials or article text.
                receipt["error_code"] = failure_code(proc.stderr or "")
                raise RuntimeError(f"source command failed (exit {proc.returncode})")
            result = json.loads(proc.stdout)
            report = result[{"news": "capture_news", "sec": "sec", "market": "capture_market"}[source]]
            if source == "news":
                if not isinstance(report["articles"], int) or report["articles"] < 0:
                    raise ValueError("invalid news count")
                receipt["articles"] = report["articles"]
                receipt["snapshot"] = Path(report["snapshot"]).name
            elif source == "market":
                if (report.get("feed") != "iex" or report.get("symbols_expected") != 46
                        or type(report.get("quotes_present")) is not int
                        or not 0 < report["quotes_present"] <= 46
                        or type(report.get("quotes_usable_for_spread")) is not int):
                    raise ValueError("incomplete market observation")
                receipt["quotes_present"] = report["quotes_present"]
                receipt["quotes_usable_for_spread"] = report["quotes_usable_for_spread"]
                receipt["quotes_unpriced"] = report["quotes_unpriced"]
                receipt["snapshot"] = Path(report["snapshot"]).name
            else:
                coverage = report["coverage"]
                if (report.get("issuers_checked") != 44 or not isinstance(report.get("appended"), int)
                        or any(type(coverage.get(key)) is not int or coverage[key] < 0 for key in
                               ("item_202_recent", "without_single_exhibit", "skipped_cap", "matched"))
                        or coverage["skipped_cap"] != 0 or coverage["matched"] < report["appended"]):
                    raise ValueError("incomplete SEC sweep")
                receipt["issuers_checked"] = report["issuers_checked"]
                receipt["events_appended"] = report["appended"]
                receipt["coverage"] = coverage
            receipt["status"] = "ok"
        except (subprocess.TimeoutExpired, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError, RuntimeError) as exc:
            # Deliberately record a bounded class, not error text from upstream providers.
            receipt["error_type"] = type(exc).__name__
        receipt["finished_at"] = (now or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc).isoformat()
        path = state / (source + ".jsonl")
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(json.dumps(receipt, sort_keys=True) + "\n")
            output.flush()
            os.fsync(output.fileno())
        return receipt


def health(*, state: Path = STATE, snapshots: Path = SNAPSHOTS, at=None) -> dict:
    """Return explicit last-run and continuity status; never mistake no articles for failure."""
    now = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local = now.astimezone(ZoneInfo("America/New_York"))
    market_window = local.weekday() < 5 and 4 <= local.hour < 20
    results = {}
    for source in COMMANDS:
        path = state / (source + ".jsonl")
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        last = rows[-1] if rows else None
        good = [row for row in rows if row.get("status") == "ok"]
        last_good = good[-1] if good else None
        fresh = bool(last_good and timedelta(0) <= now - instant(last_good["finished_at"]) <= MAX_AGE[source])
        results[source] = {"healthy": bool(fresh and last and last["status"] == "ok"),
                           "last_status": last["status"] if last else "missing",
                           "last_success_at": last_good["finished_at"] if last_good else None,
                           "failures": sum(row.get("status") != "ok" for row in rows)}
        if last and last["status"] != "ok":
            code = last.get("error_code")
            results[source]["last_error_code"] = code if code in {*SAFE_FAILURES.values(), "source_command_failed"} else "unknown_failure"
        if source == "market":
            results[source]["expected_now"] = market_window
            if not market_window:
                results[source]["healthy"] = True
    if results["news"]["healthy"]:
        try:
            records = load_snapshots(snapshots, latest_only=True)
            end = max((instant(row["window_end"]) for row in records), default=None)
            results["news"]["healthy"] = bool(end and timedelta(0) <= now - end <= MAX_AGE["news"])
            results["news"]["last_window_end"] = end.isoformat() if end else None
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
            results["news"]["healthy"] = False
            results["news"]["last_window_end"] = None
    return {"healthy": all(row["healthy"] for row in results.values()), "sources": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["news", "sec", "market", "health"])
    args = parser.parse_args()
    if args.action == "health":
        status = health()
        print(json.dumps(status, sort_keys=True))
        return 0 if status["healthy"] else 1
    receipt = run_source(args.action)
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
