import json
from copy import deepcopy
from dataclasses import asdict

from test_mission_repair import ROOT, evidence

from top_heroes_auto.automation.expedition_journal import (
    collection_period,
    dispatch_period,
    renewed_collection,
    renewed_dispatch,
)


def record(identifier, kind, *, status='VERIFIED', after=None, stamp='10:00:00'):
    return dict(id=identifier,reward_id='event:fixture',status=status,
        reserved_at=f'2026-10-14T{stamp}+00:00',verified_at=f'2026-10-14T{stamp}.900+00:00',
        before_evidence=json.dumps(dict(action_type=kind,persistent_identity='disk',
            capture=str(ROOT/'relic-dispatch-before.png'))),
        after_evidence=json.dumps(after or [dict(state='NOT_AVAILABLE',independent_evidence=['changed'])]*2))


def test_only_later_verified_collection_opens_next_dispatch_occurrence():
    old=record(1,'DISPATCH')
    collect=record(2,'COLLECT',stamp='12:00:00')
    rows=[old,collect]
    saved=deepcopy(rows)
    period=dispatch_period(rows,'disk')
    assert period=='after-expedition-collection:2'
    assert renewed_dispatch(old,period,rows,'disk')
    assert not renewed_dispatch({**old,'status':'RESERVED'},period,rows,'disk')
    assert not renewed_dispatch(old,'tomorrow',rows,'disk')
    assert not renewed_dispatch(old,period,rows,'another-disk')
    assert rows==saved


def test_unrelated_reward_or_prior_collection_does_not_renew_send():
    old=record(1,'DISPATCH',stamp='12:00:00')
    prior=record(2,'COLLECT')
    assert not renewed_dispatch(old,dispatch_period([old,prior],'disk'),[old,prior],'disk')
    assert dispatch_period([{**prior,'reward_id':'vip-daily'}],'disk')=='unknown-period'
    assert dispatch_period([{**prior,'status':'RESERVED'}],'disk')=='unknown-period'


def test_later_proven_running_mission_is_an_independent_collection_occurrence():
    image, rows=evidence('relic-dispatch-before')
    observations=[dict(state='RUNNING',capture=str(ROOT/(name+'.png')),
        transitions=[dict(row=asdict(r['row']),before='DISPATCHABLE',after='WAITING') for r in rows])
        for name in ('relic-dispatch-running','relic-dispatch-running-confirmed')]
    old=record(1,'COLLECT')
    sent=record(2,'DISPATCH',stamp='12:00:00',after=observations)
    period=collection_period([old,sent],'disk',image,rows[0])
    assert period=='after-expedition-dispatch:2'
    assert renewed_collection(old,period,[old,sent],'disk')
    assert not renewed_collection({**old,'status':'RESERVED'},period,[old,sent],'disk')
    assert collection_period([{**sent,'status':'RESERVED'}],'disk',image,rows[0])=='unknown-period'
    other=image.copy()
    other[490:640,:530]=0
    assert collection_period([sent],'disk',other,rows[0])=='unknown-period'
