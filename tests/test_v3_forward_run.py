import json
from datetime import datetime, timedelta, timezone
import sys
import pytest

from scripts.v3_forward_run import acquire, resolve, main
SEEN = datetime(2026, 10, 1, 14, 0, 10, tzinfo=timezone.utc)
EVENT = {'id': 'a' * 64, 'symbol': 'CCL', 'provider': 'sec-edgar-ex-99.1',
         'kind': 'earnings', 'first_seen_at': SEEN.isoformat(), 'available_at': SEEN.isoformat()}
BAR = {'symbol': 'CCL', 'feed': 'iex', 'timestamp': '2026-10-01T14:01:00Z',
       'open': 20, 'high': 20.04, 'low': 19.94, 'close': 20.02, 'volume': 1000}


class FakeBars:
    def __init__(self, bars):
        self.bars = bars
        self.calls = []

    def fetch_stock_bars(self, symbols, **kwargs):
        self.calls.append((symbols, kwargs))
        assert kwargs['feed'] == 'iex' and kwargs['timeframe'] == '1Min'
        return self.bars


def test_acquire_never_networks_or_backdates_pre_activation_event(tmp_path):
    api = FakeBars([BAR])
    result = acquire([EVENT], now=SEEN + timedelta(minutes=2),
                     activated=SEEN + timedelta(minutes=1), data=api, store=tmp_path)
    assert result['historical_or_ineligible'] == 1 and not api.calls
    assert list(tmp_path.iterdir()) == []


def test_failed_first_intake_does_not_backdate_activation(tmp_path, monkeypatch):
    monkeypatch.setattr('scripts.v3_forward_run.STORE', tmp_path / 'plans')
    monkeypatch.setattr('scripts.v3_forward_run.client', lambda: FakeBars([]))
    monkeypatch.setattr('scripts.v3_forward_run.load_ledger', lambda *args: (_ for _ in ()).throw(ValueError('bad ledger')))
    monkeypatch.setattr(sys, 'argv', ['v3_forward_run', 'intake'])
    with pytest.raises(ValueError, match='bad ledger'):
        main()
    assert not (tmp_path / 'plans/activation.json').exists()


def test_late_session_event_records_abstention_without_bar_network(tmp_path):
    seen = datetime(2026, 10, 1, 19, 0, 10, tzinfo=timezone.utc)
    event = EVENT | {'first_seen_at': seen.isoformat(), 'available_at': seen.isoformat()}
    api = FakeBars([BAR])
    result = acquire([event], now=seen + timedelta(minutes=1),
                     activated=SEEN, data=api, store=tmp_path)
    assert result['abstentions'] == 1 and not api.calls
    assert json.loads((tmp_path / ('a' * 64 + '.json')).read_text())['reason'] == 'outside_decision_window'


def test_acquire_real_id_and_resolve_sparse_iex_fails_closed(tmp_path):
    event = EVENT
    store, outcomes = tmp_path / 'plans', tmp_path / 'outcomes'
    api = FakeBars([BAR])
    result = acquire([event], now=SEEN + timedelta(minutes=2),
                     activated=SEEN - timedelta(minutes=1), data=api, store=store)
    assert result['new_plans'] == 1
    plan = json.loads((store / ('a' * 64 + '.json')).read_text())
    assert plan['decision_bar']['feed'] == 'iex'
    assert (store / ('a' * 64 + '.json')).stat().st_mode & 0o777 == 0o600
    assert acquire([event], now=SEEN + timedelta(minutes=3),
                   activated=SEEN - timedelta(minutes=1), data=api, store=store)['new_plans'] == 0
    assert len(api.calls) == 1
    after_close = datetime(2026, 10, 1, 21, tzinfo=timezone.utc)
    api.bars = []
    result = resolve(now=after_close, data=api, store=store, outcomes=outcomes)
    assert result['data_gap'] == 1
    record = json.loads((outcomes / ('a' * 64 + '.json')).read_text())
    assert record['outcome']['status'] == 'data_gap'
    assert 'net_dollars' not in record['outcome']
    assert resolve(now=after_close, data=api, store=store, outcomes=outcomes)['data_gap'] == 0
