"""Regression coverage for the user's two observed production omissions."""
import logging
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_phase7_guild_mail import Port, execute, fake_frame

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.guild_mail_claims import Opportunity, qualified_progress
from top_heroes_auto.ui.operational_log import OperationalLogHandler
from top_heroes_auto.vision.fixed_rewards import MONTHLY_DAILY, FixedRewardDetector, claim_geometry
from top_heroes_auto.vision.guild_mail import GuildMailDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


def capture(name):
    path = Path(__file__).parent/'fixtures'/f'{name}.png'
    return ScreenshotService(lambda _: path.read_bytes()).take(Target(17,'offline','explicit','boot'))


def test_live_quick_is_preferred_to_ordinary_wood_control():
    detector = GuildMailDetector(number_reader=lambda *a, **k: 10)
    frame = detector.observe(capture('phase7/donation-quick-live'))
    view = detector.availability(frame, 'guild-technology')
    assert view.state == 'AVAILABLE' and view.role == 'donation-quick'
    assert frame.values['donation_resource']['resource'] == 'WOOD'
    assert view.box.y < detector.control(frame, 'donation-green', 'green').y
    detector.action_geometry(frame, view.role, view.box, view.forbidden)


@pytest.mark.parametrize('remaining', [0, None])
def test_quick_does_not_override_unknown_or_zero_count(remaining):
    detector = GuildMailDetector(number_reader=lambda *a, **k: remaining)
    view = detector.availability(detector.observe(capture('phase7/donation-quick-live')), 'guild-technology')
    assert view.state == ('NOT_AVAILABLE' if remaining == 0 else 'UNKNOWN')


class DonationPort(Port):
    def __init__(self, states, roles):
        super().__init__(states)
        self.roles = iter(roles)

    def opportunity(self, reward, initial=None):
        frame, view = super().opportunity(reward, initial)
        return frame, replace(view, role=next(self.roles))


def test_ordinary_once_then_quick_exhausts_attempts(rig):
    port = DonationPort([('AVAILABLE',20),('AVAILABLE',19),('AVAILABLE',19),
                         ('AVAILABLE',19),('NOT_AVAILABLE',0),('NOT_AVAILABLE',0)],
                        ['donation-green','donation-quick','donation-quick','donation-quick','',''])
    result = execute(rig, port, 'guild-technology')
    assert result['result'] == 'SUCCESS' and port.taps == 2
    assert (result['ordinary_taps'],result['quick_invocations'],result['verified_contributions']) == (1,1,20)


def test_no_slow_ordinary_fallback(rig):
    port = DonationPort([('AVAILABLE',20),('AVAILABLE',19),('AVAILABLE',19),('AVAILABLE',19)],
                        ['donation-green']*4)
    result = execute(rig, port, 'guild-technology')
    assert result['result'] == 'BLOCKED' and port.taps == 1


def test_quick_already_visible_and_uncertain_is_never_retried(rig):
    port = DonationPort([('AVAILABLE',20)]+[('AVAILABLE',19)]*4, ['donation-quick']*5)
    result = execute(rig, port, 'guild-technology')
    assert result['result'] == 'ACTION_DISPATCHED_UNVERIFIED' and port.taps == 1
    again = DonationPort([('AVAILABLE',19)], ['donation-quick'])
    assert execute(rig, again, 'guild-technology')['result'] == 'ALREADY_ATTEMPTED'
    assert again.taps == 0


def test_bulk_requires_exhausted_counter_not_command_or_popup():
    view = Opportunity('guild-technology','AVAILABLE','donation-quick',remaining=20,context='node')
    assert qualified_progress(fake_frame(1,'donation'),view,fake_frame(2,'donation'),
                              replace(view,state='NOT_AVAILABLE',remaining=0))
    assert not qualified_progress(fake_frame(1,'donation'),view,fake_frame(2,'donation'),
                                  replace(view,remaining=19))


@pytest.fixture(scope='module')
def monthly():
    detector = FixedRewardDetector()
    return detector, [detector.observe(capture(p)) for p in
                      ('phase7_resume/shop-monthly-owned','phase6_finalization/monthly-daily-received')]


