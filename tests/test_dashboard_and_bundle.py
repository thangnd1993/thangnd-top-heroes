import json
import logging
import os
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from top_heroes_auto.app.diagnostic_bundle import export_bundle
from top_heroes_auto.storage.store import AccountStatus, RunStatus
from top_heroes_auto.ui.operational_log import OperationalLogHandler
from top_heroes_auto.ui.run_progress import ERROR_LABELS, RunProgress, classify_error, format_elapsed
from top_heroes_auto.ui.window import Window


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


# ---- pure progress model -------------------------------------------------

def test_progress_counts_real_states_and_never_invents_percentages():
    clock = Clock()
    progress = RunProgress(clock=clock)
    progress.begin(7)
    progress.account_started(8)
    progress.account_started(10)
    assert progress.active_workers() == 2 and progress.finished_accounts() == 0
    progress.flow_event(8, 'events', 'STARTED', 'Đang xử lý Sự kiện.')
    assert progress.accounts[8].line() == 'Sự kiện · đang xử lý'
    progress.flow_event(8, 'events', 'COMPLETE', 'ok')
    progress.flow_event(8, 'mail', 'BLOCKED', 'mail: bị chặn (screen UNKNOWN)')
    assert (progress.accounts[8].done, progress.accounts[8].blocked) == (1, 1)
    assert 'Màn hình không xác định' in progress.accounts[8].line() and '%' not in progress.accounts[8].line()
    clock.now = 165.0
    progress.account_finished(8, 'Lỗi', 'Còn phần bị chặn')
    assert progress.active_workers() == 1 and progress.finished_accounts() == 1
    assert progress.elapsed() == 65.0 and format_elapsed(65) == '01:05' and format_elapsed(3725) == '1:02:05'


def test_a_new_run_resets_account_state_but_the_same_run_does_not():
    progress = RunProgress(clock=Clock())
    progress.begin(1)
    progress.account_started(2)
    progress.begin(1)
    assert 2 in progress.accounts
    progress.begin(2)
    assert not progress.accounts


def test_error_classification_covers_the_shared_categories():
    assert classify_error('Indexed ADB serial unavailable') == 'ADB_UNAVAILABLE'
    assert classify_error('Protected target') == 'PROTECTED_TARGET'
    assert classify_error('Observed screenshot boot changed: identity') == 'TARGET_IDENTITY_AMBIGUOUS'
    assert classify_error('screen UNKNOWN after popup') == 'SCREEN_UNKNOWN'
    assert classify_error('something unexpected') == 'RECOVERABLE_FEATURE_ERROR'
    assert classify_error('') == 'RECOVERABLE_FEATURE_ERROR'
    assert all(classify_error(m) in ERROR_LABELS for m in ('x', 'adb', 'possible'))


def test_blocked_flow_does_not_hide_later_independent_flows():
    progress = RunProgress(clock=Clock())
    progress.begin(1)
    progress.account_started(3)
    for flow, state in (('vip', 'BLOCKED'), ('ranking', 'COMPLETE'), ('shop', 'COMPLETE')):
        progress.flow_event(3, flow, state, f'{flow}: {state}')
    assert (progress.accounts[3].done, progress.accounts[3].blocked) == (2, 1)


# ---- structured flow events through the real logging path ----------------

def test_operational_handler_forwards_flow_events_even_when_technical_view_is_off():
    handler = OperationalLogHandler()
    logger = logging.getLogger('test.flow.events')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        logger.info('detail', extra={'category': 'operation', 'ui_index': 4, 'ui_flow': 'vip', 'ui_state': 'COMPLETE'})
        logger.info('chatter')  # technical info is not shown, and not a flow event
    finally:
        logger.removeHandler(handler)
    assert handler.drain_flow_events() == [(4, 'vip', 'COMPLETE', 'detail')]


