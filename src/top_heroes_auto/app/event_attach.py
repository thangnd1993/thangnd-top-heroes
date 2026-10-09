"""One running account, existing production Event services, no lifecycle ownership."""
import json
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from top_heroes_auto.app.automation_fleet import execute_instance
from top_heroes_auto.app.automation_ownership import exclusive_automation
from top_heroes_auto.app.bxh_shop_acceptance import inventory, persistent_identity, progress, write
from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.app.flow_registry import production_registry
from top_heroes_auto.automation.guard import SafetyError, bound_snapshot
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


def inventory_signature(rows):
    return {r['index']: (r['name'], r['status'], r['stable_id'], r['protected']) for r in rows}


@contextmanager
def attach_guard(manager, before, folder):
    """Reject cross-target/lifecycle commands; bind only the authorized runtime."""
    identities = {r["index"]: r["stable_id"] for r in before}
    binding = dict(index=None, serial=None, boot=None, runtime=None)
    actions = []
    execute, capture = manager.execute, manager.capture_verified

    def check():
        index = binding['index']
        if index is None:
            return  # Random HOME qualification has not bound a target yet.
        live = manager.query(index)
        meta = manager.store.metadata(manager.namespace, index)
        if (not live.running or not live.android_started or meta.protected or not meta.selected
                or live.stable_id != identities.get(index) or meta.identity_state != 'VERIFIED'):
            raise SafetyError('ATTACH_ONLY_BOUND_TARGET_UNSAFE: no further input.')
        runtime = live.pid, live.vbox_pid
        if binding['runtime'] is None:
            binding['runtime'] = runtime
        elif binding['runtime'] != runtime:
            raise SafetyError('ATTACH_ONLY_RUNTIME_CHANGED: no further input.')

    def guarded_execute(index, action, *args, **kwargs):
        check()
        if index != binding['index'] or action not in {'tap', 'swipe', 'keyevent'}:
            raise SafetyError(f'ATTACH_ONLY_FORBIDDEN_OPERATION: {index}/{action}')
        entry = dict(index=index, action=action, values=kwargs.get('values'),
                     timestamp=datetime.now(timezone.utc).isoformat(), outcome='REQUESTED')
        actions.append(entry)
        write(folder/'action-trace.json', actions)
        result = execute(index, action, *args, **kwargs)
        entry['outcome'] = 'DISPATCHED'
        write(folder/'action-trace.json', actions)
        progress(f"EVENT ACTION #{index}: {action} dispatched {entry['values']}")
        return result

    def guarded_capture(index, *args, **kwargs):
        check()
        if binding['index'] is not None and index != binding['index']:
            raise SafetyError('ATTACH_ONLY_TARGET_CHANGED')
        target, payload = capture(index, *args, **kwargs)
        if binding['serial'] is not None and (target.serial, target.boot_id) != (binding['serial'], binding['boot']):
            raise SafetyError('ATTACH_ONLY_ADB_OR_BOOT_CHANGED')
        return target, payload

    manager.execute, manager.capture_verified = guarded_execute, guarded_capture
    try:
        yield binding, check, actions
    finally:
        manager.execute, manager.capture_verified = execute, capture


def capture_home(manager, data, row, folder):
    snapshot = bound_snapshot(manager.store, manager.namespace, ((row['index'], row['name']),), True)
    target, payload = manager.capture_verified(row['index'], snapshot)
    screen = ScreenshotService(lambda serial: payload if serial == target.serial else b'').take(
        target, folder, 'attach-home')
    detection = RecoveryScreenDetector().detect(screen)
    proof = dict(index=row['index'], adb=target.serial, boot=target.boot_id,
                 screenshot=str(screen.source_image), detection=detection.as_dict())
    return detection.state == ScreenState.GAME_HOME, proof


def resume_home(manager, row, folder, check, event_identity, *, port_factory=DynamicEventPort):
    """A recorded repair continuation may leave only qualified Event parent edges."""
    snapshot = bound_snapshot(manager.store, manager.namespace, ((row['index'], row['name']),), True)
    live = manager.query(row['index'])
    runtime = live.pid, live.vbox_pid

    def exact_check():
        check()
        current = manager.query(row['index'])
        if not current.running or (current.pid, current.vbox_pid) != runtime:
            raise SafetyError('ATTACH_ONLY_RUNTIME_CHANGED')

    session = SimpleNamespace(manager=manager, snapshot=snapshot, index=row['index'], name=row['name'],
                              target=row, check=exact_check, cancelled=lambda: False)
    port = port_factory(session, folder)
    port.entered = event_identity  # Context only; every parent needs fresh qualified shell evidence.
    trace = []
    for _ in range(4):
        frame = port.observe()
        trace.append(dict(capture=frame.capture, page=frame.page))
        write(folder/'repair-resume-navigation.json', trace)
        if frame.page == 'home' and not frame.popup and frame.event_scan_performed:
            return True
        if not frame.page.startswith('event:') or frame.popup or frame.parent is None:
            return False
        port.navigate(frame, frame.parent)
        trace[-1]['parent_dispatched'] = True
        write(folder/'repair-resume-navigation.json', trace)
    return False


