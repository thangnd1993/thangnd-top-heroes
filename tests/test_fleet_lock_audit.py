import json

import pytest

from top_heroes_auto.storage.fleet_repair import TRIAL, release_trial_locks
from top_heroes_auto.storage.store import Store


def fixture_trial(tmp_path):
    database = tmp_path / 'app.db'
    store = Store(database)
    fleet_path = tmp_path / 'fleet.json'
    accounts = []
    for claim, outer, inner, index, name in TRIAL:
        report_path = tmp_path / f'task-{inner}.json'
        recovery_path = tmp_path / f'recovery-{inner}.json'
        result = 'UNKNOWN_SCREEN' if index == 2 else 'ACTION_FAILED'
        error = 'GAME_HOME portal anchor was not verified.' if index == 2 else 'GAME_HOME precondition failed: LOADING_TIMEOUT: unknown'
        report = {'instance': {'index': index, 'name': name}, 'task_run_id': inner,
                  'claim_dispatched': False, 'actions': [], 'result': result, 'error': error,
                  'steps': [{'state': 'UNKNOWN', 'action': None}] if index == 2 else [],
                  'recovery_report': str(recovery_path), 'screenshots': []}
        report_path.write_text(json.dumps(report), encoding='utf-8')
        recovery_path.write_text(json.dumps({'instance': report['instance'], 'actions': ['launch_game', 'wait'],
                                            'result': 'SUCCESS' if index == 2 else 'LOADING_TIMEOUT'}), encoding='utf-8')
        accounts.append({'index': index, 'account': name, 'journal_id': claim, 'task_run_id': inner,
                         'claims_performed': 0, 'task_report': str(report_path)})
        with store.connect() as db:
            for run, task, status, path in ((outer, 'fleet-idle-once', 'BLOCKED', fleet_path),
                                             (inner, 'idle-reward', result, report_path)):
                db.execute('''INSERT INTO task_runs(id,namespace,task,instance_index,instance_name,status,
                           started_at,finished_at,report_path) VALUES (?,?,?,?,?,?,?,?,?)''',
                           (run, 'install', task, index, name, status, 'start', 'finish', str(path)))
            db.execute('''INSERT INTO reward_claims(id,namespace,instance_index,instance_name,reward_id,
                       cycle_key,task_run_id,status,reserved_at,before_evidence) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                       (claim, 'install', index, name, 'idle-reward', 'fleet-current-implementation-once',
                        outer, 'RESERVED', 'start', 'before'))
    fleet_path.write_text(json.dumps({'commit': 'af5464c', 'max_concurrency': 1, 'finished_at': 'end',
                                     'accounts': accounts}), encoding='utf-8')
    return store, fleet_path


def test_exact_fleet_audit_atomic_release_and_idempotent(tmp_path):
    store, fleet = fixture_trial(tmp_path)
    dry = release_trial_locks(store.path, fleet)
    assert [r['status'] for r in dry] == ['PROVEN_NOT_DISPATCHED'] * 3
    assert store.reward_claims('install', 2)
    assert [r['status'] for r in release_trial_locks(store.path, fleet, apply=True)] == ['RELEASED'] * 3
    assert [r['status'] for r in release_trial_locks(store.path, fleet, apply=True)] == ['ALREADY_RELEASED'] * 3
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM reward_claims').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM reward_release_audit').fetchone()[0] == 3


@pytest.mark.parametrize('change', ['missing_flag', 'dispatched', 'action', 'wrong_instance', 'incomplete_steps', 'wrong_run'])
def test_audit_rejects_incomplete_or_changed_production_evidence(tmp_path, change):
    store, fleet = fixture_trial(tmp_path)
    path = tmp_path / 'task-22.json'
    report = json.loads(path.read_text())
    if change == 'missing_flag':
        del report['claim_dispatched']
    elif change == 'dispatched':
        report['claim_dispatched'] = True
    elif change == 'action':
        report['actions'] = ['claim_once']
    elif change == 'wrong_instance':
        report['instance']['index'] = 0
    elif change == 'incomplete_steps':
        del report['steps']
    else:
        report['task_run_id'] = 99
    path.write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError):
        release_trial_locks(store.path, fleet, apply=True)
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM reward_claims').fetchone()[0] == 3
        assert db.execute('SELECT COUNT(*) FROM reward_release_audit').fetchone()[0] == 0
