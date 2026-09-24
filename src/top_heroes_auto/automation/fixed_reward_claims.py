"""One-shot journal boundary shared by BXH and the two authorized shop gifts."""
import json
import time

from top_heroes_auto.vision.fixed_rewards import REWARDS, claim_geometry


def process_reward(port, store, namespace, task_id, reward, identity, report, persist):
    if reward not in REWARDS:
        raise ValueError("Reward is outside the annotated fixed flow.")
    before = port.observe_settled()
    state, core, badge = port.detector.availability(before, reward)
    # A rocking gift may briefly hide its stable core; observation only, bounded.
    for _ in range(2):
        if state != 'UNKNOWN' or before.page == 'UNKNOWN':
            break
        time.sleep(.4)
        before = port.observe_settled()
        state, core, badge = port.detector.availability(before, reward)
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
        from top_heroes_auto.automation.fixed_reward_reconcile import reconcile_ranking

        try:
            proof = reconcile_ranking(store, locked[-1], port.detector, before, identity)
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
        after = port.settle(immediate)
        report['after'] = after.evidence()
        after_state, _, _ = port.detector.availability(after, reward)
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
