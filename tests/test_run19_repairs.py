"""Run19 original pixels and production boundaries; no live gameplay."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.fixed_reward_port import FixedRewardPort
from top_heroes_auto.app.guild_mail_port import GuildMailPort
from top_heroes_auto.app.instance_session import InstanceSession
from top_heroes_auto.automation.fixed_reward_claims import observe_reward
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.event_task_grid import task_grid_rows, task_grid_shell, unresolved_grid_actions
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.fixed_rewards import FixedRewardDetector, portrait_region
from top_heroes_auto.vision.guild_mail import GuildMailDetector
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.screenshot import ScreenshotService

FIXTURES = Path(__file__).parent/'fixtures/run19'


def capture(name, image=None):
    payload = (FIXTURES/(name+'.png')).read_bytes() if image is None else cv2.imencode('.png',image)[1].tobytes()
    return ScreenshotService(lambda _:payload).take(Target(53,'display only','explicit-fixture','boot'))


@pytest.fixture(scope='module')
def shop():
    d = FixedRewardDetector()
    return d, {name:d.observe(capture(name)) for name in
               ('shop-back-resampled','shop-permanent-ticker','shop-permanent-received')}


def test_original_footer_failure_strictly_requalified_without_lowering_threshold(shop):
    detector, frames = shop
    frame = frames['shop-back-resampled']
    raw = unique_current_anchor(frame.captured,replace(detector.anchors['back'],
        expected_region=portrait_region(0,.90,1,1)))
    assert .959 < raw.score < raw.threshold == .96 and not raw.matched
    assert frame.page == 'shop-daily'
    assert frame.anchors['back'].matched and frame.anchors['back'].score >= .98
    assert frame.box('back').center[1] > frame.captured.device_size[1]*.92


def test_duplicate_or_missing_back_cannot_authorize_footer_input(shop):
    detector, frames = shop
    image = cv2.imread(str(FIXTURES/'shop-back-resampled.png'))
    box = frames['shop-back-resampled'].box('back')
    patch = image[box.y:box.y+box.height,box.x:box.x+box.width].copy()
    image[box.y:box.y+box.height,box.x+85:box.x+85+box.width] = patch
    assert not detector.observe(capture('shop-back-resampled',image)).box('back')
    image[1152:,:166] = 0
    assert not detector.observe(capture('shop-back-resampled',image)).box('back')


def test_ticker_never_proves_consumption_and_post_action_wait_can_reach_clean_proof(shop,monkeypatch):
    detector, frames = shop
    ticker, received = frames['shop-permanent-ticker'], frames['shop-permanent-received']
    assert detector.availability(ticker,'shop-permanent-privilege-gift')[0] == 'UNKNOWN'
    assert detector.availability(received,'shop-permanent-privilege-gift')[0] == 'NOT_AVAILABLE'
    seen = []
    sequence = iter([ticker,ticker,received])
    port = SimpleNamespace(detector=detector, observe_settled=lambda:(seen.append('capture') or next(sequence)))
    monkeypatch.setattr('top_heroes_auto.automation.fixed_reward_claims.pause',lambda *a:None)
    after,state,_,_ = observe_reward(port,ticker,'shop-permanent-privilege-gift',post_action=True)
    assert after is received and state == 'NOT_AVAILABLE' and len(seen) == 3


def test_actual_world_frame_does_not_trigger_six_mail_settle_captures():
    frame = GuildMailDetector(number_reader=lambda *a,**k:None).observe(capture('mail-world'))
    assert frame.page == 'UNKNOWN' and frame.overlay.state == ScreenState.GAME_WORLD
    port = object.__new__(GuildMailPort)
    port.cancelled = lambda:False
    port.observe = lambda:pytest.fail('Known foreign surface must not be polled as a Mail transition')
    port.dispatch = lambda *a:pytest.fail('No input from Mail on World')
    assert port.settle(frame) is frame


def session_for(manager,tmp_path):
    live = manager.query(7)
    session = InstanceSession(manager,tmp_path,dict(index=7,name=live.name,persistent_identity=live.stable_id),tmp_path)
    session.runtime = (live.pid,live.vbox_pid)
    return session


@pytest.mark.parametrize('change',['pid','disk','boot','protected','unselected','cancelled'])
def test_transaction_guard_rejects_session_change_before_capture_or_input(rig,tmp_path,change):
    manager,process,store = rig
    session = session_for(manager,tmp_path)
    target,_ = manager.capture_verified(7,session.snapshot)
    session.boot_id = target.boot_id
    if change == 'pid':
        process.listing = process.listing.replace('201,202','301,302')
    if change == 'disk':
        session.target['persistent_identity'] = 'different backing disk'
    if change == 'boot':
        session.boot_id = 'previous-boot'
    if change == 'protected':
        store.protect(manager.namespace,7,True)
    if change == 'unselected':
        store.select(manager.namespace,7,False)
    if change == 'cancelled':
        session.cancelled = lambda:True
    process.calls.clear()
    with pytest.raises(SafetyError):
        manager.capture_verified(7,session.snapshot,observed_target=target,operation_guard=session.validate_operation)
    with pytest.raises(SafetyError):
        manager.execute(7,'tap',values=(100,100),snapshot=session.snapshot,observed_target=target,
                        operation_guard=session.validate_operation)
    assert not any('input' in c or 'screencap' in c for c in process.calls)


def test_one_transaction_reuses_fresh_binding_and_ignores_unrelated_runtime_change(rig,tmp_path):
    manager,process,_ = rig
    session = session_for(manager,tmp_path)
    target,_ = manager.capture_verified(7,session.snapshot)
    session.boot_id = target.boot_id
    process.listing = process.listing.replace('101,102','501,502')
    process.calls.clear()
    current,_ = manager.capture_verified(7,session.snapshot,observed_target=target,
                                       operation_guard=session.validate_operation)
    assert current == target
    assert sum(c[1:] == ['list2'] for c in process.calls) == 2
    assert any(c[1:3] == ['-s',target.serial] and c[-1].endswith('boot_id') for c in process.calls)
    assert any(c[1] == 'adb' and c[2:4] == ['--index','7'] for c in process.calls)
    assert not any(c[1:3] == ['--index','0'] or c[1:] == ['kill-server'] for c in process.calls)


def test_exception_consumes_original_frame_before_uncertain_dispatch(tmp_path):
    port = object.__new__(FixedRewardPort)
    frame = SimpleNamespace(captured=SimpleNamespace(source_image='before.png'))
    port.last = frame
    port.target = object()
    port.events = []
    port.identity_check = lambda:None
    port.check = lambda **k:None
    port.save_events = lambda:None
    port.index,port.snapshot = 7,None
    port.manager = SimpleNamespace(execute=lambda *a,**k:(_ for _ in ()).throw(OSError('after dispatch')))
    with pytest.raises(OSError):
        port.dispatch(frame,'tap',(10,20))
    assert port.last is None and port.events[0]['outcome'] == 'POSSIBLE'
    with pytest.raises(SafetyError,match='Stale'):
        port.dispatch(frame,'tap',(10,20))


def test_bounded_explicit_sibling_reentry_uses_only_current_home_frame(monkeypatch):
    port = object.__new__(GuildMailPort)
    home = SimpleNamespace(page='home',captured=SimpleNamespace(source_image='home.png'),
                           overlay=SimpleNamespace(state=ScreenState.GAME_HOME),box=lambda _:True,
                           anchors={'home-guild':object()})
    guild = SimpleNamespace(page='guild')
    port.last = home
    port.sibling_recoveries,port.reentry_frame = [],None
    port.entries = {'guild':1,'mail':0}
    port.observe_settled = lambda:home
    port.cancelled = lambda:False
    port.recover_for_sibling(SimpleNamespace())
    assert port.sibling_recoveries[0]['result'] == 'HOME_VERIFIED'
    calls = []
    port.tap = lambda frame,anchor:calls.append((frame,anchor))
    monkeypatch.setattr('top_heroes_auto.app.guild_mail_port.poll',lambda *a,**k:guild)
    assert port.navigate(home,'home-guild','guild') is guild
    assert len(calls) == 1 and calls[0][0] is home
    with pytest.raises(SafetyError,match='silent re-entry'):
        port.navigate(home,'home-guild','guild')
    port.recover_for_sibling(SimpleNamespace())
    assert len(port.sibling_recoveries) == 1


def test_saved_grid_pixels_and_actual_ocr_transcript_qualify_free_complete_card():
    image = cv2.imread(str(FIXTURES/'race-task-grid.png'))
    data = json.loads((FIXTURES/'race-task-grid-ocr.json').read_text())
    assert data['engine'] == 'Windows.Media.Ocr'
    def reader(crop):
        return data['readings'][hashlib.sha256(crop.tobytes()).hexdigest()]
    shell = task_grid_shell(image)
    rows = task_grid_rows(image,shell,reader=reader)
    available = [r for r in rows if r['state'] == 'AVAILABLE']
    assert len(shell['cards']) == 5 and len(available) == 1
    assert 'completed-fraction-full-bar-and-free-label' in available[0]['evidence']
    assert not unresolved_grid_actions(image,shell,rows)


@pytest.mark.parametrize('fault',['conflicting-fraction','unreadable-control','unreadable-caption'])
def test_grid_ocr_conflict_or_partial_evidence_never_authorizes_claim(fault):
    image = cv2.imread(str(FIXTURES/'race-task-grid.png'))
    data = json.loads((FIXTURES/'race-task-grid-ocr.json').read_text())['readings']
    def reader(crop):
        words = data.get(hashlib.sha256(crop.tobytes()).hexdigest(), [])
        text = ' '.join(w['text'] for w in words)
        if fault == 'conflicting-fraction' and '(10/10)' in text:
            # One valid recognized contradictory fraction must veto both later
            # agreeing raw readings, not be discarded as OCR noise.
            return [{'text':'(5/10)'}] if crop.shape[0] < 200 else words
        if fault == 'unreadable-control' and any('Nh' in w['text'] for w in words):
            return []
        if fault == 'unreadable-caption' and ('hoang' in text):
            return []
        return words
    rows = task_grid_rows(image,task_grid_shell(image),reader=reader)
    assert not any(r['state'] == 'AVAILABLE' for r in rows)
    assert unresolved_grid_actions(image,task_grid_shell(image),rows)


def test_navigation_frame_reuse_does_not_bypass_journal_lock(rig,tmp_path,monkeypatch):
    from top_heroes_auto.automation.fixed_reward_claims import process_reward
    from top_heroes_auto.automation.fixed_reward_period import cycle_key
    from top_heroes_auto.vision.models import BoundingBox
    manager,_,store = rig
    task = store.create_task_run(manager.namespace,'bxh-shop-fixed',7,'label')
    claim = store.reserve_reward_claim(task,'shop-daily-gift',cycle_key('shop-daily-gift'),
        json.dumps(dict(persistent_identity='disk')),expected_instance=(7,'label'),not_dispatched=True,
        fixed_reward_period=True)
    store.mark_reward_dispatch(claim,task)
    frame = SimpleNamespace(captured=SimpleNamespace(index=7),evidence=lambda:{},box=lambda _:None,
                            page='shop-daily')
    port = SimpleNamespace(last=frame, settle=lambda f:f,
        detector=SimpleNamespace(availability=lambda *a:('AVAILABLE',SimpleNamespace(device_box=BoundingBox(1,1,5,5)),None)),
        observe_settled=lambda:pytest.fail('Do not duplicate a valid current frame'),
        tap=lambda *a,**k:pytest.fail('POSSIBLE must never redispatch'))
    monkeypatch.setattr('top_heroes_auto.automation.fixed_reward_reconcile.reconcile_fixed_reward',lambda *a:None)
    result = {}
    process_reward(port,store,manager.namespace,task,'shop-daily-gift','disk',result,lambda:None)
    assert result['result'] == 'ALREADY_ATTEMPTED' and result['claim_id'] == claim
    assert store.reward_claims(manager.namespace,7)[0]['dispatch_state'] == 'POSSIBLE'


def test_protected_runtime_delta_is_separate_from_flags_and_never_restored(rig,tmp_path,monkeypatch):
    from test_instance_pipeline import setup

    from top_heroes_auto.app import automation_fleet
    manager,process,_ = rig
    calls = []
    registry,session,_ = setup(calls)
    original = process.listing
    process.listing = original.replace('0,Main-Thang,1,2,1,101,102','0,Main-Thang,0,0,0,-1,-1')
    before = process.listing
    def observer(message):
        if 'REPORT' not in message:
            process.listing = original  # Simulate an unrelated user's start.
    monkeypatch.setattr(automation_fleet,'progress',observer)
    result = automation_fleet.run(manager,tmp_path,registry=registry,session_factory=session,
        identity_reader=lambda *a:'disk')
    assert before != process.listing
    assert result['protected_flags_unchanged'] is True
    assert result['protected_state_unchanged'] is False
    assert result['protected_runtime_changes'] == [dict(index=0,before='stopped',after='running',cause='UNPROVEN')]
    assert not any('--index' in c and c[c.index('--index')+1] == '0' for c in process.calls)


@pytest.mark.parametrize('kind',[FixedRewardPort,GuildMailPort])
def test_failed_fresh_capture_invalidates_previous_observation(kind):
    port = object.__new__(kind)
    port.last,port.qualified = object(),object()
    def revoked(**kw):
        raise SafetyError('revoked before capture')
    port.check = revoked
    with pytest.raises(SafetyError):
        port.observe()
    assert port.last is None
    if kind is GuildMailPort:
        assert port.qualified is None


def test_mail_sibling_and_return_home_reuse_only_unconsumed_current_frame():
    port = object.__new__(GuildMailPort)
    frame = SimpleNamespace(page='mail',overlay=SimpleNamespace(state=ScreenState.UNKNOWN))
    port.last = frame
    port.entries,port.reentry_frame = {'mail':1,'guild':0},None
    port.settle = lambda value:value
    port.detector = SimpleNamespace(mail_tabs=lambda f:{'war':{'count':0}})
    port.observe_settled = lambda:pytest.fail('No input changed the current proof')
    assert port.open_reward('mail-war') is frame
    home = SimpleNamespace(page='home')
    port.last = home
    assert port.home() is home
