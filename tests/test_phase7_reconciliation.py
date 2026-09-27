"""Original action evidence may resolve uncertainty; never create a new input."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from top_heroes_auto.automation.guild_mail_claims import Opportunity
from top_heroes_auto.automation.guild_mail_reconcile import (
    qualify_saved_guild_mail,
    reconcile_saved_guild_mail,
)
from top_heroes_auto.vision.models import BoundingBox


@pytest.fixture
def saved(rig,tmp_path,monkeypatch):
    manager,_,store = rig
    folder = tmp_path/'guild'
    folder.mkdir()
    base = datetime.now(timezone.utc)-timedelta(minutes=1)
    frames, evidence = {},[]
    for n in range(3):
        image = folder/f'{n}.png'
        item = dict(capture=str(image),index=7,name='Farm-007',adb='emulator-test',boot_id='boot',
                    timestamp=(base+timedelta(seconds=n)).isoformat())
        image.with_suffix('.json').write_text(json.dumps(dict(timestamp=item['timestamp'])),encoding='utf-8')
        frame = SimpleNamespace(page='gifts-member',captured=SimpleNamespace(source_image=image,index=7,
            name='Farm-007',serial='emulator-test',boot_id='boot',timestamp=item['timestamp']),evidence=lambda e=item:e)
        frames[str(image)] = frame
        evidence.append(item)
    geometry = dict(role='gifts-quick',bbox=dict(x=100,y=100,width=50,height=30),tap=[125,115],
                    forbidden=[],capture=evidence[0]['capture'])
    available = Opportunity('guild-gifts-member','AVAILABLE','gifts-quick',BoundingBox(100,100,50,30),12,'guild-gifts-member')
    unavailable = Opportunity('guild-gifts-member','NOT_AVAILABLE',remaining=0,context='guild-gifts-member')
    class Detector:
        def observe(self,frame):
            return frame
        def availability(self,frame,reward):
            return available if frame.captured.source_image.name == '0.png' else unavailable
        def action_geometry(self,*args):
            return geometry
    monkeypatch.setattr('top_heroes_auto.automation.guild_mail_reconcile.saved_frame',lambda e,f:frames[e['capture']])
    task = store.create_task_run(manager.namespace,'guild',7,'Farm-007')
    before = dict(frame=evidence[0],opportunity=available.evidence(),geometry=geometry,persistent_identity='disk')
    claim = store.reserve_reward_claim(task,'guild-gifts-member','progress:after-verified-0',json.dumps(before),
                                      expected_instance=(7,'Farm-007'),not_dispatched=True)
    store.mark_reward_dispatch(claim,task)
    action = dict(claim_id=claim,claim_dispatched=True,before=before,
                  post_observations=[dict(frame=evidence[1]),dict(frame=evidence[2])])
    report = dict(task_run_id=task,index=7,name='Farm-007',rewards={'guild-gifts-member':dict(actions=[action])})
    report_path = folder/'feature-report.json'
    report_path.write_text(json.dumps(report),encoding='utf-8')
    store.finish_task_run(task,'BLOCKED',report_path=str(report_path))
    transport = [dict(before=evidence[0]['capture'],action='tap',values=[125,115],outcome='DISPATCHED')]
    (folder/'actions.json').write_text(json.dumps(transport),encoding='utf-8')
    return SimpleNamespace(store=store,claim=claim,detector=Detector(),report=report,frames=frames,folder=folder,
                           action=action,transport=transport,evidence=evidence,namespace=manager.namespace)


def test_original_two_postframes_verify_without_transport(saved):
    before = saved.store.reward_claims(saved.namespace,7)[0]
    proof = qualify_saved_guild_mail(saved.store,saved.claim,detector=saved.detector)
    assert proof['proof']['claim_redispatched'] is False
    assert saved.store.reward_claims(saved.namespace,7)[0] == before
    result = reconcile_saved_guild_mail(saved.store,saved.claim,detector=saved.detector)
    assert result['result'] == 'VERIFIED' and result['claim_redispatched'] is False
    rows = saved.store.reward_claims(saved.namespace,7)
    assert len(rows) == 1 and rows[0]['status'] == 'VERIFIED'


@pytest.mark.parametrize('corruption',['duplicate','unknown','late','identity','two-taps','geometry'])
def test_ambiguous_saved_evidence_stays_possible(saved,corruption):
    if corruption == 'duplicate':
        saved.action['post_observations'][1] = saved.action['post_observations'][0]
    elif corruption == 'unknown':
        saved.frames[saved.evidence[1]['capture']].page = 'UNKNOWN'
    elif corruption == 'late':
        saved.frames[saved.evidence[1]['capture']].captured.timestamp = (
            datetime.fromisoformat(saved.evidence[0]['timestamp'])+timedelta(minutes=3)).isoformat()
    elif corruption == 'identity':
        saved.evidence[1]['boot_id'] = 'another-boot'
    elif corruption == 'two-taps':
        saved.transport.append(saved.transport[0])
    else:
        saved.transport[0]['values'] = [0,0]
    (saved.folder/'actions.json').write_text(json.dumps(saved.transport),encoding='utf-8')
    (saved.folder/'feature-report.json').write_text(json.dumps(saved.report),encoding='utf-8')
    with pytest.raises(ValueError):
        reconcile_saved_guild_mail(saved.store,saved.claim,detector=saved.detector)
    row = saved.store.reward_claims(saved.namespace,7)[0]
    assert row['status'] == 'RESERVED' and row['dispatch_state'] == 'POSSIBLE'
    assert not (saved.folder/f'claim-{saved.claim}-reconciled.json').exists()


@pytest.fixture
def fresh(saved):
    from top_heroes_auto.vision.models import AnchorEvidence, ScreenState

    saved.action['immediate_after'] = saved.evidence[1]
    saved.frames[saved.evidence[1]['capture']].overlay = SimpleNamespace(
        state=ScreenState.REWARD_RECEIPT,confidence=.995,
        evidence=[AnchorEvidence(n,ScreenState.REWARD_RECEIPT,.995,.98,True,device_box=BoundingBox(20,30,40,50))
                  for n in ('receipt-title','receipt-continue')])
    saved.frames[saved.evidence[1]['capture']].captured.device_size = (720,1280)
    (saved.folder/'feature-report.json').write_text(json.dumps(saved.report),encoding='utf-8')
    now = datetime.now(timezone.utc)
    frames = []
    for n,seconds in enumerate((20,10)):
        image = saved.folder/f'fresh{n}.png'
        evidence = dict(capture=str(image),index=7,name='Farm-007',adb='emulator-test',boot_id='new-verified-boot',
                        timestamp=(now-timedelta(seconds=seconds)).isoformat())
        frames.append(SimpleNamespace(page='gifts-member',captured=SimpleNamespace(source_image=image,index=7,
            name='Farm-007',serial='emulator-test',boot_id='new-verified-boot',timestamp=evidence['timestamp']),
            evidence=lambda e=evidence:e))
    return saved,frames


def test_fresh_exhausted_batch_with_original_receipt_verifies_without_input(fresh):
    from top_heroes_auto.automation.guild_mail_reconcile import reconcile_observed_guild_mail

    saved,frames = fresh
    proof = reconcile_observed_guild_mail(saved.store,saved.claim,saved.detector,frames,'disk')
    assert proof['claim_redispatched'] is False
    assert saved.store.reward_claims(saved.namespace,7)[0]['status'] == 'VERIFIED'


@pytest.mark.parametrize('bad',['identity','stale','duplicate','one','receipt_missing','receipt_unknown','unchanged','boot'])
def test_fresh_reconcile_failures_keep_original_possible(fresh,bad):
    from top_heroes_auto.automation.guild_mail_reconcile import reconcile_observed_guild_mail
    from top_heroes_auto.vision.models import ScreenState

    saved,frames = fresh
    identity = 'disk'
    if bad == 'identity':
        identity = 'replacement'
    elif bad == 'stale':
        frames[0].captured.timestamp = (datetime.now(timezone.utc)-timedelta(minutes=3)).isoformat()
    elif bad == 'duplicate':
        frames[1] = frames[0]
    elif bad == 'one':
        frames = frames[:1]
    elif bad == 'receipt_missing':
        del saved.action['immediate_after']
        (saved.folder/'feature-report.json').write_text(json.dumps(saved.report),encoding='utf-8')
    elif bad == 'receipt_unknown':
        saved.frames[saved.evidence[1]['capture']].overlay.state = ScreenState.UNKNOWN
    elif bad == 'boot':
        frames[1].captured.boot_id = 'changed-during-observation'
    else:
        previous = saved.detector.availability
        saved.detector.availability = lambda f,r: (Opportunity(r,'AVAILABLE',remaining=12,context=r)
            if f in frames else previous(f,r))
    with pytest.raises(ValueError):
        reconcile_observed_guild_mail(saved.store,saved.claim,saved.detector,frames,identity)
    row = saved.store.reward_claims(saved.namespace,7)[0]
    assert row['status'] == 'RESERVED' and row['dispatch_state'] == 'POSSIBLE'


@pytest.fixture
def delayed(saved):
    from top_heroes_auto.vision.models import AnchorEvidence, ScreenState

    base = datetime.fromisoformat(saved.evidence[0]['timestamp'])
    for n,seconds in ((1,100),(2,110)):
        timestamp = (base+timedelta(seconds=seconds)).isoformat()
        saved.evidence[n]['timestamp'] = timestamp
        frame = saved.frames[saved.evidence[n]['capture']]
        frame.captured.timestamp = timestamp
        frame.captured.source_image.with_suffix('.json').write_text(json.dumps(dict(timestamp=timestamp)),encoding='utf-8')
    for seconds in (10,80):
        image = saved.folder/f'popup{seconds}.png'
        timestamp = (base+timedelta(seconds=seconds)).isoformat()
        item = dict(capture=str(image),timestamp=timestamp,index=7,name='Farm-007',adb='emulator-test',boot_id='boot')
        metadata = dict(timestamp=timestamp,instance=dict(index=7,name='Farm-007'),adb_target='emulator-test',boot_id='boot')
        image.with_suffix('.json').write_text(json.dumps(metadata),encoding='utf-8')
        overlay = SimpleNamespace(state=ScreenState.REWARD_RECEIPT,confidence=.99,evidence=[
            AnchorEvidence(role,ScreenState.REWARD_RECEIPT,.99,.98,True,device_box=BoundingBox(20,30,40,50))
            for role in ('receipt-title','receipt-continue')])
        frame = SimpleNamespace(page='UNKNOWN',overlay=overlay,captured=SimpleNamespace(source_image=image,index=7,
            name='Farm-007',serial='emulator-test',boot_id='boot',timestamp=timestamp,device_size=(720,1280)),
            evidence=lambda e=item:e)
        saved.frames[str(image)] = frame
        if seconds == 10:
            saved.action['immediate_after'] = item
        else:
            saved.transport.append(dict(before=str(image),action='tap',values=[58,1203],outcome='DISPATCHED'))
    (saved.folder/'actions.json').write_text(json.dumps(saved.transport),encoding='utf-8')
    (saved.folder/'feature-report.json').write_text(json.dumps(saved.report),encoding='utf-8')
    return saved


def test_original_delayed_receipt_requires_bounded_dismissal_chain(delayed):
    result = reconcile_saved_guild_mail(delayed.store,delayed.claim,detector=delayed.detector)
    assert result['result'] == 'VERIFIED' and result['claim_redispatched'] is False


@pytest.mark.parametrize('bad',['another_input','wrong_dismissal','unknown_popup','late_post'])
def test_delayed_receipt_cannot_relax_generic_progress_guard(delayed,bad):
    from top_heroes_auto.vision.models import ScreenState

    if bad == 'another_input':
        delayed.transport.append(delayed.transport[-1])
    elif bad == 'wrong_dismissal':
        delayed.transport[-1]['values'] = [500,500]
    elif bad == 'unknown_popup':
        delayed.frames[str(delayed.folder/'popup80.png')].overlay.state = ScreenState.UNKNOWN
    else:
        frame = delayed.frames[delayed.evidence[2]['capture']]
        frame.captured.timestamp = (datetime.fromisoformat(delayed.evidence[0]['timestamp'])+timedelta(seconds=120)).isoformat()
    (delayed.folder/'actions.json').write_text(json.dumps(delayed.transport),encoding='utf-8')
    with pytest.raises(ValueError):
        reconcile_saved_guild_mail(delayed.store,delayed.claim,detector=delayed.detector)
    assert delayed.store.reward_claims(delayed.namespace,7)[0]['status'] == 'RESERVED'


def test_another_input_before_original_receipt_cannot_verify_fresh_state(fresh):
    from top_heroes_auto.automation.guild_mail_reconcile import reconcile_observed_guild_mail

    saved,frames = fresh
    saved.transport.append(dict(before=saved.evidence[1]['capture'],action='tap',values=[400,500],outcome='DISPATCHED'))
    (saved.folder/'actions.json').write_text(json.dumps(saved.transport),encoding='utf-8')
    with pytest.raises(ValueError,match='not a qualified dismissal'):
        reconcile_observed_guild_mail(saved.store,saved.claim,saved.detector,frames,'disk')
    assert saved.store.reward_claims(saved.namespace,7)[0]['status'] == 'RESERVED'


@pytest.mark.parametrize('receipt_ok',[True,False])
def test_process_resolves_original_or_keeps_lock_without_redispatch(fresh,receipt_ok):
    from top_heroes_auto.automation.guild_mail_claims import process
    from top_heroes_auto.vision.models import ScreenState

    saved,frames = fresh
    if not receipt_ok:
        saved.frames[saved.evidence[1]['capture']].overlay.state = ScreenState.UNKNOWN
    observations = iter(frames)
    seen = []
    def observe():
        seen.append('capture')
        return next(observations)
    port = SimpleNamespace(detector=saved.detector,observe=observe,
        opportunity=lambda reward:(frames[0],saved.detector.availability(frames[0],reward)),
        claim=lambda *a,**kw:pytest.fail('Original POSSIBLE action must never redispatch'))
    task = saved.store.create_task_run(saved.namespace,'guild',7,'Farm-007')
    report = {}
    process(port,saved.store,saved.namespace,task,'guild-gifts-member','disk',report,lambda:None)
    assert report['claim_count'] == 0 and report['claim_dispatched'] is False
    assert report['result'] == ('ALREADY_VERIFIED' if receipt_ok else 'ALREADY_ATTEMPTED')
    assert len(saved.store.reward_claims(saved.namespace,7)) == 1
    assert len(seen) == (2 if receipt_ok else 0)


@pytest.mark.parametrize('counts',[(1,1),(1,2),(12,12)])
def test_receipt_and_two_equal_independent_lower_counts_are_required(fresh,counts):
    from top_heroes_auto.automation.guild_mail_reconcile import reconcile_observed_guild_mail

    saved,frames = fresh
    previous = saved.detector.availability
    def availability(frame,reward):
        for n,f in enumerate(frames):
            if frame is f:
                return Opportunity(reward,'AVAILABLE','gifts-quick',BoundingBox(100,100,50,30),counts[n],reward)
        return previous(frame,reward)
    saved.detector.availability = availability
    if counts == (1,1):
        proof = reconcile_observed_guild_mail(saved.store,saved.claim,saved.detector,frames,'disk')
        assert proof['claim_redispatched'] is False
        assert proof['after'][0]['opportunity']['remaining'] == 1
    else:
        with pytest.raises(ValueError):
            reconcile_observed_guild_mail(saved.store,saved.claim,saved.detector,frames,'disk')
        assert saved.store.reward_claims(saved.namespace,7)[0]['status'] == 'RESERVED'


def test_proven_old_batch_then_one_remaining_batch_is_not_a_replay(fresh):
    from top_heroes_auto.automation.guild_mail_claims import process

    saved,frames = fresh
    first,second = frames
    previous = saved.detector.availability
    def available(reward,count):
        return Opportunity(reward,'AVAILABLE' if count else 'NOT_AVAILABLE','gifts-quick',
                           BoundingBox(100,100,50,30),count,reward)
    saved.detector.availability = lambda f,r:(available(r,1) if f is first or f is second else previous(f,r))
    for n in range(4):
        item = dict(first.evidence(),capture=str(saved.folder/f'next{n}.png'),
                    timestamp=(datetime.now(timezone.utc)-timedelta(seconds=8-n)).isoformat())
        frames.append(SimpleNamespace(page='gifts-member',captured=SimpleNamespace(source_image=saved.folder/f'next{n}.png',
            index=7,name='Farm-007',serial='emulator-test',boot_id='new-verified-boot',timestamp=item['timestamp']),
            evidence=lambda e=item:e))
    a,b,c,d = frames[2:]
    views = iter([(first,1),(a,1),(b,0),(c,0),(d,0)])
    captures = iter([first,second,b])
    inputs = []
    def opportunity(reward,initial=None):
        f,count = next(views)
        return f,available(reward,count)
    def claim(frame,view,*,before_input):
        before_input()
        inputs.append(frame)
    port = SimpleNamespace(detector=saved.detector,opportunity=opportunity,observe=lambda:next(captures),
                           geometry=lambda *a:dict(tap=[125,115]),claim=claim)
    task = saved.store.create_task_run(saved.namespace,'guild',7,'Farm-007')
    report = {}
    process(port,saved.store,saved.namespace,task,'guild-gifts-member','disk',report,lambda:None)
    rows = saved.store.reward_claims(saved.namespace,7)
    assert report['result'] == 'SUCCESS' and report['claim_count'] == len(inputs) == 1
    assert len(rows) == 2 and all(r['status'] == 'VERIFIED' for r in rows)
    assert rows[1]['cycle_key'] == f'progress:after-verified-{saved.claim}'
    assert inputs[0] is a  # Original claim and its two reconciliation captures got no input.


def test_safe_dismissal_bound_to_immediate_receipt_is_after_capture(fresh):
    from top_heroes_auto.automation.guild_mail_reconcile import reconcile_observed_guild_mail

    saved,frames = fresh
    saved.transport.append(dict(before=saved.evidence[1]['capture'],action='tap',values=[58,1203],outcome='DISPATCHED'))
    (saved.folder/'actions.json').write_text(json.dumps(saved.transport),encoding='utf-8')
    proof = reconcile_observed_guild_mail(saved.store,saved.claim,saved.detector,frames,'disk')
    assert proof['claim_redispatched'] is False


@pytest.fixture
def settling(fresh):
    from copy import copy

    from top_heroes_auto.vision.models import ScreenState

    saved,frames = fresh
    immediate = saved.frames[saved.evidence[1]['capture']]
    receipt = copy(immediate.overlay)
    immediate.page = 'UNKNOWN'
    immediate.overlay = SimpleNamespace(state=ScreenState.UNKNOWN,confidence=0,evidence=[])
    start = datetime.fromisoformat(saved.evidence[0]['timestamp'])
    def add(seconds, *, known=False):
        image = saved.folder/f'{seconds:02}-guild-mail.png'
        item = dict(saved.evidence[1],capture=str(image),timestamp=(start+timedelta(seconds=seconds)).isoformat())
        image.with_suffix('.json').write_text(json.dumps(dict(timestamp=item['timestamp'])),encoding='utf-8')
        image.with_name(image.stem+'.evidence.json').write_text(json.dumps(item),encoding='utf-8')
        frame = SimpleNamespace(page='mail' if known else 'UNKNOWN',overlay=copy(receipt),
            captured=SimpleNamespace(source_image=image,index=7,name='Farm-007',serial='emulator-test',
                boot_id='boot',timestamp=item['timestamp']),evidence=lambda e=item:e)
        saved.frames[str(image)] = frame
        return item,frame
    item,frame = add(20)
    return saved,frames,add,item,frame


def test_original_animation_can_settle_without_input_before_fresh_progress(settling):
    from top_heroes_auto.automation.guild_mail_reconcile import reconcile_observed_guild_mail

    saved,frames,_,item,_ = settling
    proof = reconcile_observed_guild_mail(saved.store,saved.claim,saved.detector,frames,'disk')
    assert proof['receipt']['capture'] == item['capture']
    assert proof['claim_redispatched'] is False
    assert len(saved.store.reward_claims(saved.namespace,7)) == 1
    assert saved.store.reward_claims(saved.namespace,7)[0]['status'] == 'VERIFIED'


@pytest.mark.parametrize('bad',['input','input_at_receipt','late','missing_anchor','wrong_boot',
                                'wrong_owner','known_screen','too_many','no_progress'])
def test_original_animation_chain_remains_fail_closed(settling,bad):
    from top_heroes_auto.automation.guild_mail_reconcile import reconcile_observed_guild_mail
    from top_heroes_auto.vision.models import ScreenState

    saved,frames,add,item,frame = settling
    sidecar = saved.folder/'20-guild-mail.evidence.json'
    if bad in {'input','input_at_receipt'}:
        saved.transport.append(dict(before=(saved.evidence[2]['capture'] if bad=='input' else item['capture']),
                                    action='tap',values=[500,500],outcome='DISPATCHED'))
        (saved.folder/'actions.json').write_text(json.dumps(saved.transport),encoding='utf-8')
    elif bad == 'late':
        sidecar.unlink()
        add(61)
    elif bad == 'missing_anchor':
        frame.overlay.evidence = frame.overlay.evidence[:1]
    elif bad in {'wrong_boot','wrong_owner'}:
        changed = dict(item,**({'boot_id':'another'} if bad=='wrong_boot' else {'capture':saved.evidence[1]['capture']}))
        sidecar.write_text(json.dumps(changed),encoding='utf-8')
    elif bad == 'known_screen':
        _,other = add(10,known=True)
        other.overlay.state = ScreenState.UNKNOWN
    elif bad == 'too_many':
        for seconds in range(3,8):
            _,other = add(seconds)
            other.overlay.state = ScreenState.UNKNOWN
    else:
        previous = saved.detector.availability
        saved.detector.availability = lambda f,r:(Opportunity(r,'AVAILABLE',remaining=12,context=r)
            if f in frames else previous(f,r))
    with pytest.raises(ValueError):
        reconcile_observed_guild_mail(saved.store,saved.claim,saved.detector,frames,'disk')
    row = saved.store.reward_claims(saved.namespace,7)[0]
    assert row['status'] == 'RESERVED' and row['dispatch_state'] == 'POSSIBLE'
