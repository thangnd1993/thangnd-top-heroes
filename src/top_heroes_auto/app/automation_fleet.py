"""Global instance-first scheduler: snapshot flows, exhaust each, cleanup once."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from top_heroes_auto.app.bxh_shop_acceptance import (
    candidates,
    choose_random,
    inventory,
    persistent_identity,
    progress,
    write,
)
from top_heroes_auto.app.flow_registry import COMPLETE, production_registry
from top_heroes_auto.app.instance_session import InstanceSession
from top_heroes_auto.app.resume_exception import preserved_claims
from top_heroes_auto.automation.guard import SafetyError


def blocked(error):
    return dict(result='BLOCKED', claim_dispatched=False, journal='NONE', error=str(error))


def execute_instance(manager, data, target, folder, registry, *, prior=None, enabled=None,
                     session_factory=InstanceSession, identity_reader=persistent_identity,
                     temporary_selection=True, cancelled=lambda: False, preserve_possible=(), resume_flows=(), refresh_flows=(), only_flows=()):
    prior = prior or {}
    full_plan = registry.snapshot(enabled)
    plan = tuple(f for f in full_plan if (not resume_flows or f.id in resume_flows)
                 and (not only_flows or f.id in only_flows))
    required = tuple(r for flow in plan for r in flow.rewards)
    row = dict(index=target['index'], name=target['name'], result='PARTIAL',
        plan=[dict(flow=f.id, rewards=list(f.rewards), enabled=f.enabled, supported=f.supported) for f in plan],
        rewards=dict(prior.get('rewards', {})), flows={},
        cleanup='NOT_REQUIRED', selection_restored=True, recovery_ok=prior.get('recovery_ok', False), new_claims=0)
    exceptions = preserved_claims(manager, {'accounts': [prior]}, [target], preserve_possible)
    by_reward = {proof['reward']: proof for proof in exceptions.values()}
    if set(by_reward)-set(required):
        raise SafetyError('Preserved reward is absent from the frozen registry plan.')
    row['rewards'].update(by_reward)
    row['execution_flows'] = [f.id for f in plan]
    row['out_of_scope_flows'] = [f.id for f in full_plan if f not in plan]

    def complete(outcome):
        return outcome.get('result') in COMPLETE or (
            outcome.get('reward') in by_reward and outcome == by_reward[outcome['reward']])

    folder.mkdir(parents=True, exist_ok=True)
    def persist():
        write(folder/'account-report.json', row)
    persist()  # The execution plan is durable BEFORE selection/lifecycle mutation.
    session = session_factory(manager, data, target, folder, identity_reader=identity_reader,
        temporary_selection=temporary_selection, cancelled=cancelled)
    started = False
    if all(not f.enabled for f in plan):
        row['recovery_ok'] = True
    start_error = target.get('identity_error')
    try:
        for flow in plan:
            try:
                status = ('DISABLED' if not flow.enabled else 'NOT_APPLICABLE' if not flow.applicable(target)
                          else 'BLOCKED' if not flow.supported else None)
                completed = flow.completed(session,flow.rewards) if status is None else {}
                for reward, proof in completed.items():
                    if (reward not in flow.rewards or proof.get('result') != 'ALREADY_VERIFIED'
                            or proof.get('journal') != 'VERIFIED' or not proof.get('claim_id')):
                        raise SafetyError('Invalid feature journal completion evidence.')
                    prior_reward = row['rewards'].get(reward,{})
                    if not complete(prior_reward):
                        row['rewards'][reward] = dict(proof,claim_dispatched=False,
                            prior_result=prior_reward.get('result'))
                    elif not prior_reward.get('claim_id'):
                        row['rewards'][reward] = dict(prior_reward,claim_id=proof['claim_id'],
                            journal='VERIFIED',completion_source=proof.get('completion_source','journal'))

            except Exception as exc:  # noqa: BLE001 - invalid applicability cannot omit later independent flows
                row['flows'][flow.id] = dict(result='BLOCKED', error=str(exc))
                row['error'] = str(exc)
                for reward in flow.rewards:
                    if not complete(row['rewards'].get(reward,{})):
                        row['rewards'][reward] = blocked(exc)
                persist()
                continue
            if status:
                row['flows'][flow.id] = dict(result=status, error='Unsupported flow.' if status == 'BLOCKED' else None)
                for reward in flow.rewards:
                    row['rewards'].setdefault(reward, dict(result=status, journal='NONE', claim_dispatched=False))
                persist()
                continue
            pending = tuple(r for r in flow.rewards if not complete(row['rewards'].get(r, {})) or row['rewards'].get(r, {}).get('result') in {'DISABLED', 'NOT_APPLICABLE'})
            if flow.refresh_current_batches and (pending or flow.id in refresh_flows):
                pending = flow.rewards  # Current counters + batch journal guards decide input.
            if not pending:
                row['flows'][flow.id] = dict(result='ALREADY_COMPLETED', rewards={r: row['rewards'][r] for r in flow.rewards})
                persist()
                continue
            try:
                if start_error:
                    raise SafetyError(start_error)
                if not started:
                    started = True
                    try:
                        session.start()
                    except Exception as exc:
                        start_error = str(exc)
                        raise
                session.check()
                flow_folder = folder/flow.id
                flow_folder.mkdir(exist_ok=True)
                detail = flow.run(session, flow_folder, pending)
                outcomes = detail.get('rewards', {})
                # Silent omissions never become successful/exhausted features.
                for reward in pending:
                    row['rewards'][reward] = outcomes.get(reward, blocked('Enabled reward omitted by flow.'))
                detail['result'] = 'COMPLETE' if all(complete(row['rewards'][r]) for r in flow.rewards) else 'BLOCKED'
                row['flows'][flow.id] = detail
                row['new_claims'] += sum(outcomes.get(r, {}).get('claim_count', int(bool(outcomes.get(r, {}).get('claim_dispatched')))) for r in pending)
                row['recovery_ok'] = detail.get('return_home') == 'SUCCESS'
                if 'shop_traversal' in detail:
                    row['shop_traversal'] = detail['shop_traversal']
            except Exception as exc:  # noqa: BLE001 - every independent flow still gets a terminal result
                row['flows'][flow.id] = dict(result='BLOCKED', error=f'{type(exc).__name__}: {exc}')
                for reward in pending:
                    row['rewards'][reward] = blocked(exc)
                row['recovery_ok'] = False
            persist()
        if not started and not prior and row['rewards'] and all(
                complete(r) for r in row['rewards'].values()):
            row['recovery_ok'] = True  # Nothing required lifecycle or navigation.
        # Recovery-only resume never calls reward adapters again.
        if row['rewards'] and all(r['result'] in {'DISABLED', 'NOT_APPLICABLE'} for r in row['rewards'].values()):
            row['recovery_ok'] = True
        if prior and not started and not start_error and not row['recovery_ok'] and any(f.enabled and f.supported for f in plan):
            started = True
            session.start()
            recovery, _, _ = session.recover()
            row['recovery_ok'] = recovery.status.value in {'SUCCESS', 'ALREADY_HOME'}
    except Exception as exc:  # noqa: BLE001 - cleanup is independent of plan errors
        row['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if started:
            lifecycle = session.close()
            row.update(session=lifecycle, cleanup=lifecycle['cleanup'], selection_restored=lifecycle['selection_restored'])
        if start_error:
            row['error'] = start_error
        for reward in required:
            row['rewards'].setdefault(reward, blocked(row.get('error', 'Plan did not finish.')))
        row['result'] = 'COMPLETE' if (not row.get('error') and row['recovery_ok']
            and row['cleanup'] in {'SUCCESS', 'NOT_REQUIRED'} and row['selection_restored']
            and all(complete(row['rewards'][r]) for r in required)) else 'PARTIAL'
        persist()
    return row


def run(manager, data, *, random_test=False, resume_report=None, registry=None, enabled=None,
        identity_reader=persistent_identity, session_factory=InstanceSession, targets=None,
        temporary_selection=True, cancelled=lambda: False, exclude=(), preserve_possible=(), resume_indexes=(), resume_flows=(), refresh_flows=(), only_flows=()):
    registry = registry or production_registry()
    before = inventory(manager)
    previous = json.loads(Path(resume_report).read_text(encoding='utf-8')) if resume_report else None
    if previous and (previous.get('schema') != 'instance-first-v1' or previous.get('max_concurrency') != 1):
        raise SafetyError('Resume requires an original global instance-first snapshot.')
    if previous and (random_test or targets is not None):
        raise SafetyError('Cannot widen a resumed fleet snapshot.')
    if previous:
        if enabled is not None and enabled != previous.get('enabled_config', {}):
            raise SafetyError('Resume cannot change the original enabled configuration.')
        enabled = previous.get('enabled_config', {})
    # An explicit continuation scope narrows the frozen registry without changing
    # normal Run Selected configuration or reopening unrelated historical blockers.
    inherited_scope = previous.get('execution_flows', []) if previous and previous.get('scope_limited') else []
    if resume_flows:
        known = {f.id for f in registry.snapshot(enabled)}
        original = {p['flow'] for a in previous.get('accounts', []) for p in a.get('plan', [])} if previous else set()
        if (not previous or len(set(resume_flows)) != len(resume_flows)
                or any(not isinstance(f, str) for f in resume_flows)
                or set(resume_flows) - (known & original)
                or (inherited_scope and set(resume_flows) - set(inherited_scope))):
            raise SafetyError('Continuation flows must narrow the original registered scope.')
    elif inherited_scope:
        resume_flows = tuple(inherited_scope)
    if only_flows:
        known = {f.id for f in registry.snapshot(enabled)}
        if (len(set(only_flows)) != len(only_flows) or set(only_flows)-known
                or (inherited_scope and set(only_flows)-set(inherited_scope))):
            raise SafetyError('Explicit flow allowlist must be unique, registered and within inherited scope.')
    execution_plan = tuple(f for f in registry.snapshot(enabled)
        if (not resume_flows or f.id in resume_flows) and (not only_flows or f.id in only_flows))
    if refresh_flows:
        refreshable = {f.id for f in execution_plan if f.enabled and f.supported and f.refresh_current_batches}
        if (not previous or not resume_indexes or len(set(refresh_flows)) != len(refresh_flows)
                or set(refresh_flows) - refreshable):
            raise SafetyError('Fresh batch inspection requires explicit resumed targets and batch-capable flows.')
    # Exceptions are opt-in on every resume, never inherited as generic completion.
    if previous and set(previous.get('preserved_possible_claims', [])) - set(preserve_possible):
        raise SafetyError('Resume must explicitly retain previously authorized POSSIBLE exceptions.')
    if resume_indexes:
        if (not previous or len(set(resume_indexes)) != len(resume_indexes)
                or any(type(i) is not int for i in resume_indexes)
                or set(resume_indexes) - {t['index'] for t in previous['targets']}):
            raise SafetyError('Continuation indexes must be unique members of the original snapshot.')
        old_accounts = {a['index']: a for a in previous['accounts']}
        if any(old_accounts.get(t['index'], {}).get('result') != 'COMPLETE'
               for t in previous['targets'] if t['index'] not in resume_indexes):
            raise SafetyError('Only completed accounts can be retained without execution.')
    eligible = candidates(before)
    chosen = None
    if previous:
        targets = previous['targets']
    elif random_test:
        # Additional development checks must use a different live eligible account.
        used = set(exclude)
        history = []
        for path in (data/'diagnostics/tasks').glob('*/*/fleet-report.json'):
            old = json.loads(path.read_text(encoding='utf-8'))
            if old.get('mode') == 'random-test' and old.get('random_target'):
                history.append((path.parent.name, old['random_target']['index']))
        if history:
            used.add(max(history)[1])
        chosen, eligible = choose_random(before, exclude=used)
        targets = [chosen]
    elif targets is None:
        targets = eligible
    if len({t['index'] for t in targets}) != len(targets):
        raise SafetyError('Ambiguous instance snapshot.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%fZ')+'-'+uuid4().hex[:8]
    folder = data/'diagnostics/tasks/automation'/stamp
    folder.mkdir(parents=True, exist_ok=False)
    report = dict(schema='instance-first-v1', mode='resume' if previous else 'random-test' if random_test else 'fleet',
        max_concurrency=1, before_instances=before, targets=targets,
        required_rewards=[r for f in execution_plan for r in f.rewards],
        execution_flows=[f.id for f in execution_plan],
        scope_limited=bool(resume_flows or only_flows), explicit_flow_allowlist=list(only_flows), refresh_flows=list(refresh_flows),
        enabled_config=enabled or {}, eligible_candidates=eligible, random_target=chosen,
        random_method='secrets.choice' if random_test else None,
        resumed_from=str(resume_report) if previous else None, accounts=[])
    path = folder/'fleet-report.json'
    for target in targets:
        try:
            live = [r for r in before if r['index'] == target['index']]
            if len(live) != 1 or live[0]['protected']:
                raise SafetyError('Original target is missing or Protected.')
            target['preflight_running'] = live[0]['status'] == 'running'
            identity = identity_reader(manager, target['index'])
            if previous and target.get('persistent_identity') != identity:
                raise SafetyError('Original persistent identity changed.')
            if live[0]['name'] != target['name']:
                if not previous:
                    raise SafetyError('Explicit target name changed before its snapshot.')
                # User-owned display labels can change between sessions. Only
                # the SAME verified backing disk permits binding the fresh name.
                previous_name = target['name']
                target['historical_names'] = sorted(set(target.get('historical_names', [])) | {previous_name})
                target['name'] = live[0]['name']
                report.setdefault('observed_name_changes', []).append(dict(index=target['index'],
                    previous_name=previous_name,current_name=target['name'],persistent_identity=identity,
                    ldplayer_name_modified=False))
            target['persistent_identity'] = identity
            target.pop('identity_error', None)
        except (SafetyError, OSError, ValueError) as exc:
            target['identity_error'] = str(exc)
    if resume_indexes and any(t.get('identity_error') for t in targets if t['index'] not in resume_indexes):
        raise SafetyError('Retained account identity is no longer valid.')
    report['execution_indexes'] = list(resume_indexes) if resume_indexes else [t['index'] for t in targets]
    report['retained_completed_indexes'] = [t['index'] for t in targets if resume_indexes and t['index'] not in resume_indexes]
    exceptions = preserved_claims(manager, previous, targets, preserve_possible)
    report['preserved_possible_claims'] = list(exceptions)
    report['acceptance_exceptions'] = list(exceptions.values())
    write(path, report)
    old = {r['index']: r for r in previous['accounts']} if previous else {}
    for target in targets:
        if resume_indexes and target['index'] not in resume_indexes:
            row = dict(old[target['index']], name=target['name'], new_claims=0,
                       cleanup='NOT_REQUIRED', selection_restored=True,
                       retained_from=str(resume_report))
            row.pop('session', None)
            row['flows'] = {key: dict(result='RETAINED_COMPLETE') for key in row.get('flows', {})}
            report['accounts'].append(row)
            write(path, report)
            continue  # No session, selection, recovery, feature or lifecycle for retained accounts.
        progress(f"INSTANCE START #{target['index']} / {target['name']}")
        row = execute_instance(manager, data, target, folder/str(target['index']), registry,
            prior=old.get(target['index']), enabled=enabled, session_factory=session_factory,
            identity_reader=identity_reader, temporary_selection=temporary_selection, cancelled=cancelled,
            preserve_possible=tuple(cid for cid, proof in exceptions.items() if proof['index'] == target['index']),
            resume_flows=resume_flows, refresh_flows=refresh_flows, only_flows=only_flows)
        report['accounts'].append(row)
        write(path, report)
        progress(f"INSTANCE END #{target['index']}: {row['result']}")
    # A preserved journal must remain byte-for-byte unchanged throughout the run.
    final_exceptions = preserved_claims(manager, previous, targets, preserve_possible)
    report['preserved_journals_unchanged'] = final_exceptions == exceptions
    report['after_instances'] = inventory(manager)
    report['all_selection_states_restored'] = {r['index']: r['selected'] for r in before} == {
        r['index']: r['selected'] for r in report['after_instances']}
    report['protected_state_unchanged'] = all(r in report['after_instances'] for r in before if r['protected'])
    report['instance_names_unchanged'] = {r['index']: r['name'] for r in before} == {
        r['index']: r['name'] for r in report['after_instances']}
    report['result'] = 'PASS' if (targets and all(r['result'] == 'COMPLETE' for r in report['accounts'])
        and report['all_selection_states_restored'] and report['protected_state_unchanged']
        and report['instance_names_unchanged'] and report['preserved_journals_unchanged']) else 'PARTIAL'
    write(path, report)
    progress(f'AUTOMATION REPORT: {path}')
    return report
