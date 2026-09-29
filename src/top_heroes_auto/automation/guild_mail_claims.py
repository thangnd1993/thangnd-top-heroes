"""One-shot, progress-verified Guild/Mail actions on a single owned session."""
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.guild_mail import GUILD_REWARDS, MAIL_REWARDS


@dataclass(frozen=True)
class Opportunity:
    reward: str
    state: str
    role: str = ''
    box: object = None
    remaining: int | None = None
    context: str = ''
    forbidden: tuple = ()

    def evidence(self):
        return asdict(self)


def relic_cycle(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Relic reset needs an aware time.')
    now = now.astimezone(timezone.utc)
    start = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if now < start:
        start -= timedelta(days=1)
    return f'guild-relic:{start.isoformat()}'


def qualified_progress(before_frame, before, after_frame, after, *, maximum_elapsed=90):
    """A popup, changed pixels, or successful transport is never a receipt."""
    a, b = before_frame.captured, after_frame.captured
    post_states = {'AVAILABLE','NOT_AVAILABLE'}
    if before.reward == 'guild-technology':
        # A qualified counter proves the preceding WOOD input even if its next
        # cost/control is no longer actionable. UNKNOWN pages/counts still fail.
        post_states.update(('RESOURCE_NOT_AUTHORIZED','UNKNOWN'))
    if (not a.source_image or not b.source_image or a.source_image == b.source_image or
            (a.index,a.name,a.serial,a.boot_id) != (b.index,b.name,b.serial,b.boot_id) or
            before_frame.page == 'UNKNOWN' or before_frame.page != after_frame.page or
            before.state != 'AVAILABLE' or after.state not in post_states or
            before.reward != after.reward or not before.context or before.context != after.context):
        return False
    try:
        elapsed = (datetime.fromisoformat(b.timestamp)-datetime.fromisoformat(a.timestamp)).total_seconds()
    except (ValueError,TypeError):
        return False
    if not 0 < elapsed <= maximum_elapsed <= 180:
        return False
    if before.reward == 'guild-relic':
        return after.state == 'NOT_AVAILABLE'
    if type(before.remaining) is not int or type(after.remaining) is not int:
        return False
    if not 0 <= after.remaining < before.remaining:
        return False
    return before.reward != 'guild-technology' or after.remaining == before.remaining-1


def process(port, store, namespace, task_id, reward, identity, report, persist):
    if reward not in (*GUILD_REWARDS,*MAIL_REWARDS):
        raise SafetyError('Unsupported Guild/Mail action.')
    report.update(result='UNKNOWN',journal='NONE',claim_dispatched=False,claim_count=0,actions=[])
    limit = 20 if reward == 'guild-technology' else 1 if reward == 'guild-relic' else 12
    for _ in range(limit):
        frame, view = port.opportunity(reward)
        report['latest'] = dict(frame=frame.evidence(),opportunity=view.evidence())
        if reward == 'guild-technology':
            report.setdefault('start_remaining',view.remaining)
            report['end_remaining'] = view.remaining
            report['resource'] = getattr(frame,'values',{}).get('donation_resource',{})
        rows = [r for r in store.reward_claims(namespace,frame.captured.index) if r['reward_id'] == reward]
        for row in rows:
            original = json.loads(row['before_evidence'])
            allowed_names = {frame.captured.name, *getattr(port, 'historical_names', ())}
            if original.get('persistent_identity') != identity or row['instance_name'] not in allowed_names:
                report['result'] = 'IDENTITY_CONTINUITY_UNPROVEN'
                persist()
                return
        # An uncertain batch/donation cannot be regenerated from a new screenshot,
        # elapsed clock, restart, changed count or a new process.
        locks = [r for r in rows if r['status'] != 'VERIFIED']
        period = relic_cycle() if reward == 'guild-relic' else None
        if period:
            locks += [r for r in rows if r['cycle_key'] == period and r['status'] == 'VERIFIED']
        if locks:
            last = locks[-1]
            previous_count = json.loads(last['before_evidence']).get('opportunity',{}).get('remaining')
            if (last['status'] != 'VERIFIED' and view.state in {'AVAILABLE','NOT_AVAILABLE'}
                    and type(previous_count) is int and type(view.remaining) is int
                    and 0 <= view.remaining < previous_count):
                from top_heroes_auto.automation.guild_mail_reconcile import (
                    FRESH_BATCH_REWARDS,
                    prepare_observed_guild_mail,
                    reconcile_observed_guild_mail,
                )

                if reward in FRESH_BATCH_REWARDS:
                    # Observe only. The existing POSSIBLE action remains locked
                    # unless its original receipt and two agreeing progress frames prove it.
                    try:
                        prepared = prepare_observed_guild_mail(store,last['id'],port.detector,identity)
                        fresh,confirmation = port.observe(),port.observe()
                        report['reconciliation'] = reconcile_observed_guild_mail(
                            store,last['id'],port.detector,(fresh,confirmation),identity,prepared=prepared)
                    except ValueError as exc:
                        report['reconciliation_error'] = str(exc)
                    else:
                        report.update(result='ALREADY_VERIFIED',journal='VERIFIED',claim_id=last['id'])
                        persist()
                        if report['reconciliation']['after'][-1]['opportunity']['remaining'] == 0:
                            return
                        # The original action is now proven. Reobserve any
                        # remaining free content through the normal batch guard.
                        continue
            report.update(result='ALREADY_VERIFIED' if last['status'] == 'VERIFIED' else 'ALREADY_ATTEMPTED',
                          journal=last['status'],claim_id=last['id'])
            persist()
            return
        if reward == 'guild-technology' and view.state == 'RESOURCE_NOT_AUTHORIZED':
            report.update(result=('RESOURCE_NOT_AUTHORIZED' if report['resource'].get('resource') in
                                  {'STONE','DIAMOND'} else 'UNKNOWN'),remaining=view.remaining,
                          remaining_result='RESOURCE_NOT_AUTHORIZED')
            persist()
            return
        if view.state == 'NOT_AVAILABLE':
            report['result'] = 'SUCCESS' if report['claim_count'] else 'NOT_AVAILABLE'
            report['remaining'] = view.remaining
            persist()
            return
        if view.state != 'AVAILABLE' or view.box is None:
            report['result'] = 'UNKNOWN'
            persist()
            return
        if reward != 'guild-relic' and (type(view.remaining) is not int or view.remaining <= 0):
            raise SafetyError('Action needs a qualified positive current count.')
        if period and relic_cycle(datetime.fromisoformat(frame.captured.timestamp)) != period:
            report['result'] = 'STALE_PERIOD_EVIDENCE'
            persist()
            return
        # The sequence is linked to independently verified consumption, never a
        # screenshot hash. Same sequence is transactionally unique in the Store.
        parent = rows[-1]['id'] if rows else 0
        cycle = period or f'progress:after-verified-{parent}'
        geometry = port.geometry(frame,view)
        proof = dict(frame=frame.evidence(),opportunity=view.evidence(),geometry=geometry,
                     persistent_identity=identity,parent_claim_id=parent)
        claim_id = store.reserve_reward_claim(task_id,reward,cycle,json.dumps(proof,ensure_ascii=False),
                    expected_instance=(frame.captured.index,frame.captured.name),not_dispatched=True)
        action = dict(claim_id=claim_id,cycle=cycle,before=proof,journal='RESERVED',claim_dispatched=False)
        report['actions'].append(action)
        report.update(claim_id=claim_id,journal='RESERVED')
        dispatched = False
        try:
            persist()

            def intent():
                nonlocal dispatched
                # Reset crossing is a reason to recapture, not to relabel a claim.
                if period and period != relic_cycle():
                    raise SafetyError('Relic period changed before input.')
                store.mark_reward_dispatch(claim_id,task_id)
                dispatched = True
                action['claim_dispatched'] = 'POSSIBLE'
                report['claim_dispatched'] = True
                report['claim_count'] += 1

            port.claim(frame,view,before_input=intent)
            action['claim_dispatched'] = True
            immediate = port.observe()
            action['immediate_after'] = immediate.evidence()
            persist()
            after_frame, after = port.opportunity(reward, initial=immediate)
            action['post_observations'] = []
            # The first screenshot can precede the server/UI update. Poll only;
            # no second action and no journal release, even if nothing changes.
            for attempt in range(3):
                action['post_observations'].append(dict(frame=after_frame.evidence(),opportunity=after.evidence()))
                persist()
                if qualified_progress(frame,view,after_frame,after) or attempt == 2:
                    break
                time.sleep(.4)
                after_frame, after = port.opportunity(reward)
            confirmation_frame, confirmation = port.opportunity(reward)
            action['after'] = dict(frame=after_frame.evidence(),opportunity=after.evidence())
            action['confirmation'] = dict(frame=confirmation_frame.evidence(),opportunity=confirmation.evidence())
            if (qualified_progress(frame,view,after_frame,after) and
                    qualified_progress(frame,view,confirmation_frame,confirmation) and
                    after_frame.captured.source_image != confirmation_frame.captured.source_image and
                    after.state == confirmation.state and after.remaining == confirmation.remaining):
                store.verify_reward_claim(claim_id,task_id,json.dumps(
                    dict(after=action['after'],confirmation=action['confirmation']),ensure_ascii=False))
                action.update(journal='VERIFIED',result='SUCCESS')
                report.update(journal='VERIFIED',result='SUCCESS',remaining=after.remaining)
                if reward == 'guild-technology':
                    report['end_remaining'] = confirmation.remaining
                    report['resource'] = getattr(confirmation_frame,'values',{}).get('donation_resource',{})
                    if confirmation.state == 'RESOURCE_NOT_AUTHORIZED':
                        report['remaining_result'] = 'RESOURCE_NOT_AUTHORIZED'
                        report['result'] = ('RESOURCE_NOT_AUTHORIZED' if report['resource'].get('resource') in
                                            {'STONE','DIAMOND'} else 'UNKNOWN')
            else:
                action['result'] = report['result'] = 'ACTION_DISPATCHED_UNVERIFIED'
                return
        except Exception as exc:  # noqa: BLE001 - preserve dispatch uncertainty and stop this reward
            action['error'] = str(exc)
            action['result'] = report['result'] = 'ACTION_DISPATCHED_UNVERIFIED' if dispatched else 'SAFETY_BLOCKED'
            return
        finally:
            if not dispatched:
                store.release_undispatched_reward(claim_id,task_id,'Current-frame dispatch hook was never entered.')
                action['journal'] = report['journal'] = 'NONE'
            persist()
        if (reward == 'guild-relic' or report.get('remaining') == 0
                or report.get('remaining_result') == 'RESOURCE_NOT_AUTHORIZED'):
            return
    report['result'] = 'BOUNDED_LIMIT'
    persist()
