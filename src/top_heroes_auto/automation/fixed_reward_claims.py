"""One-shot journal boundary shared by BXH and the two authorized shop gifts."""
import json
import time

from top_heroes_auto.vision.fixed_rewards import ALL_REWARDS as REWARDS
from top_heroes_auto.vision.fixed_rewards import claim_geometry


def observe_reward(port, frame, reward):
    state, core, badge = port.detector.availability(frame, reward)
    # A positively detected transient announcement can cover the gift label.
    # Wait only; it is never permission for a dismiss/claim input.
    announced = bool(frame.box('shop-notice-speaker'))
    for _ in range(4 if announced else 2):
        if state != 'UNKNOWN' or frame.page == 'UNKNOWN':
            break
        time.sleep(1 if announced else .4)
        frame = port.observe_settled()
        state, core, badge = port.detector.availability(frame, reward)
    return frame, state, core, badge


def process_reward(port, store, namespace, task_id, reward, identity, report, persist):
    if reward not in REWARDS:
        raise ValueError("Reward is outside the annotated fixed flow.")
    before, state, core, badge = observe_reward(port, port.observe_settled(), reward)
    report.update(before=before.evidence(), availability=state, claim_dispatched=False,
                  journal="NONE", result=state,
                  badge_confidence=badge.score if badge else None)
    existing = [r for r in store.reward_claims(namespace, before.captured.index) if r['reward_id'] == reward]
    # A page countdown proves daily-offer reset. Unqualified reset semantics for
    # other gifts are deliberately conservative, never guessed from VIP reset.
    from top_heroes_auto.automation.fixed_reward_period import current_attempts, cycle_key

    period = cycle_key(reward)
    report['period'] = period
    for row in existing:
        prior = json.loads(row['before_evidence'])
        if prior.get('persistent_identity') != identity:
            report['result'] = 'IDENTITY_CONTINUITY_UNPROVEN'
            return
    locked = current_attempts(existing, reward)
    if locked:
        report.update(result='ALREADY_VERIFIED' if locked[-1]['status'] == 'VERIFIED' else 'ALREADY_ATTEMPTED',
                      journal=locked[-1]['status'], claim_id=locked[-1]['id'])
        from datetime import datetime

        from top_heroes_auto.automation.fixed_reward_period import period_start
        from top_heroes_auto.automation.fixed_reward_reconcile import reconcile_fixed_reward

        start = period_start(reward)
        if (reward.startswith('shop-') and start is None and state == 'AVAILABLE'
                and locked[-1]['status'] == 'VERIFIED'):
            report['result'] = 'PERIOD_UNQUALIFIED'
            report['period_error'] = 'A prior VERIFIED claim stays locked; a new reward period has not been proven.'
            return
        if reward.startswith('shop-') and locked[-1]['status'] == 'VERIFIED' and state != 'NOT_AVAILABLE':
            report['result'] = 'UNKNOWN' if state == 'UNKNOWN' else 'STATE_CONFLICT'
            report['state_error'] = 'Existing VERIFIED journal preserved; current reward state is not independently unavailable.'
            return
        if start is not None and locked[-1]['status'] != 'VERIFIED':
            try:
                original = datetime.fromisoformat(locked[-1]['reserved_at'])
                same_period = original.tzinfo is not None and original >= start
            except (ValueError, TypeError):
                same_period = False
            if not same_period:
                report['reconciliation_error'] = 'Current state cannot prove an uncertain claim from a prior reset period.'
                return

        try:
            proof = reconcile_fixed_reward(store, locked[-1], port.detector, before, identity)
            if proof:
                report.update(result='SUCCESS', journal='VERIFIED', reconciliation=proof,
                              post_condition='NOT_AVAILABLE')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Missing/invalid evidence cannot unlock or re-dispatch anything.
            report['reconciliation_error'] = str(exc)
        return
    if state != 'AVAILABLE':
        return
    geometry = claim_geometry(before, reward, core)
    report['geometry'] = geometry
    port.save_geometry(before, geometry, reward)
    evidence = dict(before.evidence(), persistent_identity=identity, period=period, geometry=geometry)
    claim_id = store.reserve_reward_claim(
        task_id, reward, period, json.dumps(evidence, ensure_ascii=False),
        expected_instance=(before.captured.index, before.captured.name), not_dispatched=True,
        fixed_reward_period=True,
    )
    report.update(claim_id=claim_id, journal='RESERVED', result='RESERVED')
    dispatched = False
    try:
        persist()

        def intent():
            nonlocal dispatched
            store.mark_reward_dispatch(claim_id, task_id)
            dispatched = True
            report['claim_dispatched'] = 'POSSIBLE'

        port.tap(before, core, before_input=intent)
        report['claim_dispatched'] = True
        immediate = port.observe()
        report['immediate_after'] = immediate.evidence()
        persist()
        after, after_state, _, _ = observe_reward(port, port.settle(immediate), reward)
        report['after'] = after.evidence()
        report['post_condition'] = after_state
        if (after_state == 'NOT_AVAILABLE' and before.captured.source_image != after.captured.source_image
                and (before.captured.index, before.captured.serial, before.captured.boot_id) ==
                (after.captured.index, after.captured.serial, after.captured.boot_id)):
            store.verify_reward_claim(claim_id, task_id, json.dumps(after.evidence(), ensure_ascii=False))
            report.update(journal='VERIFIED', result='SUCCESS')
        else:
            report['result'] = 'ACTION_DISPATCHED_UNVERIFIED'
    except Exception:
        report['result'] = 'ACTION_DISPATCHED_UNVERIFIED' if dispatched else 'SAFETY_BLOCKED'
        raise
    finally:
        if not dispatched:
            store.release_undispatched_reward(claim_id, task_id, 'Screenshot-bound dispatch hook was never entered.')
            report['journal'] = 'NONE'
        persist()