def test_monthly_lower_claim_without_red_badge(monthly):
    detector, (before, after) = monthly
    state, core, _ = detector.availability(before, MONTHLY_DAILY)
    assert state == 'AVAILABLE'
    geometry = claim_geometry(before, MONTHLY_DAILY, core)
    assert geometry['tap'] == list(core.device_box.center)
    assert geometry['outside_forbidden']
    assert detector.availability(after, MONTHLY_DAILY)[0] == 'NOT_AVAILABLE'


def test_monthly_missing_ownership_context_cannot_claim(monthly):
    detector, (frame, _) = monthly
    anchors = dict(frame.anchors)
    anchors['monthly-owned-label'] = replace(anchors['monthly-owned-label'],matched=False)
    assert detector.availability(replace(frame,anchors=anchors),MONTHLY_DAILY)[0] == 'UNKNOWN'


def test_monthly_duplicate_claim_label_is_unknown(monthly):
    detector, (frame, _) = monthly
    anchors = dict(frame.anchors)
    anchors['monthly-daily-claim'] = replace(anchors['monthly-daily-claim'],matched=False)
    assert detector.availability(replace(frame,anchors=anchors),MONTHLY_DAILY)[0] == 'UNKNOWN'


def test_monthly_paid_control_cannot_overlap_claim(monthly, monkeypatch):
    from top_heroes_auto.vision import monthly as module

    detector, (frame, _) = monthly
    component_reader = module.components
    claim = module.controls(frame,'monthly-daily-claim','green')[0]
    monkeypatch.setattr(module,'components',lambda image,color: [claim] if color == 'orange'
                        else component_reader(image,color))
    assert detector.availability(frame,MONTHLY_DAILY)[0] == 'UNKNOWN'


def test_quiet_ui_keeps_warnings_and_diagnostics_independent():
    handler = OperationalLogHandler()
    technical = logging.LogRecord('test',logging.INFO,'x',1,'inventory read',(),None)
    handler.emit(technical)
    assert handler.drain() == []
    warning = logging.LogRecord('test',logging.WARNING,'x',1,'uncertain action',(),None)
    handler.emit(warning)
    assert 'uncertain action' in handler.drain()[0]
    handler.technical = True
    handler.emit(technical)
    assert 'inventory read' in handler.drain()[0]
    for n in range(2000):
        handler.emit(logging.LogRecord('test',logging.INFO,'x',1,f'event {n}',(),None))
    assert len(handler.drain()) == 500


@pytest.mark.parametrize('upper_result', ['SUCCESS','ALREADY_VERIFIED','ALREADY_ATTEMPTED','UNKNOWN'])
def test_monthly_upper_outcome_never_suppresses_lower_daily(monkeypatch, upper_result):
    from top_heroes_auto.automation import monthly_privilege as module
    from top_heroes_auto.vision.fixed_rewards import MONTHLY_QUICK

    def frame(page):
        return SimpleNamespace(page=page, box=lambda _: object(), evidence=lambda: {'page':page})
    class MonthlyPort:
        def __init__(self):
            self.page = 'shop-monthly'
            self.detector = SimpleNamespace(selected_tab=lambda *a: True,
                availability=lambda *a: ('NOT_AVAILABLE',None,None))
        def observe_settled(self):
            return frame(self.page)
        def navigate(self, source, role, destination):
            self.page = destination
            return frame(self.page)
    calls = []
    def process(port, store, namespace, task_id, reward, identity, outcome, persist):
        calls.append(reward)
        outcome.update(result=upper_result if reward == MONTHLY_QUICK else 'SUCCESS',
                       claim_dispatched=reward == MONTHLY_DAILY, journal='VERIFIED')
    monkeypatch.setattr(module, 'process_reward', process)
    result = {}
    module.process_monthly(MonthlyPort(),None,'n',1,'disk',result,lambda:None)
    assert calls == [MONTHLY_QUICK,MONTHLY_DAILY]
    assert result['children'][MONTHLY_DAILY]['result'] == 'SUCCESS'
    assert result['result'] == ('SUCCESS' if upper_result in {'SUCCESS','ALREADY_VERIFIED'} else 'BLOCKED')


