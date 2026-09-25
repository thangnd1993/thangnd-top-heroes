"""Explicit BXH/shop acceptance; normal Run Selected scope is not widened."""
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.app.diagnostic import _instance, _view
from top_heroes_auto.app.fixed_reward_port import FixedRewardPort, TabNotFound
from top_heroes_auto.app.recovery_cli import RecoveryFailure, run_home_recovery
from top_heroes_auto.automation.fixed_reward_claims import process_reward
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.recovery import RecoveryStatus
from top_heroes_auto.vision.fixed_rewards import REWARDS, SHOP_REWARDS

MANDATORY_PROTECTED = frozenset({'Queen', 'anh Ry', 'Chicken', 'Happy'})
COMPLETE_REWARDS = frozenset({'SUCCESS', 'NOT_AVAILABLE', 'ALREADY_VERIFIED'})


def write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def persistent_identity(manager, index):
    """Read-only disk continuity in addition to indexed ADB + boot verification.

    LDPlayer Machine UUIDs encode its index, so UUID alone cannot detect reuse.
    The backing data file identity and creation time must also remain stable.
    No file contents/credentials are read and display-name changes do not affect it.
    """
    if type(index) is not int or index < 0:
        raise SafetyError('Invalid target index.')
    root = manager.ld.installation.console.parent / 'vms'
    # A default console label after a damaged/missing instance config must not
    # silently become a new authorized identity on the next fleet snapshot.
    config = json.loads((root / 'config' / f'leidian{index}.config').read_text(encoding='utf-8-sig'))
    configured_name = config.get('statusSettings.playerName')
    if not configured_name or configured_name != manager.query(index).name:
        raise SafetyError('Persistent instance name unavailable or mismatched; no lifecycle/input permitted.')
    path = root / f'leidian{index}' / 'data.vmdk'
    stat = path.stat()
    created = getattr(stat, 'st_birthtime_ns', None)
    if created is None or not stat.st_ino:
        raise SafetyError('Persistent disk identity unavailable; index reuse cannot be ruled out.')
    return hashlib.sha256(f'{path.resolve()}:{stat.st_dev}:{stat.st_ino}:{created}'.encode()).hexdigest()


def inventory(manager):
    rows = _view(manager, manager.refresh())
    for row in rows:
        if row['name'] in MANDATORY_PROTECTED and not row['protected']:
            raise SafetyError(f"Mandatory Protected account is not Protected: {row['name']}")
        if row['protected'] and row['selected']:
            raise SafetyError('Protected selection invariant violated.')
    return rows


def candidates(rows):
    return [dict(row) for row in rows if not row['protected'] and row['name'] not in MANDATORY_PROTECTED]


def choose_random(rows, *, choice=secrets.choice, exclude=()):
    eligible = [r for r in candidates(rows) if r['index'] not in exclude]
    if not eligible:
        raise SafetyError('No eligible untouched development target.')
    return choice(eligible), eligible


