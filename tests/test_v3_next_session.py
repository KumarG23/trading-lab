import json
from datetime import datetime, timedelta, timezone

from trading_lab.v3_next_session_rule import PREREGISTERED, next_session, decide
from scripts.v3_next_session_run import acquire, resolve, main
from scripts.cron.v3_daily_update import next_session_summary
import sys
import pytest

SEEN = datetime(2026, 10, 2, 20, 24, tzinfo=timezone.utc)  # Friday after close
EVENT = {"id": "b" * 64, "symbol": "MU", "provider": "sec-edgar-ex-99.1",
         "kind": "earnings", "available_at": SEEN.isoformat(), "first_seen_at": SEEN.isoformat()}
OPEN = datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc)
BARS = [{"symbol": "MU", "feed": "iex", "timestamp": (OPEN + timedelta(minutes=i)).isoformat(),
         "open": 100, "high": 100.1, "low": 99.9, "close": 100, "volume": 1000} for i in range(5)]

class Reader:
    def __init__(self, bars=BARS):
        self.bars, self.calls = bars, []
    def fetch_stock_bars(self, symbols, **kwargs):
        self.calls.append((symbols, kwargs))
        assert kwargs["feed"] == "iex" and kwargs["timeframe"] == "1Min"
        return self.bars


def test_activation_and_calendar_guard_mu_historical():
    old = EVENT | {"first_seen_at": "2026-09-30T20:24:00Z", "available_at": "2026-09-30T20:24:00Z"}
    assert next_session(old, PREREGISTERED) is None
    assert next_session(EVENT, SEEN + timedelta(seconds=1)) is None
    session = next_session(EVENT, PREREGISTERED)
    assert session[0] == OPEN and session[1].date() == OPEN.date()
    assert next_session(EVENT | {"available_at": (SEEN - timedelta(seconds=1)).isoformat()}, PREREGISTERED) is None
    assert next_session(EVENT | {"first_seen_at": "2026-10-02T19:59:00Z", "available_at": "2026-10-02T19:59:00Z"}, PREREGISTERED) is None


def test_timely_opening_decision_is_fixed_and_private(tmp_path):
    store = tmp_path / "decisions"
    reader = Reader()
    now = OPEN + timedelta(minutes=5, seconds=20)
    assert acquire([EVENT], now=OPEN, activated=PREREGISTERED, data=reader, store=store)["awaiting_open"] == 1
    assert not reader.calls
    assert acquire([EVENT], now=now, activated=PREREGISTERED, data=reader, store=store)["planned"] == 1
    path = store / (EVENT["id"] + ".json")
    plan = json.loads(path.read_text())
    assert plan["data_cutoff_at"] == (OPEN + timedelta(minutes=5)).isoformat()
    assert plan["shares"] == 1 and plan["planned_entry"] == 100.11
    assert plan["execution_eligible"] is False and plan["mode"] == "offline_counterfactual_no_orders"
    assert plan["decision_at"] == now.isoformat()
    assert path.stat().st_mode & 0o777 == 0o600
    assert acquire([EVENT], now=OPEN + timedelta(hours=1), activated=PREREGISTERED,
                   data=reader, store=store)["already_recorded"] == 1
    assert len(reader.calls) == 1
    assert 'inactive' in next_session_summary([EVENT], tmp_path / 'empty', tmp_path / 'outcomes')
    (store / 'activation.json').write_text(json.dumps({'activated_at': PREREGISTERED.isoformat()}))
    summary = next_session_summary([EVENT], store, tmp_path / 'outcomes')
    assert '1 eligible events' in summary and '1 plans' in summary
    assert 'MU' not in summary and EVENT['id'] not in summary


def test_missing_bar_late_capture_and_outcome_gap(tmp_path):
    session = next_session(EVENT, PREREGISTERED)
    assert session is not None
    now = OPEN + timedelta(minutes=5, seconds=30)
    assert decide(EVENT, BARS[:-1], received_at=now, session=session) is None
    missing = decide(EVENT, BARS[:-1], received_at=OPEN + timedelta(minutes=7), session=session)
    assert missing is not None and missing["reason"] == "missing_opening_bars"
    assert decide(EVENT, BARS + [BARS[0]], received_at=now, session=session)["reason"] == "invalid_iex_bar"
    assert decide(EVENT, BARS, received_at=OPEN + timedelta(minutes=7, seconds=1), session=session)["reason"] == "late_capture"
    store, outcomes = tmp_path / "plans", tmp_path / "outcomes"
    late = Reader()
    assert acquire([EVENT], now=OPEN + timedelta(minutes=8), activated=PREREGISTERED,
                   data=late, store=store)["abstain"] == 1
    assert not late.calls
    store2 = tmp_path / "valid"
    acquire([EVENT], now=now, activated=PREREGISTERED, data=Reader(), store=store2)
    after_close = OPEN + timedelta(hours=7)
    resolver = Reader([])
    assert resolve(now=after_close, data=resolver, store=store2, outcomes=outcomes)["data_gap"] == 1
    result = json.loads((outcomes / (EVENT["id"] + ".json")).read_text())["outcome"]
    assert result["status"] == "data_gap" and "net_dollars" not in result
    assert resolve(now=after_close, data=resolver, store=store2, outcomes=outcomes)["data_gap"] == 0


def test_first_activation_only_after_successful_ledger_read(tmp_path, monkeypatch):
    store = tmp_path / 'ledger'
    monkeypatch.setattr('scripts.v3_next_session_run.STORE', store)
    monkeypatch.setattr('scripts.v3_next_session_run.client', lambda: Reader())
    monkeypatch.setattr('scripts.v3_next_session_run.load_ledger', lambda *args: (_ for _ in ()).throw(ValueError('bad ledger')))
    monkeypatch.setattr(sys, 'argv', ['v3_next_session_run', 'intake'])
    with pytest.raises(ValueError, match='bad ledger'):
        main()
    assert not (store / 'activation.json').exists()
    monkeypatch.setattr('scripts.v3_next_session_run.load_ledger', lambda *args: [])
    main()
    marker = json.loads((store / 'activation.json').read_text())
    assert datetime.fromisoformat(marker['activated_at']) >= PREREGISTERED
    assert next_session(EVENT | {'available_at': '2026-09-30T20:24:00Z',
                                 'first_seen_at': '2026-09-30T20:24:00Z'},
                        datetime.fromisoformat(marker['activated_at'])) is None


def test_failed_source_does_not_record_abstention(tmp_path):
    class Failed:
        def fetch_stock_bars(self, *args, **kwargs):
            raise OSError("unavailable")
    try:
        acquire([EVENT], now=OPEN + timedelta(minutes=5), activated=PREREGISTERED,
                data=Failed(), store=tmp_path)
    except OSError:
        pass
    else:
        assert False, "expected source failure"
    assert list(tmp_path.iterdir()) == []
