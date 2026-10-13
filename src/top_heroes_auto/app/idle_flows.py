"""Existing conservative Idle task in the shared per-instance lifecycle."""
import json

from top_heroes_auto.app.flow_registry import REGISTRY, Flow
from top_heroes_auto.app.task_cli import run_idle_reward_diagnostic
from top_heroes_auto.automation.guard import SafetyError

REWARD = 'idle-reward'
CYCLE = 'idle-conservative-opportunity'


def previous(session):
    from top_heroes_auto.app.idle_opportunity import opportunity

    try:
        opportunity(session.manager.store, session.manager.namespace, session.index,
                    session.target['persistent_identity'])
    except SafetyError as exc:
        if session.manager.store.metadata(session.manager.namespace, session.index).protected:
            raise
        return dict(result='BLOCKED', journal='LEGACY_ACTION_LOCKED' if 'LEGACY_ACTION_LOCKED' in str(exc)
                    else 'HISTORICAL_ACTION_LOCKED', claim_dispatched=False, error=str(exc))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return dict(result='BLOCKED', journal='ORIGINAL_EMPTY_PROOF_MISSING', claim_dispatched=False,
                    error=str(exc))
    return None


def completed(session, rewards):
    # Historical success does not complete a newly accumulated opportunity.
    # Only current visual availability can qualify another one-shot action.
    previous(session)
    return {}


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
