"""No-agent Discord alert for V3 collector failure/recovery; no article or credential data."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("/home/neal/trading-lab")
STATE = ROOT / "data/events/collector/alert-state.json"


def message(status: dict, prior: dict, now: datetime) -> tuple[str, dict]:
    reasons = [k + " (" + v.get("last_error_code", "stale_or_incomplete") + ")"
               for k, v in sorted(status["sources"].items()) if not v["healthy"]]
    signature = ",".join(reasons)
    previous = prior.get("signature", "")
    last_alert = datetime.fromisoformat(prior["last_alert_at"]) if prior.get("last_alert_at") else None
    due = signature != previous or (signature and (not last_alert or now - last_alert >= timedelta(hours=4)))
    state = {"signature": signature, "last_alert_at": now.isoformat() if due else prior.get("last_alert_at")}
    if not due:
        return "", state
    if signature:
        return "⚠️ V3 research collection degraded: " + signature + ". Intake is not complete; no trades. Inspect `python -m scripts.v3_collector health` and user systemd units.", state
    return "V3 research collection recovered: news and SEC sources are current. No trading enabled.", state


def main():
    now = datetime.now(ZoneInfo("America/New_York"))
    if not 7 <= now.hour < 23:
        return
    try:
        proc = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "scripts.v3_collector", "health"],
                              cwd=ROOT, capture_output=True, text=True, timeout=15)
        status = json.loads(proc.stdout)
        if not isinstance(status.get("sources"), dict) or set(status["sources"]) != {"news", "sec", "market"}:
            raise ValueError("invalid collector health output")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print("⚠️ V3 research collection health check failed. Inspect trading-lab-v3-health.service. No trading enabled.")
        return
    prior = json.loads(STATE.read_text()) if STATE.exists() else {}
    text, next_state = message(status, prior, now)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    with os.fdopen(os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "w") as output:
        json.dump(next_state, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temp, STATE)
    if text:
        print(text)


if __name__ == "__main__":
    main()
