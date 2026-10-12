"""Existing conservative Idle task in the shared per-instance lifecycle."""
import json
from pathlib import Path

from top_heroes_auto.app.flow_registry import REGISTRY, Flow
from top_heroes_auto.app.task_cli import run_idle_reward_diagnostic
from top_heroes_auto.automation.guard import SafetyError

REWARD = 'idle-reward'
CYCLE = 'idle-conservative-opportunity'


def previous(session):
    store, namespace = session.manager.store, session.manager.namespace
    if store.metadata(namespace, session.index).protected:
        raise SafetyError('Protected target cannot authorize Idle.')
    rows = [r for r in store.reward_claims(namespace, session.index)
            if r['reward_id'] == REWARD and (r['cycle_key'] == CYCLE or r['status'] == 'RESERVED')]
    if not rows:
        # Early accepted Idle actions predate the durable claim table. A missing
        # journal is not proof that these historical actions were undispatched.
        with store.connect() as db:
            legacy = db.execute('SELECT id,status,report_path FROM task_runs '
                'WHERE namespace=? AND instance_index=? AND task=? ORDER BY id',
                (namespace, session.index, REWARD)).fetchall()
        for task_id, status, path in legacy:
            evidence = {}
            try:
                if path:
                    evidence = json.loads(Path(path).read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
            if evidence.get('claim_dispatched') or status in {
                    'SUCCESS', 'SUCCESS_WITH_RECOVERY_WARNING', 'CLEANUP_FAILED', 'ACTION_RESULT_UNCERTAIN'}:
                return dict(result='BLOCKED', journal='LEGACY_ACTION_LOCKED',
                    historical_task_id=task_id, report_path=path, claim_dispatched=False,
                    error='Historical Idle action has no proven reset; no redispatch.')
        return None
    # Calendar changes do not establish another Idle opportunity. Old ambiguous
    # disk mappings remain locked, rather than being treated as completion.
    with store.connect() as db:
        identity = db.execute('SELECT stable_id,state FROM instance_identities WHERE namespace=? AND idx=?',
                              (namespace, session.index)).fetchone()
        bindings = [db.execute('SELECT stable_id,state FROM journal_identities WHERE claim_id=?',
                               (r['id'],)).fetchone() for r in rows]
    expected = (session.target['persistent_identity'], 'VERIFIED')
    bound = identity == expected and all(binding == expected for binding in bindings)
    verified = bound and all(r['status'] == 'VERIFIED' for r in rows)
    row = rows[-1]
    return dict(result='ALREADY_VERIFIED' if verified else 'BLOCKED',
                journal=row['status'], claim_id=row['id'], claim_dispatched=False,
                completion_source='conservative_idle_journal',
                error=None if verified else 'Existing Idle attempt remains locked; no redispatch.')


def completed(session, rewards):
    prior = previous(session)
    return {REWARD: prior} if prior and prior['result'] == 'ALREADY_VERIFIED' else {}


def run(session, folder, rewards):
    session.check()
    prior = previous(session)
    if prior:
        return dict(rewards={REWARD: prior})
    result, path, started, _ = run_idle_reward_diagnostic(
        session.manager, session.data, session.index, session.name,
        cancelled=session.cancelled, session=session)
    if started:
        raise SafetyError('Shared Idle flow cannot own lifecycle.')
    detail = json.loads(path.read_text(encoding='utf-8'))
    detail['report_path'] = str(path)
    detail['rewards'] = {REWARD: dict(result=result.status.value,
        journal=result.journal_result, claim_id=detail['claim_journal_id'],
        claim_dispatched=result.claim_dispatched, postcondition=result.postcondition_result,
        error=result.error)}
    detail['return_home'] = 'SUCCESS' if result.recovery_result in {'SUCCESS', 'VERIFIED'} else 'FAILED'
    return detail


REGISTRY.register(Flow('idle', (REWARD,), run, completed=completed))