def test_unchanged_inventory_does_not_rewrite_persistent_rows(rig, monkeypatch):
    manager, _, store = rig
    instances = manager.refresh()
    connect = store.connect
    writes = []
    @contextmanager
    def observed():
        with connect() as db:
            yield db
            writes.append(db.total_changes)
    monkeypatch.setattr(store, 'connect', observed)
    store.merge(manager.namespace, instances)
    assert writes == [0]
    writes.clear()
    store.metadata(manager.namespace,7)
    assert len(writes) == 1  # Flags + stable identity are one consistent read.


def test_diagnostic_context_is_separate_from_ui_filter():
    from top_heroes_auto.app.log_context import RunContextFilter, instance_index, run_id

    run_token, instance_token = run_id.set(123), instance_index.set(17)
    try:
        record = logging.LogRecord('test',logging.INFO,'caller.py',10,'read inventory',(),None)
        assert RunContextFilter().filter(record)
        handler = OperationalLogHandler()
        handler.emit(record)
        assert handler.drain() == []
        assert (record.run_id,record.instance_index,record.filename,record.lineno) == (123,17,'caller.py',10)
    finally:
        run_id.reset(run_token)
        instance_index.reset(instance_token)


def test_bounded_diagnostic_queue_preserves_critical_outcomes():
    from top_heroes_auto.app.log_context import DiagnosticQueue

    records = []
    class Destination(logging.Handler):
        def emit(self, record):
            records.append(record)
    queued = DiagnosticQueue(Destination())
    for _ in range(2050):
        queued.handle(logging.LogRecord('test',logging.INFO,'caller',1,'inventory',(),None))
    assert queued.queue.qsize() == 2048 and queued.dropped_repetitive == 2
    queued.handle(logging.LogRecord('test',logging.ERROR,'caller',1,'uncertain dispatch',(),None))
    assert records[-1].getMessage() == 'uncertain dispatch'


def test_quick_wood_authorization_is_not_inherited_from_green_color(monkeypatch):
    detector = GuildMailDetector(number_reader=lambda *a, **k: 10)
    frame = detector.observe(capture('phase7/donation-quick-live'))
    monkeypatch.setattr(detector, 'donation_resource', lambda *a: 'STONE')
    assert detector.availability(frame, 'guild-technology').state == 'RESOURCE_NOT_AUTHORIZED'


def test_failed_bounded_recovery_does_not_reset_for_every_feature(rig, tmp_path):
    from top_heroes_auto.app.instance_session import InstanceSession
    from top_heroes_auto.automation.guard import SafetyError
    from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus

    calls = []
    def recover(*args, **kwargs):
        calls.append(kwargs)
        status = RecoveryStatus.SUCCESS if len(calls) == 1 else RecoveryStatus.LOADING_TIMEOUT
        return RecoveryResult(status), tmp_path/'recovery.json', False
    session = InstanceSession(rig[0],tmp_path,dict(index=7,name='Farm-007',persistent_identity='disk'),
        tmp_path,identity_reader=lambda *a:'disk',recovery_runner=recover)
    session.start()
    session.recover()
    session.recover()
    with pytest.raises(SafetyError, match='NOT_RUN_TARGET_BLOCKED'):
        session.recover()
    assert len(calls) == 2


def test_target_recovery_block_records_remaining_plan_without_inputs(rig, tmp_path):
    from test_instance_pipeline import setup

    from top_heroes_auto.app.automation_fleet import run
    from top_heroes_auto.app.flow_registry import Flow, FlowRegistry

    calls = []
    _, session, feature = setup(calls)
    def failed_recovery(session, folder, rewards):
        session.navigation_blocked = 'LOADING_TIMEOUT'
        return dict(rewards={r:dict(result='BLOCKED') for r in rewards})
    registry = FlowRegistry()
    registry.register(Flow('blocked',('one',),failed_recovery))
    registry.register(Flow('later',('two',),feature))
    result = run(rig[0],tmp_path,registry=registry,session_factory=session,identity_reader=lambda *a:'disk')
    row = result['accounts'][0]
    assert row['rewards']['two']['result'] == 'NOT_RUN_TARGET_BLOCKED'
    assert row['flows']['later']['no_input']
    assert calls == [(7,'start'),(7,'cleanup')]