def run_account(manager, data, target, folder, *, rewards=REWARDS, cancelled=lambda: False,
                identity_reader=persistent_identity, port_factory=FixedRewardPort,
                recovery_runner=run_home_recovery, temporary_selection=True):
    index, name = target['index'], target['name']
    snapshot = RunSnapshot(manager.namespace, ((index, name),), True)
    row = dict(index=index, name=name, recovery='NOT_STARTED', adb=None,
               rewards={r: dict(result='NOT_STARTED', claim_dispatched=False, journal='NONE') for r in rewards},
               cleanup='NOT_REQUIRED', selection_restored=False, result='BLOCKED')
    # Report durable prior actions even when recovery fails before visiting a
    # reward. This is reporting only; no journal is rewritten or released.
    from top_heroes_auto.automation.fixed_reward_period import current_attempts

    prior_rows = manager.store.reward_claims(manager.namespace, index)
    for reward, outcome in row['rewards'].items():
        locked = current_attempts(prior_rows, reward)
        if locked:
            prior = locked[-1]
            outcome.update(journal=prior['status'], claim_id=prior['id'],
                           prior_dispatch_state=prior['dispatch_state'])
    folder.mkdir(parents=True, exist_ok=True)
    def persist():
        write(folder / 'account-report.json', row)
    selected_before = None
    changed_selection = False
    started = False
    cleanup_attempted = False
    task_id = None
    identity = target.get('persistent_identity')

    def check_identity():
        _instance(manager, index, name)
        if identity_reader(manager, index) != identity:
            raise SafetyError('Persistent target identity changed; no action or cleanup permitted.')

    try:
        _instance(manager, index, name)
        metadata = manager.store.metadata(manager.namespace, index)
        selected_before = metadata.selected
        if metadata.protected or name in MANDATORY_PROTECTED:
            raise SafetyError('Protected target excluded.')
        identity = identity or identity_reader(manager, index)
        check_identity()
        row['persistent_identity'] = identity
        if not metadata.selected:
            if not temporary_selection:
                raise SafetyError('Normal application task requires explicit selection.')
            manager.select(index, True)
            changed_selection = True
        task_id = manager.store.create_task_run(manager.namespace, 'bxh-shop-fixed', index, name)
        row['task_run_id'] = task_id
        persist()
        recovery, path, started = recovery_runner(manager, data, index, name, cleanup_owned=False,
                                                  cancelled=cancelled)
        row.update(recovery=recovery.status.value, recovery_report=str(path), adb=recovery.adb_target)
        if recovery.status not in {RecoveryStatus.SUCCESS, RecoveryStatus.ALREADY_HOME}:
            raise SafetyError(recovery.error or f'Recovery failed: {recovery.status.value}')
        row['recovery'] = 'SUCCESS'
        port = port_factory(manager, snapshot, index, name, folder, check_identity, cancelled)
        for reward in rewards:
            outcome = row['rewards'][reward]
            try:
                frame = port.home()
                if reward == 'ranking-chest':
                    frame = port.navigate(frame, 'avatar-frame', 'profile')
                    port.navigate(frame, 'profile-bxh', 'ranking')
                else:
                    port.open_shop_reward(frame, reward)
                process_reward(port, manager.store, manager.namespace, task_id, reward, identity, outcome, persist)
            except Exception as exc:  # noqa: BLE001 - each reward retains its own durable result
                if outcome['result'] in {'NOT_STARTED', 'RESERVED'}:
                    outcome['result'] = 'TAB_NOT_FOUND' if isinstance(exc, TabNotFound) else 'BLOCKED'
                outcome['error'] = f'{type(exc).__name__}: {exc}'
            persist()
        try:
            port.home()
            row['return_home'] = 'SUCCESS'
        except Exception as exc:  # noqa: BLE001 - never downgrade a VERIFIED reward
            row['return_home'] = f'FAILED: {exc}'
        row['actions'] = port.events
        good = {'SUCCESS', 'NOT_AVAILABLE', 'ALREADY_VERIFIED'}
        row['result'] = 'COMPLETE' if (
            all(r['result'] in good for r in row['rewards'].values()) and row['return_home'] == 'SUCCESS'
        ) else 'PARTIAL'
    except Exception as exc:  # noqa: BLE001 - persist and continue other authorized accounts
        row['error'] = f'{type(exc).__name__}: {exc}'
        if isinstance(exc, RecoveryFailure):
            started, cleanup_attempted = exc.started_by_run, exc.cleanup_attempted
            row['cleanup'] = 'SUCCESS' if exc.cleanup_succeeded else 'FAILED' if cleanup_attempted else 'NOT_REQUIRED'
            row['recovery_report'] = str(exc.report_path)
        for outcome in row['rewards'].values():
            if outcome['result'] == 'NOT_STARTED':
                outcome.update(result='BLOCKED', error=row['error'])
    finally:
        if started and not cleanup_attempted:
            try:
                check_identity()
                if manager.store.metadata(manager.namespace, index).protected:
                    raise SafetyError('Protection added; cleanup is revoked.')
                manager.execute(index, 'quit', snapshot=snapshot)
                row['cleanup'] = 'SUCCESS'
            except Exception as exc:  # noqa: BLE001 - do not override protection or retry quit
                row['cleanup'] = f'FAILED: {exc}'
        try:
            if changed_selection:
                check_identity()
                current = manager.store.metadata(manager.namespace, index)
                if current.selected != selected_before:
                    if current.protected:
                        raise SafetyError('Protection added; no selection restoration mutation allowed.')
                    manager.select(index, selected_before)
            row['selection_restored'] = manager.store.metadata(manager.namespace, index).selected == selected_before
        except Exception as exc:  # noqa: BLE001 - do not restore a reused/Protected index
            row['selection_error'] = str(exc)
        if not row['selection_restored'] or row['cleanup'].startswith('FAILED'):
            row['result'] = 'PARTIAL'
        persist()
        if task_id is not None:
            manager.store.finish_task_run(task_id, row['result'], error=row.get('error', ''),
                                          report_path=str(folder / 'account-report.json'))
    return row


