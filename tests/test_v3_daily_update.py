from datetime import datetime, timezone

from scripts.cron.v3_daily_update import report

NOW = datetime(2026, 10, 1, 21, tzinfo=timezone.utc)
SAFETY = {'mode': 'paper_proposal_only_no_orders',
          'safety': {'broker_orders_enabled': False, 'live_trading_enabled': False}}
COLLECTOR = {'sources': {s: {'healthy': True} for s in ('news', 'sec', 'market')}}
EVENT = {'id': 'new', 'symbol': 'CCL', 'provider': 'sec-edgar-ex-99.1', 'kind': 'earnings',
         'first_seen_at': '2026-10-01T14:00:10Z', 'available_at': '2026-10-01T14:00:10Z'}


def test_daily_report_excludes_historical_event_and_calls_partial_score_diagnostic():
    old = EVENT | {'id': 'old', 'first_seen_at': '2026-09-29T16:51:14Z',
                   'available_at': '2026-09-29T16:51:14Z'}
    decision = {'event_id': 'new', 'status': 'planned', 'mode': 'offline_counterfactual_no_orders',
                'observed_at': NOW.isoformat()}
    gap = {'fetched_at': NOW.isoformat(), 'outcome': {'event_id': 'new', 'status': 'data_gap'}}
    text = report(at=NOW, collector=COLLECTOR, events=[old, EVENT], decisions=[decision],
                  outcomes=[gap], activated=datetime(2026, 9, 30, 14, tzinfo=timezone.utc),
                  safety=SAFETY, forward_timers=True)
    assert '1 post-activation' in text
    assert '1 data gaps excluded' in text
    assert 'not an edge claim' in text
    assert 'disabled (dashboard verified)' in text


def test_daily_update_labels_old_pnl_cumulative_not_today():
    old_day = NOW.replace(day=2)
    decision = {'event_id': 'new', 'status': 'planned', 'mode': 'offline_counterfactual_no_orders',
                'observed_at': '2026-10-01T14:02:00Z'}
    outcome = {'fetched_at': '2026-10-01T21:00:00Z',
               'outcome': {'event_id': 'new', 'status': 'resolved', 'net_dollars': 1.25}}
    text = report(at=old_day, collector=COLLECTOR, events=[EVENT], decisions=[decision],
                  outcomes=[outcome], activated=datetime(2026, 9, 30, 14, tzinfo=timezone.utc),
                  safety=SAFETY, forward_timers=True)
    assert 'Today: 0 new prospective events; decisions {}; outcomes {}' in text
    assert 'Since activation (cumulative)' in text
    assert 'observed net: $1.25' in text
