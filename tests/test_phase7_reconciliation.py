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
    base = datetime.now(timezone.utc)
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
