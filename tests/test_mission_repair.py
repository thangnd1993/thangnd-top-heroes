"""Saved real mission states, typed one-shot dispatch and independent proof."""
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.automation.dynamic_events import Control, EventFrame
from top_heroes_auto.automation.event_journal import dispatch_once
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.relic_expedition import dispatch_transition, mission_rows

ROOT = Path(__file__).parent/'fixtures/phase8'


def evidence(name):
    image = cv2.imread(str(ROOT/(name+'.png')))
    recorded = json.loads((ROOT/'relic-mission-ocr.json').read_text(encoding='utf-8'))
    rows = mission_rows(image, cv2.imread('assets/tasks/phase8/personal-task-tab.png'),
        reader=lambda crop: recorded.get(hashlib.sha256(crop.tobytes()).hexdigest(), []))
    return image, rows


def test_running_timers_are_waiting_not_claims_or_dispatchable():
    _, before = evidence('relic-dispatch-before')
    _, after = evidence('relic-dispatch-running')
    assert len(before) == len(after) == 3
    assert all(r['state']=='DISPATCHABLE' for r in before)
    assert all(r['state']=='WAITING' for r in after)
    assert sum(r['timer_confirmed'] for r in after) >= 1


def test_real_dispatch_proof_requires_changed_matching_missions():
    before, old = evidence('relic-dispatch-before')
    after, new = evidence('relic-dispatch-running')
    assert dispatch_transition(before, after, old, new)
    assert not dispatch_transition(before, before, old, old)
    assert not dispatch_transition(after, after, new, new)
    assert not dispatch_transition(before, after, old,
        [{**r, 'timer_confirmed':False} for r in new])
    assert not dispatch_transition(before, after, old,
        [{**r, 'row':replace(r['row'],y=r['row'].y+30)} for r in new])


@pytest.mark.parametrize('changed', [True, False])
def test_production_send_once_requires_two_independent_running_frames(rig,tmp_path,changed):
    manager, _, store = rig
    port = object.__new__(DynamicEventPort)
    port.session = SimpleNamespace(manager=manager,index=7,name='display',
                                   target={'persistent_identity':'fixture-disk-7'})
    port.folder = tmp_path
    identity = (7,'fixture-disk-7','explicit','boot')
    action = Control('relic-expedition-confirm-send',BoundingBox(280,990,160,50),
                     ('context','qualified-selected-teams','free'),'mission',cost='FREE',available=True)
    confirm = EventFrame('confirm',identity,'event:relic-expedition:confirm','confirm',(action,))
    origin = replace(confirm,capture='before',page='event:event:personal-tasks',controls=())
    before, old = evidence('relic-dispatch-before')
    port.dispatch_origin = (origin,before,old)
    images = [evidence('relic-dispatch-running'), evidence('relic-dispatch-running-confirmed')]
    frames = iter([replace(confirm,capture='fresh'),
                   replace(origin,capture='running1'),replace(origin,capture='running2')])
    n = 0
    def observe():
        nonlocal n
        port.current = next(frames)
        if n:
            port.navigation_image, port.mission_rows = images[min(n-1,1)] if changed else (before,old)
        n += 1
        return port.current
    calls = []
    def dispatch(*args, **kwargs):
        kwargs['before_input']()
        calls.append(args)
    port.current = confirm
    port.observe = observe
    port.transport = SimpleNamespace(last=object(),dispatch=dispatch)
    result = port.send_mission(confirm,action)
    assert len(calls)==1 and result['mission_dispatched']
    assert result['journal']==('VERIFIED' if changed else 'RESERVED')
    row = store.reward_claims(manager.namespace,7)[0]
    assert json.loads(row['before_evidence'])['action_type']=='DISPATCH'
    if changed:
        assert all(p['state']=='RUNNING' for p in json.loads(row['after_evidence']))
    # Re-entering the same action cannot send again, even after a later day.
    port.current = confirm
    port.observe = lambda: setattr(port,'current',confirm) or confirm
    second = port.send_mission(confirm,action)
    assert not second['mission_dispatched'] and len(calls)==1


def test_collect_and_dispatch_are_distinct_even_with_identical_labels(rig):
    manager, _, store = rig
    f = EventFrame('before',(7,'fixture-disk-7','adb','boot'),'mission-page','x')
    c = Control('mission-occurrence',BoundingBox(1,1,20,20),('one','two','three'),
                'reward',cost='FREE',available=True,period='proven-occurrence-1')
    calls=[]
    for kind in ('DISPATCH','COLLECT'):
        task=store.create_task_run(manager.namespace,'event',7,'display')
        def send(f,c,p,intent):
            intent()
            calls.append(kind)
        result=dispatch_once(store,task,manager.namespace,f,c,event_identity='mission',
            persistent_identity='fixture-disk-7',dispatch=send,action_type=kind,
            postcondition=lambda f,c:[dict(identity=f.identity,capture=f'{kind}-{n}',
                event='mission',page=f.page,reward=c.identity,
                state='RUNNING' if kind=='DISPATCH' else 'NOT_AVAILABLE',
                independent_evidence=['qualified-state-change']) for n in range(2)])
        assert result['journal']=='VERIFIED'
    assert calls==['DISPATCH','COLLECT']


def test_unknown_mission_or_wrong_context_does_not_become_available():
    image, _ = evidence('relic-dispatch-running')
    image[535:990,535:695]=0  # Occlude clocks/timers, retain qualified card context.
    assert all(r['state']=='UNKNOWN' for r in mission_rows(image,
        cv2.imread('assets/tasks/phase8/personal-task-tab.png'),reader=lambda _:[]))
    image[:400]=0
    assert mission_rows(image,cv2.imread('assets/tasks/phase8/personal-task-tab.png'),reader=lambda _:[])==()