def test_fleet_event_emits_structured_ui_fields(tmp_path):
    """The real fleet `event()` helper must carry index/flow/state to the UI handler."""
    import inspect

    from top_heroes_auto.app import automation_fleet

    source = inspect.getsource(automation_fleet)
    assert "'ui_index': target['index'], 'ui_flow': flow, 'ui_state': state" in source


# ---- window --------------------------------------------------------------

def make_window(rig, tmp_path, monkeypatch):
    manager, _, store = rig
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(Window, 'discover_ld', lambda self: None)
    window = Window(store, tmp_path)
    window.manager = manager
    window.instances = manager.refresh()
    window.render()
    return window, manager, store


def test_window_shows_build_metadata_not_a_hardcoded_version(rig, tmp_path, monkeypatch):
    window, *_ = make_window(rig, tmp_path, monkeypatch)
    summary = window.version.summary
    assert summary in window.windowTitle() and 'V0.1.0 · Phase 1' not in window.windowTitle()
    window.update_dashboard()
    assert window.cards['version'].text() == summary
    window.close()


def test_dashboard_counts_instances_without_using_names(rig, tmp_path, monkeypatch):
    window, manager, store = make_window(rig, tmp_path, monkeypatch)
    window.update_dashboard()
    text = window.cards['fleet'].text()
    protected = sum(store.metadata(manager.namespace, i.index).protected for i in window.instances)
    assert f"{len(window.instances)} tổng" in text
    assert f'{len(window.instances) - protected} khả dụng' in text
    assert window.cards['run'].text() == 'Chưa bắt đầu' and window.cards['verified'].text() == '—'
    window.close()


def test_live_progress_reaches_table_and_dashboard(rig, tmp_path, monkeypatch):
    window, manager, store = make_window(rig, tmp_path, monkeypatch)
    run_id = store.create_run(manager.namespace, [(7, 'Farm')], 2) if hasattr(store, 'create_run') else 1
    store.set_run_status(run_id, RunStatus.RUNNING)
    window.update_run_progress(run_id, 7, AccountStatus.RUNNING, 'Đang chạy toàn bộ kế hoạch nhận quà')
    window.progress.flow_event(7, 'shop', 'STARTED', 'Đang xử lý Tiệm.')
    window.sync_run_states()
    window.render()
    row = next(r for r in range(window.table.rowCount()) if window.table.item(r, 1).text() == '7')
    assert window.table.item(row, 7).text() == 'Tiệm · đang xử lý'
    window.update_dashboard()
    assert window.cards['workers'].text().startswith('1/')
    assert window.cards['run'].text().startswith(f'#{run_id}')
    window.close()


def test_advanced_tools_collapsed_and_stop_is_distinct_from_start(rig, tmp_path, monkeypatch):
    window, *_ = make_window(rig, tmp_path, monkeypatch)
    window.show()
    QApplication.instance().processEvents()
    assert not window.advanced.isVisible()
    window.advanced_toggle.setChecked(True)
    assert window.advanced.isVisible()
    assert window.auto_start.objectName() == 'primary' and window.auto_stop.objectName() == 'danger'
    assert window.auto_start.text() != window.auto_stop.text()
    window.close()


def test_warning_banner_reports_blocked_items(rig, tmp_path, monkeypatch):
    window, *_ = make_window(rig, tmp_path, monkeypatch)
    window.progress.begin(1)
    window.progress.flow_event(7, 'events', 'BLOCKED', 'events: bị chặn')
    window.update_dashboard()
    assert not window.warning_banner.isHidden() and '1 mục bị chặn' in window.warning_banner.text()
    window.close()


# ---- diagnostic bundle ---------------------------------------------------