def test_monthly_cancellation_after_dispatch_retains_child_evidence(monkeypatch):
    from top_heroes_auto.automation import monthly_privilege as module
    from top_heroes_auto.automation.guard import SafetyError

    report = {}
    def interrupted(port, store, namespace, task_id, identity, report, persist):
        report.update(result='BLOCKED',children={'upper':dict(claim_dispatched='POSSIBLE',claim_id=44)})
        raise SafetyError('Run cancelled')
    monkeypatch.setattr(module,'_process_monthly',interrupted)
    with pytest.raises(SafetyError,match='cancelled'):
        module.process_monthly(None,None,'n',1,'disk',report,lambda:None)
    assert report['claim_dispatched'] and report['claim_count'] == 1
    assert report['children']['upper']['claim_id'] == 44


def test_operational_info_visible_and_repetitive_details_summarized():
    handler = OperationalLogHandler()
    outcome = logging.LogRecord('test',logging.INFO,'caller',1,'Đã xác minh quà',(),None)
    outcome.category = 'operation'
    handler.emit(outcome)
    handler.emit(outcome)
    handler.emit(logging.LogRecord('test',logging.ERROR,'caller',2,'UNKNOWN',(),None))
    visible = handler.drain()
    assert len(visible) == 3
    assert 'Đã xác minh quà' in visible[0] and '1 lần' in visible[1] and 'UNKNOWN' in visible[2]


def test_receipt_budget_is_per_qualified_action_not_all_shop_rewards():
    from top_heroes_auto.app.fixed_reward_port import FixedRewardPort
    from top_heroes_auto.automation.guard import SafetyError
    from top_heroes_auto.automation.overlays import OverlayBudget
    from top_heroes_auto.vision.models import BoundingBox, ScreenState

    port = object.__new__(FixedRewardPort)
    port.overlay_budget = OverlayBudget(max_total=6,max_same=3)
    receipt = SimpleNamespace(state=ScreenState.REWARD_RECEIPT,evidence=[])
    anchor = SimpleNamespace(matched=True,device_box=BoundingBox(1,1,20,20))
    page = SimpleNamespace(page='shop-monthly',anchors={'free':anchor})
    inputs = []
    port.dispatch = lambda *args: inputs.append(args)
    for _ in range(5):
        port.tap(page,anchor)
        port.overlay_budget.reserve(receipt)
    assert len(inputs) == 5
    port.overlay_budget.reserve(receipt)
    port.overlay_budget.reserve(receipt)
    with pytest.raises(SafetyError,match='limit reached'):
        port.overlay_budget.reserve(receipt)
    with pytest.raises(SafetyError,match='current-page'):
        port.tap(SimpleNamespace(page='UNKNOWN'),anchor)
    assert port.overlay_budget.total == 3  # UNKNOWN never renews permission.


def test_current_technology_like_is_strictly_aligned_and_bound_to_node():
    detector = GuildMailDetector()
    frame = detector.observe(capture('phase7/technology-like-current'))
    assert frame.page == 'technology'
    marker = frame.anchors['technology-like']
    assert marker.matched and marker.score >= marker.threshold >= .98
    assert frame.box('technology-node') is not None
    assert frame.box('technology-node').y > marker.device_box.y


def test_duplicate_aligned_technology_marker_remains_ambiguous():
    import cv2

    from top_heroes_auto.vision.guild_mail import portrait

    detector = GuildMailDetector()
    captured = capture('phase7/technology-like-current')
    frame = detector.observe(captured)
    box = frame.box('technology-like')
    image = portrait(captured).copy()
    image[box.y:box.y+box.height,box.x+2*box.width:box.x+3*box.width] = image[
        box.y:box.y+box.height,box.x:box.x+box.width].copy()
    duplicate = ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(
        Target(17,'offline','explicit','boot'))
    result = detector.observe(duplicate)
    assert result.box('technology-like') is None and result.box('technology-node') is None
