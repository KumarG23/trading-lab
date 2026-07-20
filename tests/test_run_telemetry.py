import json

from trading_lab.run_telemetry import write_run_telemetry


def test_write_run_telemetry_atomically_persists_latest_payload(tmp_path):
    output = tmp_path / "last-run.json"

    write_run_telemetry(output, {"ok": True, "timings_ms": {"total": 812.4}})

    assert json.loads(output.read_text()) == {"ok": True, "timings_ms": {"total": 812.4}}
    assert not list(tmp_path.glob("*.tmp"))