def build_run(rig, tmp_path):
    manager, _, store = rig
    run_id = store.create_run(manager.namespace, [(7, 'Farm')], 2)
    store.set_run_status(run_id, RunStatus.RUNNING)
    folder = tmp_path / 'diagnostics' / 'tasks' / 'automation' / 'r1'
    (folder / '7').mkdir(parents=True)
    (folder / 'fleet-report.json').write_text(json.dumps(dict(result='PARTIAL', accounts=[])))
    accounts = [
        dict(index=7, result='PARTIAL', worker='w1', elapsed_seconds=100, worker_started_at='2026-10-25T00:00:00+00:00',
             worker_finished_at='2026-10-25T00:01:40+00:00', timing_seconds=dict(startup_and_initial_home=10, flows={'vip': 5}, cleanup=1),
             operation_metrics={'ocr': dict(calls=3, seconds=20.0, exclusive_seconds=20.0)}),
        dict(index=9, result='COMPLETE', worker='w2', elapsed_seconds=60, worker_started_at='2026-10-25T00:00:30+00:00',
             worker_finished_at='2026-10-25T00:01:30+00:00'),
    ]
    for a in accounts:
        (folder / str(a['index'])).mkdir(exist_ok=True)
        (folder / str(a['index']) / 'account-report.json').write_text(json.dumps(a))
    (folder / '7' / 'blocked.png').write_bytes(b'\x89PNG fake')
    store.set(f'automation-report:{run_id}', str(folder / 'fleet-report.json'))
    logs = tmp_path / 'logs'
    logs.mkdir()
    (logs / 'app.log').write_text(f'a run={run_id} index=7 hello\nb run=999 other\n', encoding='utf-8')
    return run_id


def test_bundle_contains_run_evidence_and_is_read_only(rig, tmp_path):
    manager, _, store = rig
    run_id = build_run(rig, tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file() and p.suffix in {'.json', '.log'}}
    out = export_bundle(tmp_path, run_id)
    with zipfile.ZipFile(out) as bundle:
        names = set(bundle.namelist())
        manifest = json.loads(bundle.read('manifest.json'))
        timings = json.loads(bundle.read('timings.json'))
        log = bundle.read(f'logs/app-run{run_id}.log').decode()
    assert {'manifest.json', 'timings.json', 'journal-snapshot.json', 'reports/fleet-report.json',
            'reports/7/account-report.json'} <= names
    assert not any(n.startswith('screenshots/') for n in names)
    assert 'run=999' not in log and 'hello' in log
    assert manifest['run_id'] == run_id and manifest['read_only'] and set(manifest['version']) >= {'commit', 'release_date'}
    assert all(f['sha256'] for f in manifest['files'])
    # The two recorded worker intervals genuinely overlap (30s..90s => 60s); settings alone prove nothing.
    assert timings['worker_overlap']['max_overlap_seconds'] == 70.0 - 10.0 and timings['worker_overlap']['distinct_workers'] == 2
    assert timings['accounts'][0]['exclusive_seconds_percent_of_wall'] == {'ocr': 20.0}
    assert before == {p: p.read_bytes() for p in before}  # nothing existing was rewritten
    assert (tmp_path / 'diagnostics').exists() and store.get(f'automation-report:{run_id}')


def test_bundle_screenshots_are_opt_in_and_missing_evidence_is_declared(rig, tmp_path):
    run_id = build_run(rig, tmp_path)
    with zipfile.ZipFile(export_bundle(tmp_path, run_id, screenshots=True, output=tmp_path / 'with.zip')) as bundle:
        assert 'screenshots/7/blocked.png' in bundle.namelist()
    (tmp_path / 'logs' / 'app.log').unlink()
    with zipfile.ZipFile(export_bundle(tmp_path, run_id, output=tmp_path / 'without.zip')) as bundle:
        missing = json.loads(bundle.read('manifest.json'))['missing_evidence']
    assert any('app.log' in m for m in missing)


def test_bundle_without_any_run_refuses_instead_of_inventing(tmp_path, rig):
    import pytest

    empty = tmp_path / 'empty'
    empty.mkdir()
    with pytest.raises(ValueError):
        export_bundle(empty)
