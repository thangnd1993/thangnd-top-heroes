"""Global instance-first scheduler: snapshot flows, exhaust each, cleanup once."""
import json
import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from top_heroes_auto.app.automation_ownership import exclusive_automation, ownership_evidence
from top_heroes_auto.app.build_identity import build_identity
from top_heroes_auto.app.bxh_shop_acceptance import (
    candidates,
    choose_random,
    inventory,
    persistent_identity,
    progress,
    write,
)
from top_heroes_auto.app.flow_registry import COMPLETE, FlowRegistry, production_registry
from top_heroes_auto.app.instance_session import InstanceSession
from top_heroes_auto.app.resume_exception import preserved_claims
from top_heroes_auto.automation import timing
from top_heroes_auto.automation.execution_plan import terminal_plan
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.ldplayer.name_safety import name_write_attempts


def blocked(error):
    return dict(result='BLOCKED', claim_dispatched=False, journal='NONE', error=str(error))


def execute_instance(manager, data, target, folder, registry, *, prior=None, enabled=None,
                     session_factory=InstanceSession, identity_reader=persistent_identity,
                     temporary_selection=True, cancelled=lambda: False, preserve_possible=(), resume_flows=(), refresh_flows=(), only_flows=(), peer_identities=()):
    timing.reset()
    from top_heroes_auto.app.log_context import instance_index

    instance_index.set(target['index'])
    prior = prior or {}
    full_plan = registry.snapshot(enabled)
    plan = tuple(f for f in full_plan if (not resume_flows or f.id in resume_flows)
                 and (not only_flows or f.id in only_flows))
    required = tuple(r for flow in plan for r in flow.rewards)
    row = dict(index=target['index'], name=target['name'], stable_instance_id=target.get('persistent_identity'),
        ldplayer_name_write_attempts=0, starting_display_label=target['name'], ending_display_label=target['name'], result='PARTIAL',
        plan=[dict(flow=f.id, rewards=list(f.rewards), enabled=f.enabled, supported=f.supported) for f in plan],
        rewards=dict(prior.get('rewards', {})), flows={},
        cleanup='NOT_REQUIRED', selection_restored=True, recovery_ok=prior.get('recovery_ok', False), new_claims=0)
    row['timing_seconds'] = dict(startup_and_initial_home=0.0, flows={}, cleanup=0.0)
    monthly = row['rewards'].get('shop-monthly-privilege-gift')
    if monthly and monthly.get('result') in COMPLETE and 'shop-monthly-daily' not in monthly.get('children', {}):
        row['rewards']['shop-monthly-privilege-gift'] = dict(monthly,
            prior_result=monthly['result'], result='LEGACY_COVERAGE_INCOMPLETE',
            error='Legacy upper/bulk result did not inspect the independent lower daily reward.')
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
    row['transitions'] = []
    def event(flow, state, message):
        row['transitions'].append(dict(time=datetime.now(timezone.utc).isoformat(),
            monotonic=time.perf_counter(), worker=threading.current_thread().name,
            flow=flow, state=state, message=message))
        logging.getLogger('top_heroes_auto').info('[%s / #%s] %s', target['name'], target['index'], message,
            extra={'category': 'operation', 'ui_index': target['index'], 'ui_flow': flow, 'ui_state': state})
    def persist():
        write(folder/'account-report.json', row)
    persist()  # The execution plan is durable BEFORE selection/lifecycle mutation.
    if target.get('identity_error'):
        row['error'] = target['identity_error']
        row['rewards'].update({r: blocked(row['error']) for r in required})
        row['flows'] = {f.id: dict(result='BLOCKED', error=row['error'], blocking_stage='identity_preflight') for f in plan}
        row['execution_plan_summary'] = dict(terminal=True, no_mutation=True, blocker=row['error'])
        persist()
        return row
    session = session_factory(manager, data, target, folder, identity_reader=identity_reader,
        temporary_selection=temporary_selection, cancelled=cancelled, execution_plan=plan)
    session.fleet_peer_identities = dict(peer_identities)
    started = False
    if all(not f.enabled for f in plan):
        row['recovery_ok'] = True
    start_error = target.get('identity_error')
    try:
        for flow in plan:
            if cancelled():
                row['flows'][flow.id] = dict(result='BLOCKED', blocking_stage='cancelled',
                    error='Run cancelled before feature dispatch.', no_input=True)
                for reward in flow.rewards:
                    row['rewards'].setdefault(reward, blocked('Run cancelled before feature dispatch.'))
                persist()
                continue
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
                if getattr(session, 'navigation_blocked', None):
                    for reward in pending:
                        row['rewards'][reward] = dict(blocked(session.navigation_blocked), result='NOT_RUN_TARGET_BLOCKED')
                    row['flows'][flow.id] = dict(result='NOT_RUN_TARGET_BLOCKED', error=session.navigation_blocked,
                                                no_input=True)
                    recoveries = getattr(session, 'report', {}).get('recoveries', [])
                    if recoveries:
                        row['flows'][flow.id].update(blocking_stage='before_home',
                            recovery=recoveries[-1]['status'], recovery_report=recoveries[-1]['report'])
                    persist()
                    continue
                if not started:
                    started = True
                    startup_clock = time.perf_counter()
                    try:
                        session.start()
                    except Exception as exc:
                        start_error = str(exc)
                        raise
                    finally:
                        row['timing_seconds']['startup_and_initial_home'] = round(time.perf_counter()-startup_clock, 3)
                session.check()
                flow_folder = folder/flow.id
                flow_folder.mkdir(exist_ok=True)
                flow_clock = time.perf_counter()
                label = {'guild':'Hội', 'mail':'Thư', 'shop':'Tiệm', 'ranking':'BXH',
                         'vip':'VIP', 'idle':'quà tích lũy', 'events':'Sự kiện'}.get(flow.id, flow.id)
                event(flow.id, 'STARTED', f'Đang xử lý {label}.')
                try:
                    detail = flow.run(session, flow_folder, pending)
                finally:
                    row['timing_seconds']['flows'][flow.id] = round(time.perf_counter()-flow_clock, 3)
                outcomes = detail.get('rewards', {})
                detail['omitted_rewards'] = [r for r in pending if r not in outcomes]
                # Silent omissions never become successful/exhausted features.
                for reward in pending:
                    row['rewards'][reward] = outcomes.get(reward, blocked('Enabled reward omitted by flow.'))
                detail['result'] = 'COMPLETE' if all(complete(row['rewards'][r]) for r in flow.rewards) else 'BLOCKED'
                row['flows'][flow.id] = detail
                event(flow.id, detail['result'], f"{flow.id}: {detail['result']}; kết quả đã lưu.")
                row['new_claims'] += sum(outcomes.get(r, {}).get('claim_count', int(bool(outcomes.get(r, {}).get('claim_dispatched')))) for r in pending)
                row['recovery_ok'] = detail.get('return_home') == 'SUCCESS'
                if 'shop_traversal' in detail:
                    row['shop_traversal'] = detail['shop_traversal']
            except Exception as exc:  # noqa: BLE001 - every independent flow still gets a terminal result
                row['flows'][flow.id] = dict(result='BLOCKED', error=f'{type(exc).__name__}: {exc}',
                    error_source=[dict(file=Path(f.filename).name, line=f.lineno, function=f.name)
                                  for f in traceback.extract_tb(exc.__traceback__)[-5:]])
                event(flow.id, 'BLOCKED', f'{flow.id}: bị chặn ({exc}); kiểm tra an toàn trước mục tiếp theo.')
                recoveries = session.report.get('recoveries', []) if hasattr(session, 'report') else []
                if recoveries and recoveries[-1]['status'] not in {'SUCCESS', 'ALREADY_HOME'}:
                    row['flows'][flow.id].update(blocking_stage='before_home', recovery=recoveries[-1]['status'],
                                                recovery_report=recoveries[-1]['report'])
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
        summary = terminal_plan(plan, row['flows'], row['rewards'])
        row['execution_plan_summary'] = summary
        if started:
            session.finish_plan(row['flows'], row['rewards'])
            cleanup_clock = time.perf_counter()
            lifecycle = session.close()
            row['timing_seconds']['cleanup'] = round(time.perf_counter()-cleanup_clock, 3)
            row.update(session=lifecycle, cleanup=lifecycle['cleanup'], selection_restored=lifecycle['selection_restored'],
                       ldplayer_name_write_attempts=lifecycle.get('ldplayer_name_write_attempts', 0),
                       starting_display_label=lifecycle.get('starting_display_label', target['name']),
                       ending_display_label=lifecycle.get('ending_display_label', target['name']))
        if start_error:
            row['error'] = start_error
        for reward in required:
            row['rewards'].setdefault(reward, blocked(row.get('error', 'Plan did not finish.')))
        row['result'] = 'COMPLETE' if (summary['terminal'] and not row.get('error') and row['recovery_ok']
            and row['cleanup'] in {'SUCCESS', 'NOT_REQUIRED'} and row['selection_restored']
            and all(complete(row['rewards'][r]) for r in required)) else 'PARTIAL'
        row['operation_metrics'] = timing.snapshot()
        persist()
    return row


