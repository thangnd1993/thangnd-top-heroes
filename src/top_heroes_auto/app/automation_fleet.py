"""Global instance-first scheduler: snapshot flows, exhaust each, cleanup once."""
import json
from datetime import datetime, timezone
from pathlib import Path

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
from top_heroes_auto.automation.guard import SafetyError


def blocked(error):
    return dict(result='BLOCKED', claim_dispatched=False, journal='NONE', error=str(error))


def execute_instance(manager, data, target, folder, registry, *, prior=None, enabled=None,
                     session_factory=InstanceSession, identity_reader=persistent_identity,
                     temporary_selection=True, cancelled=lambda: False):
    prior = prior or {}
    plan = registry.snapshot(enabled)
    required = tuple(r for flow in plan for r in flow.rewards)
    row = dict(index=target['index'], name=target['name'], result='PARTIAL',
        plan=[dict(flow=f.id, rewards=list(f.rewards), enabled=f.enabled, supported=f.supported) for f in plan],
        rewards={k: v for k, v in prior.get('rewards', {}).items() if k in required}, flows={},
        cleanup='NOT_REQUIRED', selection_restored=True, recovery_ok=prior.get('recovery_ok', False), new_claims=0)
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
            except Exception as exc:  # noqa: BLE001 - invalid applicability cannot omit later independent flows
                row['flows'][flow.id] = dict(result='BLOCKED', error=str(exc))
                for reward in flow.rewards:
                    row['rewards'][reward] = blocked(exc)
                persist()
                continue
            if status:
                row['flows'][flow.id] = dict(result=status, error='Unsupported flow.' if status == 'BLOCKED' else None)
                for reward in flow.rewards:
                    row['rewards'].setdefault(reward, dict(result=status, journal='NONE', claim_dispatched=False))
                persist()
                continue
            pending = tuple(r for r in flow.rewards if row['rewards'].get(r, {}).get('result') not in COMPLETE-{'DISABLED', 'NOT_APPLICABLE'})
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
                detail['result'] = 'COMPLETE' if all(row['rewards'][r]['result'] in COMPLETE for r in flow.rewards) else 'BLOCKED'
                row['flows'][flow.id] = detail
                row['new_claims'] += sum(bool(outcomes.get(r, {}).get('claim_dispatched')) for r in pending)
                row['recovery_ok'] = detail.get('return_home') == 'SUCCESS'
                if 'shop_traversal' in detail:
                    row['shop_traversal'] = detail['shop_traversal']
            except Exception as exc:  # noqa: BLE001 - every independent flow still gets a terminal result
                row['flows'][flow.id] = dict(result='BLOCKED', error=f'{type(exc).__name__}: {exc}')
                for reward in pending:
                    row['rewards'][reward] = blocked(exc)
                row['recovery_ok'] = False
            persist()
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
            and all(r['result'] in COMPLETE for r in row['rewards'].values())) else 'PARTIAL'
        persist()
    return row


def run(manager, data, *, random_test=False, resume_report=None, registry=None, enabled=None,
        identity_reader=persistent_identity, session_factory=InstanceSession, targets=None,
        temporary_selection=True, cancelled=lambda: False, exclude=()):
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
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%fZ')
    folder = data/'diagnostics/tasks/automation'/stamp
    folder.mkdir(parents=True, exist_ok=False)
    report = dict(schema='instance-first-v1', mode='resume' if previous else 'random-test' if random_test else 'fleet',
        max_concurrency=1, before_instances=before, targets=targets,
        required_rewards=[r for f in registry.snapshot(enabled) for r in f.rewards],
        enabled_config=enabled or {}, eligible_candidates=eligible, random_target=chosen,
        random_method='secrets.choice' if random_test else None,
        resumed_from=str(resume_report) if previous else None, accounts=[])
    path = folder/'fleet-report.json'
    for target in targets:
        try:
            live = [r for r in before if r['index'] == target['index']]
            if len(live) != 1 or live[0]['name'] != target['name'] or live[0]['protected']:
                raise SafetyError('Original target is missing, changed or Protected.')
            identity = identity_reader(manager, target['index'])
            if previous and target.get('persistent_identity') != identity:
                raise SafetyError('Original persistent identity changed.')
            target['persistent_identity'] = identity
            target.pop('identity_error', None)
        except (SafetyError, OSError, ValueError) as exc:
            target['identity_error'] = str(exc)
    write(path, report)
    old = {r['index']: r for r in previous['accounts']} if previous else {}
    for target in targets:
        progress(f"INSTANCE START #{target['index']} / {target['name']}")
        row = execute_instance(manager, data, target, folder/str(target['index']), registry,
            prior=old.get(target['index']), enabled=enabled, session_factory=session_factory,
            identity_reader=identity_reader, temporary_selection=temporary_selection, cancelled=cancelled)
        report['accounts'].append(row)
        write(path, report)
        progress(f"INSTANCE END #{target['index']}: {row['result']}")
    report['after_instances'] = inventory(manager)
    report['all_selection_states_restored'] = {r['index']: r['selected'] for r in before} == {
        r['index']: r['selected'] for r in report['after_instances']}
    report['protected_state_unchanged'] = all(r in report['after_instances'] for r in before if r['protected'])
    report['instance_names_unchanged'] = {r['index']: r['name'] for r in before} == {
        r['index']: r['name'] for r in report['after_instances']}
    report['result'] = 'PASS' if (targets and all(r['result'] == 'COMPLETE' for r in report['accounts'])
        and report['all_selection_states_restored'] and report['protected_state_unchanged']
        and report['instance_names_unchanged']) else 'PARTIAL'
    write(path, report)
    progress(f'AUTOMATION REPORT: {path}')
    return report
