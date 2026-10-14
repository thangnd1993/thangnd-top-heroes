"""Conservative per-account/event/page/reward durable action boundary."""
import hashlib
import json

from top_heroes_auto.automation.dynamic_events import free_geometry
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.ldplayer.identity import runtime_key


def reward_key(event, page, reward):
    if not all(isinstance(value, str) and value for value in (event, page, reward)):
        raise SafetyError('Independent event/page/reward identities required.')
    return 'event:'+hashlib.sha256(json.dumps([event,page,reward], ensure_ascii=False).encode()).hexdigest()


def affected_rewards(row):
    before = json.loads(row['before_evidence'])
    identities = {before.get('reward')}
    if row['status'] != 'VERIFIED':
        identities.update(before.get('possible_affected_rewards', []))
    elif row.get('after_evidence'):
        for after in json.loads(row['after_evidence']):
            identities.update(after.get('consumed_reward_ids', []))
    return identities


def action_kind(row):
    proof = json.loads(row['before_evidence'])
    # Old expedition records are positively typed by their original feature.
    return proof.get('action_type', 'DISPATCH' if proof.get('event') == 'relic-expedition-mission' else 'COLLECT')


def dispatch_once(store, task, namespace, frame, control, *, event_identity,
                  persistent_identity, dispatch, postcondition, persist=lambda result: None,
                  action_type='COLLECT'):
    """Unknown periods lock indefinitely; unresolved actions lock across periods.

    Adapters qualify semantic identities. Run IDs, positions and screenshot hashes
    are forbidden as reward/reset identities. Sibling rewards have separate keys.
    """
    if action_type not in {'COLLECT', 'DISPATCH'}:
        raise SafetyError('Unsupported journal action type.')
    point = free_geometry(control)
    key = reward_key(event_identity+(':DISPATCH' if action_type=='DISPATCH' else ''),
                     frame.page, control.identity)
    # OCR title changes must not unlock a dispatched visual reward. Unknown
    # identity/period collisions deliberately over-block rather than redispatch.
    all_rows = store.reward_claims(namespace, frame.identity[0])
    rows = [r for r in all_rows
            if action_kind(r)==action_type and (r['reward_id'] == key or (
                r['reward_id'].startswith('event:')
                and control.identity in affected_rewards(r)
                and (r['status'] != 'VERIFIED' or r['cycle_key'] == 'unknown-period')))]
    for row in rows:
        if json.loads(row['before_evidence']).get('persistent_identity') != persistent_identity:
            raise SafetyError('Event journal persistent identity changed.')
    locks = [r for r in rows if r['status'] != 'VERIFIED' or r['cycle_key'] == control.period
             or r['cycle_key'] == 'unknown-period']
    if action_type=='DISPATCH':
        from top_heroes_auto.automation.expedition_journal import renewed_dispatch

        locks = [r for r in rows if not renewed_dispatch(r,control.period,all_rows,persistent_identity)]
    elif control.period.startswith('after-expedition-dispatch:'):
        from top_heroes_auto.automation.expedition_journal import renewed_collection

        locks = [r for r in rows if not renewed_collection(r,control.period,all_rows,persistent_identity)]
    if locks:
        row = locks[-1]
        return dict(result='ALREADY_VERIFIED' if row['status'] == 'VERIFIED' else 'ALREADY_ATTEMPTED',
                    journal=row['status'], claim_id=row['id'], claim_dispatched=False)
    proof = dict(persistent_identity=persistent_identity, event=event_identity, page=frame.page,
                 reward=control.identity, period=control.period, capture=frame.capture,
                 identity=frame.identity, tap=point, evidence=control.evidence, action_type=action_type)
    if {'selected-task-context','qualified-task-grid'} & set(control.evidence):
        proof['possible_affected_rewards'] = [c.identity for c in frame.controls
            if c.kind == 'reward' and c.cost == 'FREE' and c.available]
        if control.identity not in proof['possible_affected_rewards']:
            proof['possible_affected_rewards'].append(control.identity)
    claim = store.reserve_reward_claim(task,key,control.period,json.dumps(proof),
                                     expected_instance=frame.identity[:2],not_dispatched=True)
    result = dict(claim_id=claim, reward=key, journal='RESERVED', claim_dispatched=False,
                  result='RESERVED', diamond_reward=control.diamond_reward)
    sent = False
    try:
        persist(result)

        def intent():
            nonlocal sent
            if sent:
                raise SafetyError('Duplicate dispatch callback.')
            store.mark_reward_dispatch(claim,task)
            sent = True
            result.update(claim_dispatched=True, result='ACTION_DISPATCHED_UNVERIFIED')
            persist(result)

        dispatch(frame, control, point, intent)
        if not sent:
            raise SafetyError('Transport omitted the journal boundary.')
        observations = postcondition(frame, control)
        if len(observations) != 2:
            return result
        captures = {frame.capture}
        for after in observations:
            if (runtime_key(after.get('identity', ())) != runtime_key(frame.identity) or after.get('capture') in captures or
                    not after.get('capture') or after.get('event') != event_identity or
                    after.get('page') != frame.page or after.get('reward') != control.identity or
                    after.get('state') != ('RUNNING' if action_type == 'DISPATCH' else 'NOT_AVAILABLE')
                    or not after.get('independent_evidence')):
                return result
            captures.add(after['capture'])
        store.verify_reward_claim(claim,task,json.dumps(observations))
        result.update(journal='VERIFIED', result='SUCCESS')
    finally:
        if not sent:
            store.release_undispatched_reward(claim,task,'Event dispatch never reached transport boundary.')
            result.update(journal='RELEASED', result='NOT_DISPATCHED')
        persist(result)
    return result
