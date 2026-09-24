from datetime import datetime, timedelta, timezone

import pytest

from top_heroes_auto.automation.vip_period import cycle_key, period_start
from top_heroes_auto.storage.store import Store


def test_game_reset_is_not_local_midnight():
    assert period_start(datetime(2026, 9, 24, 1, 59, tzinfo=timezone.utc)).day == 23
    assert period_start(datetime(2026, 9, 24, 2, tzinfo=timezone.utc)).day == 24


@pytest.mark.parametrize('state', ['RESERVED', 'VERIFIED'])
def test_prior_period_preserved_current_period_one_shot(tmp_path, state):
    store = Store(tmp_path / 'db')
    task = store.create_task_run('ns', 'vip-reward', 9, 'Pooh5')
    old = store.reserve_reward_claim(task, 'vip-daily', 'legacy', 'before', not_dispatched=True)
    store.mark_reward_dispatch(old, task)
    if state == 'VERIFIED':
        store.verify_reward_claim(old, task, 'after')
    with store.connect() as db:
        db.execute('UPDATE reward_claims SET reserved_at=? WHERE id=?',
                   ((period_start()-timedelta(hours=1)).isoformat(), old))
    new = store.reserve_reward_claim(task, 'vip-daily', cycle_key('vip-daily'), 'fresh available',
                                    not_dispatched=True, vip_daily_period=True)
    store.mark_reward_dispatch(new, task)
    with pytest.raises(ValueError, match='retry forbidden'):
        store.reserve_reward_claim(task, 'vip-daily', cycle_key('vip-daily'), 'fresh', vip_daily_period=True)
    rows = store.reward_claims('ns', 9)
    assert rows[0]['status'] == state and rows[0]['dispatch_state'] == 'POSSIBLE'
    assert rows[1]['status'] == 'RESERVED'


def test_same_day_legacy_attempt_remains_locked_and_other_tasks_cannot_expire(tmp_path):
    store = Store(tmp_path / 'db')
    task = store.create_task_run('ns', 'vip-reward', 9, 'Pooh5')
    store.reserve_reward_claim(task, 'vip-daily', 'legacy', 'before')
    with pytest.raises(ValueError, match='retry forbidden'):
        store.reserve_reward_claim(task, 'vip-daily', cycle_key('vip-daily'), 'fresh', vip_daily_period=True)
    with pytest.raises(ValueError):
        store.reserve_reward_claim(task, 'idle-reward', 'new', 'fresh', vip_daily_period=True)
    with pytest.raises(ValueError):
        store.reserve_reward_claim(task, 'vip-upper-gift', 'invented future period', 'fresh', vip_daily_period=True)