@exclusive_automation
def run(manager, data, *, resume_report=None, choice=secrets.choice):
    previous = json.loads(resume_report.read_text(encoding='utf-8')) if resume_report else None
    before = inventory(manager)
    folder = data/'diagnostics/tasks/event-attach'/datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%fZ')
    folder.mkdir(parents=True, exist_ok=False)
    report = dict(mode='ATTACH_ONLY_PHASE8_ONLY', before_instances=before, home_candidates=[],
                  eligible_indexes=[], random_method='secrets.choice', result='PRECONDITION_NOT_READY',
                  resumed_from=str(resume_report) if resume_report else None)
    selected_before = None
    chosen = None
    with attach_guard(manager, before, folder) as (binding, check, actions):
        try:
            if previous:
                if previous.get('mode') != 'ATTACH_ONLY_PHASE8_ONLY' or not previous.get('bound_target'):
                    raise SafetyError('Attach continuation requires a saved single bound account.')
                original = previous['bound_target']
                matching = [r for r in before if r['index'] == original['index'] and not r['protected']
                            and r['status'] == 'running' and r['android_started']]
                if len(matching) != 1:
                    raise SafetyError('ATTACH_ONLY_BOUND_INSTANCE_NOT_RUNNING')
                chosen = dict(matching[0], persistent_identity=persistent_identity(manager, original['index']),
                              preflight_running=True)
                if chosen['persistent_identity'] != original['persistent_identity']:
                    raise SafetyError('ATTACH_ONLY_BOUND_INSTANCE_CHANGED')
                proofs = [p for p in previous['home_candidates'] if p['index'] == chosen['index']]
                if len(proofs) != 1:
                    raise SafetyError('Attach continuation requires the original verified HOME/ADB proof.')
                binding.update(index=chosen['index'], serial=proofs[0]['adb'], boot=proofs[0]['boot'])
                report['home_candidates'] = proofs
            else:
                qualified = []
                for row in before:
                    if row['protected'] or row['status'] != 'running' or not row['android_started']:
                        continue
                    selected = row['selected']
                    try:
                        if not selected:
                            manager.select(row['index'], True)
                        stable = persistent_identity(manager, row['index'])
                        home, proof = capture_home(manager, data, row, folder)
                        report['home_candidates'].append(proof)
                        if home:
                            qualified.append(dict(row, persistent_identity=stable, preflight_running=True))
                    finally:
                        manager.select(row['index'], selected)
                report['eligible_indexes'] = [r['index'] for r in qualified]
                if qualified:
                    chosen = choice(qualified)
                    proof = next(p for p in report['home_candidates'] if p['index'] == chosen['index'])
                    binding.update(index=chosen['index'], serial=proof['adb'], boot=proof['boot'])
            if chosen:
                report['bound_target'] = chosen
                selected_before = manager.store.metadata(manager.namespace, chosen['index']).selected
                if not selected_before:
                    manager.select(chosen['index'], True)
                write(folder/'attach-report.json', report)
                if previous:
                    prior_actions = previous.get('account', {}).get('flows', {}).get('events', {}).get(
                        'exploration', {}).get('actions', [])
                    entries = [a['identity'] for a in prior_actions if a.get('kind') == 'event']
                    if not entries or not resume_home(manager, chosen, folder, check, entries[-1]):
                        raise SafetyError('ATTACH_ONLY_RESUME_HOME_NOT_VERIFIED')
                progress(f"HOME verified; bound #{chosen['index']}; production events only")
                report['account'] = execute_instance(manager, data, chosen, folder/str(chosen['index']),
                    production_registry(), only_flows=('events',), temporary_selection=False)
                report['result'] = report['account']['result']
        except (OSError, ValueError, RuntimeError) as exc:
            report.update(result='BLOCKED', error=f'{type(exc).__name__}: {exc}')
        finally:
            if chosen is not None and selected_before is False:
                meta = manager.store.metadata(manager.namespace, chosen['index'])
                if (meta.selected and not meta.protected and
                        persistent_identity(manager, chosen['index']) == chosen['persistent_identity']):
                    manager.select(chosen['index'], selected_before)
            report['actions'] = actions
            report['after_instances'] = inventory(manager)
            report['selection_restored'] = chosen is None or any(
                r['index'] == chosen['index'] and r['selected'] == selected_before
                for r in report['after_instances'])
            report['inventory_unchanged'] = inventory_signature(before) == inventory_signature(report['after_instances'])
            write(folder/'attach-report.json', report)
    progress(f'ATTACH REPORT: {folder / "attach-report.json"}')
    return report
