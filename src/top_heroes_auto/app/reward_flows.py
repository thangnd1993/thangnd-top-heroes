"""Current supported reward features registered into the global instance pipeline."""
import json

from top_heroes_auto.app.bxh_shop_acceptance import run_account
from top_heroes_auto.app.flow_registry import REGISTRY, Flow
from top_heroes_auto.app.vip_fleet import run_vip_account
from top_heroes_auto.vision.fixed_rewards import SHOP_REWARDS

VIP = ('vip-upper-gift', 'vip-daily')


def vip_outcomes(row):
    upper = row.get('upper_gift', {})
    return {
        'vip-upper-gift': dict(result=upper.get('result', 'BLOCKED'),
            availability=upper.get('availability'), journal=upper.get('journal_state', 'NONE'),
            claim_id=upper.get('claim_id', upper.get('previous_claim_id')),
            claim_dispatched=upper.get('claim_dispatched', False), error=upper.get('error', row.get('error'))),
        'vip-daily': dict(result=row.get('daily_result', row.get('final_result', 'BLOCKED')),
            availability=row.get('free_reward_state'), journal=row.get('journal_state', 'NONE'),
            claim_id=row.get('claim_id'), claim_dispatched=row.get('claim_dispatched', False),
            error=row.get('error')),
    }


def vip(session, folder, rewards):
    row = run_vip_account(session.manager, session.data, session.index, session.name, folder,
        include_upper_gift=VIP[0] in rewards, include_daily=VIP[1] in rewards,
        session=session, cancelled=session.cancelled)
    row['rewards'] = {k: v for k, v in vip_outcomes(row).items() if k in rewards}
    return row


def fixed(session, folder, rewards):
    return run_account(session.manager, session.data, session.target, folder,
        rewards=rewards, session=session, cancelled=session.cancelled,
        identity_reader=session.identity_reader, temporary_selection=False)


def journal_completions(session,rewards,*,vip_period=False):
    from top_heroes_auto.automation.fixed_reward_period import current_attempts as fixed_attempts
    from top_heroes_auto.automation.guard import SafetyError
    from top_heroes_auto.automation.vip_period import current_attempts as vip_attempts
    from top_heroes_auto.vision.fixed_rewards import MONTHLY_QUICK

    store, namespace = session.manager.store, session.manager.namespace
    if store.metadata(namespace,session.index).protected:
        raise SafetyError('Protected journal cannot authorize a flow.')
    rows = store.reward_claims(namespace,session.index)
    completed = {}
    for reward in rewards:
        action = MONTHLY_QUICK if reward == 'shop-monthly-privilege-gift' else reward
        prior = (vip_attempts if vip_period else fixed_attempts)(rows,action)
        if not prior or any(row['status'] != 'VERIFIED' or row['instance_name'] != session.name for row in prior):
            continue
        if not vip_period and any(json.loads(row['before_evidence']).get('persistent_identity') !=
                                  session.target['persistent_identity'] for row in prior):
            continue
        row = prior[-1]
        completed[reward] = dict(result='ALREADY_VERIFIED',journal='VERIFIED',claim_id=row['id'],
            action_reward_id=action,completion_source='current_period_journal',claim_dispatched=False)
    return completed


def vip_completed(session,rewards):
    return journal_completions(session,rewards,vip_period=True)


REGISTRY.register(Flow('vip', VIP, vip, completed=vip_completed))
REGISTRY.register(Flow('ranking', ('ranking-chest',), fixed, completed=journal_completions))
REGISTRY.register(Flow('shop', tuple(SHOP_REWARDS), fixed, completed=journal_completions))