def resume_plan(previous, live, rewards=REWARDS):
    """Keep the original snapshot; only unfinished rewards may be revisited."""
    if previous.get('mode') not in {'fleet', 'resume'} or 'after_instances' not in previous:
        raise SafetyError('Resume requires a completed fixed-flow fleet report.')
    targets = previous['targets']
    rows = {row['index']: row for row in previous['accounts']}
    if len(rows) != len(targets) or len({t['index'] for t in targets}) != len(targets):
        raise SafetyError('Original fleet snapshot is incomplete or ambiguous.')
    current = {row['index']: row for row in live}
    plan = []
    for target in targets:
        old = rows[target['index']]
        remaining = tuple(r for r in rewards if old.get('rewards', {}).get(r, {}).get('result') not in COMPLETE_REWARDS)
        if not remaining:
            continue
        now = current.get(target['index'])
        if not now or now['name'] != target['name'] or now['protected'] or now['name'] in MANDATORY_PROTECTED:
            # Preserve the blocker, without preventing independent accounts.
            plan.append((dict(target, identity_error='Resume target missing, renamed or Protected.'), remaining))
        else:
            plan.append((dict(target), remaining))
    return plan


def run_acceptance(manager, data: Path, *, random_test=False, account_runner=run_account,
                   identity_reader=persistent_identity, exclude=(), resume_report=None, rewards=REWARDS):
    if random_test and resume_report:
        raise SafetyError('Resume and random development test cannot be combined.')
    before = inventory(manager)
    eligible = candidates(before)
    selected = None
    if random_test:
        if not exclude:
            tested = []
            history = data/'diagnostics/tasks/bxh-shop-fixed'
            for previous in history.glob('*/fleet-report.json'):
                old = json.loads(previous.read_text(encoding='utf-8'))
                if old.get('mode') == 'random-test' and old.get('random_target'):
                    tested.append(old['random_target']['index'])
            exclude = tuple(tested)
        selected, eligible = choose_random(before, exclude=exclude)
    previous = json.loads(Path(resume_report).read_text(encoding='utf-8')) if resume_report else None
    targets = previous['targets'] if previous else [selected] if selected else eligible
    plan = resume_plan(previous, before, rewards) if previous else [(target, rewards) for target in targets]
    if previous:
        # Resolve older uncertainty first while its evidence remains fresh.
        # This orders accounts, never changes the immutable target/reward scope.
        def oldest_pending(item):
            target, rewards = item
            times = [r['reserved_at'] for r in manager.store.reward_claims(manager.namespace, target['index'])
                     if r['reward_id'] in rewards and r['status'] == 'RESERVED']
            return min(times, default='9999')
        plan.sort(key=oldest_pending)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%fZ')
    folder = data / 'diagnostics/tasks/bxh-shop-fixed' / stamp
    folder.mkdir(parents=True, exist_ok=False)
    report = dict(required_rewards=list(rewards), max_concurrency=1, mode='resume' if previous else 'random-test' if random_test else 'fleet',
                  random_method='secrets.choice' if random_test else None,
                  eligible_candidates=eligible, random_target=selected, before_instances=before,
                  excluded_protected=[r for r in before if r['protected']], targets=targets, accounts=[])
    if previous:
        report.update(resumed_from=str(Path(resume_report).resolve()), accounts=previous['accounts'],
                      resume_plan=[dict(index=t['index'], rewards=list(rewards)) for t, rewards in plan])
    for target, _ in plan:
        try:
            if 'identity_error' in target:
                continue
            identity = identity_reader(manager, target['index'])
            if previous and target.get('persistent_identity') != identity:
                raise SafetyError('Original snapshot disk identity changed.')
            target['persistent_identity'] = identity
        except (OSError, ValueError, SafetyError) as exc:
            target['identity_error'] = str(exc)
    path = folder / 'fleet-report.json'
    write(path, report)
    for target, rewards in plan:
        print(f"BXH/TIEM START #{target['index']} / {target['name']}", flush=True)
        try:
            if 'identity_error' in target:
                raise SafetyError(target['identity_error'])
            kwargs = dict(rewards=rewards) if previous or rewards != REWARDS else {}
            row = account_runner(manager, data, target, folder / str(target['index']), **kwargs)
        except Exception as exc:  # noqa: BLE001 - remaining snapshot members must still run
            row = dict(index=target['index'], name=target['name'], result='BLOCKED', error=str(exc))
        if previous:
            old = next(r for r in report['accounts'] if r['index'] == target['index'])
            history = list(old.get('attempt_history', [])) + [dict(old, attempt_history=[])]
            merged = {**old.get('rewards', {}), **row.get('rewards', {})}
            old.update(row, rewards=merged, attempt_history=history)
            old['result'] = 'COMPLETE' if (
                row['result'] == 'COMPLETE' and all(r.get('result') in COMPLETE_REWARDS for r in merged.values())
            ) else 'PARTIAL'
        else:
            report['accounts'].append(row)
        write(path, report)
        print(f"BXH/TIEM END #{target['index']}: {row['result']}", flush=True)
    report['after_instances'] = inventory(manager)
    report['all_selection_states_restored'] = {r['index']: r['selected'] for r in before} == {
        r['index']: r['selected'] for r in report['after_instances']}
    report['protected_state_unchanged'] = all(r in report['after_instances'] for r in before if r['protected'])
    # Passing requires actual VERIFIED coverage of each required claim path.
    verified = {reward for row in report['accounts'] for reward, r in row.get('rewards', {}).items()
                if r['journal'] == 'VERIFIED'}
    report['claim_paths_not_verified'] = sorted(set(report['required_rewards'])-verified)
    report['result'] = 'PASS' if (len(report['accounts']) == len(targets) and targets
        and all(r['result'] == 'COMPLETE' and all(
            r.get('rewards', {}).get(reward, {}).get('result') in COMPLETE_REWARDS
            for reward in report['required_rewards']) for r in report['accounts'])
        and report['all_selection_states_restored'] and report['protected_state_unchanged']
        and (tuple(report['required_rewards']) == SHOP_REWARDS or not report['claim_paths_not_verified'])) else 'PARTIAL'
    write(path, report)
    print(f'REPORT: {path}', flush=True)
    return report


