"""Current supported reward features registered into the global instance pipeline."""
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


REGISTRY.register(Flow('vip', VIP, vip))
REGISTRY.register(Flow('ranking', ('ranking-chest',), fixed))
REGISTRY.register(Flow('shop', tuple(SHOP_REWARDS), fixed))
