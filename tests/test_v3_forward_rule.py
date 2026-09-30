from datetime import datetime, timedelta, timezone

from trading_lab.v3_forward_rule import decide, relevant, EFFECTIVE

SEEN = datetime(2026, 10, 1, 14, 0, 10, tzinfo=timezone.utc)
EVENT = {'id': 'independent', 'symbol': 'CCL', 'provider': 'sec-edgar-ex-99.1',
         'kind': 'earnings', 'first_seen_at': SEEN.isoformat(), 'available_at': SEEN.isoformat()}
BAR = {'symbol': 'CCL', 'feed': 'iex', 'timestamp': '2026-10-01T14:01:00Z',
       'open': 20, 'high': 20.04, 'low': 19.94, 'close': 20.02, 'volume': 1000}


def test_rule_never_backdates_existing_event_and_requires_provenance():
    assert relevant(EVENT, EFFECTIVE)
    assert not relevant(EVENT, SEEN + timedelta(seconds=1))
    assert not relevant(EVENT | {'first_seen_at': '2026-09-29T16:51:14Z'}, EFFECTIVE)
    assert not relevant(EVENT | {'provider': 'news'}, EFFECTIVE)


def test_fixed_rule_builds_bounded_decision_after_completed_bar():
    now = datetime(2026, 10, 1, 14, 2, tzinfo=timezone.utc)
    assert decide(EVENT, [BAR], received_at=now - timedelta(minutes=1)) is None
    result = decide(EVENT, [BAR], received_at=now)
    assert result['status'] == 'planned'
    assert result['planned_entry'] == 20.05 and result['stop'] == 19.93
    assert result['target'] == 20.29 and result['shares'] == 9
    assert result['decision_at'] == now.isoformat()
    assert result['data_cutoff_at'] == '2026-10-01T14:02:00+00:00'
    assert result['execution_eligible'] is False


def test_missing_or_late_iex_bar_is_not_a_hindsight_fill():
    assert decide(EVENT, [], received_at=SEEN + timedelta(minutes=5)) is None
    assert decide(EVENT, [], received_at=SEEN + timedelta(minutes=12))['reason'] == 'no_completed_iex_bar'
    assert decide(EVENT, [BAR], received_at=SEEN + timedelta(minutes=12))['reason'] == 'late_first_bar'
    assert decide(EVENT, [BAR | {'high': 25}], received_at=SEEN + timedelta(minutes=2))['reason'] == 'stop_width_invalid'
