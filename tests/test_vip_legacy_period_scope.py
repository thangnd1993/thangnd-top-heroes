import json
from datetime import timedelta

import pytest

from top_heroes_auto.automation.vip_period import cycle_key, period_start


@pytest.mark.parametrize('reward', ['vip-upper-gift', 'vip-daily'])
@pytest.mark.parametrize('state', ['RESERVED', 'VERIFIED'])
def test_earlier_vip_entitlement_keeps_uncertainty_without_blocking_new_period(rig, reward, state):
    manager, _, store = rig
    task = store.create_task_run(manager.namespace, 'vip-reward', 7, 'old label')
    old = store.reserve_reward_claim(task, reward, 'legacy', '{}')
    with store.connect() as db:
        db.execute('UPDATE reward_claims SET reserved_at=?,status=? WHERE id=?',
                   ((period_start()-timedelta(hours=1)).isoformat(), state, old))
        db.execute("UPDATE journal_identities SET stable_id='',state='AMBIGUOUS' WHERE claim_id=?", (old,))
    original = store.reward_claims(manager.namespace, 7)[0]
    fresh = store.create_task_run(manager.namespace, 'vip-reward', 7, 'new label')
    new = store.reserve_reward_claim(fresh, reward, cycle_key(reward), '{}', vip_daily_period=True,
                                    not_dispatched=True)
    assert store.reward_claims(manager.namespace, 7)[0] == original
    proof = json.loads(store.get(f'vip_prior_period_review:{fresh}:{reward}:{cycle_key(reward)}'))
    assert proof['prior_claim_ids'] == [old] and proof['original_records_unchanged']
    with store.connect() as db:
        assert db.execute('SELECT state FROM journal_identities WHERE claim_id=?', (old,)).fetchone() == ('AMBIGUOUS',)
    store.mark_reward_dispatch(new, fresh)
    with pytest.raises(ValueError, match='already attempted'):
        store.reserve_reward_claim(fresh, reward, cycle_key(reward), '{}', vip_daily_period=True)
    with pytest.raises(ValueError, match='AMBIGUOUS'):
        store.verify_reward_claim(old, task, 'invented old success')


@pytest.mark.parametrize('stamp', ['today', 'future', 'invalid', 'naive', None])
def test_current_or_unproven_period_stays_locked(rig, stamp):
    manager, _, store = rig
    task = store.create_task_run(manager.namespace, 'vip-reward', 7, 'label')
    old = store.reserve_reward_claim(task, 'vip-daily', 'legacy', '{}')
    value = {'today':period_start().isoformat(), 'future':(period_start()+timedelta(days=1)).isoformat(),
             'naive':'2020-01-01T00:00:00', 'invalid':'invalid', None:''}[stamp]
    with store.connect() as db:
        db.execute('UPDATE reward_claims SET reserved_at=? WHERE id=?', (value, old))
        db.execute("UPDATE journal_identities SET stable_id='',state='AMBIGUOUS' WHERE claim_id=?", (old,))
    with pytest.raises(ValueError, match='already attempted'):
        store.reserve_reward_claim(task, 'vip-daily', cycle_key('vip-daily'), '{}', vip_daily_period=True)