@exclusive_automation
def run(manager, data, *, random_test=False, resume_report=None, registry=None, enabled=None,
        identity_reader=persistent_identity, session_factory=InstanceSession, targets=None,
        temporary_selection=True, cancelled=lambda: False, exclude=(), preserve_possible=(), resume_indexes=(), resume_flows=(), refresh_flows=(), only_flows=(),
        max_concurrency=1, manager_factory=None, account_started=lambda target: None,
        account_finished=lambda row: None, cancellation_factory=None,
        run_id=None, origin='development', report_created=lambda path: None):
    if type(max_concurrency) is not int or max_concurrency not in (1, 2):
        raise SafetyError('Explicit concurrency must be one or two accounts.')
    source_registry = registry or production_registry()
    registry = FlowRegistry()
    for flow in source_registry.snapshot():
        registry.register(flow)  # Freeze once before any worker starts.
    name_writes_before = name_write_attempts()
    before = inventory(manager)
    previous = json.loads(Path(resume_report).read_text(encoding='utf-8')) if resume_report else None
    if previous and (previous.get('schema') != 'instance-first-v1' or previous.get('max_concurrency') not in (1, 2)):
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
    excluded_random_indexes = []
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
        excluded_random_indexes = sorted(used)
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
        max_concurrency=max_concurrency, before_instances=before, targets=targets,
        automation_ownership=ownership_evidence(),
        required_rewards=[r for f in execution_plan for r in f.rewards],
        execution_flows=[f.id for f in execution_plan],
        scope_limited=bool(resume_flows or only_flows), explicit_flow_allowlist=list(only_flows), refresh_flows=list(refresh_flows),
        enabled_config=enabled or {}, eligible_candidates=eligible, random_target=chosen,
        random_method='secrets.choice' if random_test else None,
        excluded_random_indexes=excluded_random_indexes,
        resumed_from=str(resume_report) if previous else None, accounts=[])
    path = folder/'fleet-report.json'
    report['report_path'] = str(path)
    report['runtime'] = build_identity()
    report.update(run_id=run_id, origin=origin, started_at=datetime.now(timezone.utc).isoformat())
    write(path, report)
    report_created(str(path))  # Available after interruption, before any account starts.
    for target in targets:
        try:
            live = [r for r in before if r['index'] == target['index']]
            if len(live) != 1 or live[0]['protected']:
                raise SafetyError('Original target is missing or Protected.')
            target['preflight_running'] = live[0]['status'] == 'running'
            identity = identity_reader(manager, target['index'])
            if target.get('persistent_identity') and target['persistent_identity'] != identity:
                raise SafetyError('Original persistent identity changed.')
            if live[0]['name'] != target['name']:
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
    pending = []
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
        pending.append(target)

    # A Manager owns mutable active transport/lifecycle state. Never share it
    # between concurrent accounts, even though its individual methods lock.
    workers = [manager] * len(pending)
    if max_concurrency == 2:
        factory = manager_factory or manager.fork_worker
        workers = [factory() for _ in pending]
        if (len({id(m) for m in [manager, *workers]}) != len(workers) + 1
                or any(m.namespace != manager.namespace
                       or m.store.path.resolve() != manager.store.path.resolve() for m in workers)):
            raise SafetyError('Concurrent workers require separate Managers in the same fleet/store.')

    queued_clock = time.perf_counter()

    def execute(worker, target):
        started_at = datetime.now(timezone.utc).isoformat()
        started_clock = time.perf_counter()
        target_cancelled = cancellation_factory(target['index']) if cancellation_factory else cancelled
        account_started(target)
        progress(f"INSTANCE START #{target['index']} / {target['name']}")
        current = dict(target)
        if target_cancelled():
            current['identity_error'] = 'Run cancelled before account dispatch.'
        try:
            row = execute_instance(worker, data, current, folder/str(target['index']), registry,
                prior=old.get(target['index']), enabled=enabled, session_factory=session_factory,
                identity_reader=identity_reader, temporary_selection=temporary_selection, cancelled=target_cancelled,
                preserve_possible=tuple(cid for cid, proof in exceptions.items() if proof['index'] == target['index']),
                resume_flows=resume_flows, refresh_flows=refresh_flows, only_flows=only_flows,
                peer_identities=tuple((t['index'], t['persistent_identity']) for t in pending
                                      if max_concurrency == 2 and t['index'] != target['index']
                                      and not t.get('identity_error')))
        except Exception as exc:  # noqa: BLE001 - target worker exits; other bound workers remain independent
            account_path = folder/str(target['index'])/'account-report.json'
            row = json.loads(account_path.read_text(encoding='utf-8')) if account_path.is_file() else dict(
                index=target['index'], name=target['name'], rewards={}, flows={}, new_claims=0)
            row.update(result='PARTIAL', error=f'{type(exc).__name__}: {exc}',
                       cleanup='DEFERRED_OWNERSHIP_UNPROVEN', selection_restored=False,
                       worker_terminated=True)
            account_path.parent.mkdir(parents=True, exist_ok=True)
        row.update(worker_started_at=started_at, worker_finished_at=datetime.now(timezone.utc).isoformat(),
                   automation_ownership=ownership_evidence(), worker=threading.current_thread().name,
                   elapsed_seconds=round(time.perf_counter()-started_clock, 3),
                   queue_wait_seconds=round(started_clock-queued_clock, 3))
        row['transport_metrics'] = getattr(worker.ld.process, 'metrics', {})
        write(folder/str(target['index'])/'account-report.json', row)
        progress(f"INSTANCE END #{target['index']}: {row['result']}")
        return row

    def record(row):
        # Only the owning thread writes the fleet report. Account evidence is
        # isolated in its indexed folder and the existing journal transactions.
        report['accounts'].append(row)
        positions = {t['index']: i for i, t in enumerate(targets)}
        report['accounts'].sort(key=lambda r: positions[r['index']])
        if row['cleanup'] in {'OWNERSHIP_UNKNOWN', 'DEFERRED_OWNERSHIP_UNPROVEN'}:
            report.setdefault('deferred_cleanup_indexes', []).append(row['index'])
        write(path, report)
        account_finished(row)

    if max_concurrency == 1:
        for worker, target in zip(workers, pending, strict=True):
            record(execute(worker, target))
    else:
        # The parent retains ONE kernel fleet lease until all worker cleanup
        # finishes. Each task receives its own context with that same live lease,
        # following the existing lifecycle queue's ownership propagation.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix='automation-account') as pool:
            futures = [pool.submit(copy_context().run, execute, worker, target)
                       for worker, target in zip(workers, pending, strict=True)]
            for future in as_completed(futures):
                record(future.result())
    # A preserved journal must remain byte-for-byte unchanged throughout the run.
    final_exceptions = preserved_claims(manager, previous, targets, preserve_possible)
    report['preserved_journals_unchanged'] = final_exceptions == exceptions
    report['after_instances'] = inventory(manager)
    report['identity_migration_audit'] = manager.store.identity_audit(manager.namespace)
    report['all_selection_states_restored'] = {r['index']: r['selected'] for r in before} == {
        r['index']: r['selected'] for r in report['after_instances']}
    report['protected_state_unchanged'] = all(any(
        a['index'] == r['index'] and a['stable_id'] == r['stable_id'] and a['protected'] and not a['selected']
        and a['status'] == r['status'] for a in report['after_instances']) for r in before if r['protected'])
    report['protected_flags_unchanged'] = all(any(
        a['index'] == r['index'] and a['stable_id'] == r['stable_id']
        and a['protected'] == r['protected'] and a['selected'] == r['selected']
        for a in report['after_instances']) for r in before if r['protected'])
    report['protected_runtime_changes'] = [dict(index=r['index'], before=r['status'], after=a['status'],
        cause='UNPROVEN') for r in before if r['protected'] for a in report['after_instances']
        if a['index'] == r['index'] and a['status'] != r['status']]
    report['instance_names_unchanged'] = {r['index']: r['name'] for r in before} == {
        r['index']: r['name'] for r in report['after_instances']}
    report['ldplayer_name_write_attempts'] = name_write_attempts() - name_writes_before
    intervals = [(r['worker_started_at'], 1) for r in report['accounts'] if r.get('worker_started_at') and not r.get('retained_from')]
    intervals += [(r['worker_finished_at'], -1) for r in report['accounts'] if r.get('worker_finished_at') and not r.get('retained_from')]
    active = peak = 0
    for _, change in sorted(intervals):
        active += change
        peak = max(peak, active)
    report['peak_worker_concurrency'] = peak
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    report['result'] = 'PASS' if (targets and all(r['result'] == 'COMPLETE' for r in report['accounts'])
        and report['all_selection_states_restored'] and report['protected_state_unchanged']
        and report['ldplayer_name_write_attempts'] == 0 and report['preserved_journals_unchanged']) else 'PARTIAL'
    write(path, report)
    progress(f'AUTOMATION REPORT: {path}')
    return report