def run_selected_task(manager, data, index, name, task, *, cancelled=lambda: False):
    """Normal UI entry: one explicitly selected target, no random/fleet expansion."""
    from top_heroes_auto.app.free_reward_tasks import Phase6TaskResult

    routes = {'ranking-chest': (REWARDS[0],), 'free-pack': SHOP_REWARDS}
    if task not in routes:
        raise ValueError('Only BXH and annotated shop gifts are supported.')
    _instance(manager, index, name)
    meta = manager.store.metadata(manager.namespace, index)
    if not meta.selected or meta.protected:
        raise SafetyError('Explicit selected non-Protected target required.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%fZ')
    folder = data / 'diagnostics/tasks/bxh-shop-fixed' / stamp
    row = run_account(manager, data, dict(index=index, name=name), folder,
                      rewards=routes[task], cancelled=cancelled, temporary_selection=False)
    status = 'SUCCESS' if row['result'] == 'COMPLETE' else row['result']
    if all(r['result'] == 'NOT_AVAILABLE' for r in row['rewards'].values()):
        status = 'NOT_AVAILABLE'
    return Phase6TaskResult(task, status, task_run_id=row.get('task_run_id'),
                            report_path=folder/'account-report.json', error=row.get('error'),
                            claim_verified=any(r['journal'] == 'VERIFIED' for r in row['rewards'].values()))
