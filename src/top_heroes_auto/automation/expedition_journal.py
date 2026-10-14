"""Conservative occurrence transitions from existing independent receipts.

The clock/day and generic button label never open a new mission occurrence.
An older uncertain send remains locked even after another collection.
"""
import json
from pathlib import Path

import cv2
import numpy as np

from top_heroes_auto.automation.event_journal import action_kind
from top_heroes_auto.vision.relic_expedition import quick_send
from top_heroes_auto.vision.resources import template_folder


def qualifying_collection(row, persistent_identity):
    if (not row['reward_id'].startswith('event:') or row['status']!='VERIFIED'
            or action_kind(row)!='COLLECT'):
        return False
    proof=json.loads(row['before_evidence'])
    after=json.loads(row.get('after_evidence') or '[]')
    if (proof.get('persistent_identity')!=persistent_identity or not isinstance(after,list) or len(after)!=2
            or any(not isinstance(p,dict) or p.get('state')!='NOT_AVAILABLE'
                   or not p.get('independent_evidence') for p in after)):
        return False
    path=Path(proof.get('capture',''))
    if not path.is_file():
        return False
    image=cv2.imread(str(path))
    if image is None:
        return False
    if image.shape[1]>image.shape[0]:
        image=cv2.rotate(image,cv2.ROTATE_90_COUNTERCLOCKWISE)
    context=cv2.imread(str(template_folder().parent/'tasks/phase8/personal-task-tab.png'))
    return quick_send(image,context,reader=None) is not None


def dispatch_period(rows, persistent_identity):
    collections=[r for r in rows if qualifying_collection(r,persistent_identity)]
    if not collections:
        return 'unknown-period'
    latest=max(collections,key=lambda r:r['verified_at'])
    return 'after-expedition-collection:'+str(latest['id'])


def renewed_dispatch(row, period, rows, persistent_identity):
    """Only a VERIFIED send preceding a proven collection can be a past batch."""
    if row['status']!='VERIFIED' or action_kind(row)!='DISPATCH':
        return False
    prefix='after-expedition-collection:'
    if not period.startswith(prefix) or not period[len(prefix):].isdigit():
        return False
    parents=[r for r in rows if r['id']==int(period[len(prefix):])]
    return bool(len(parents)==1 and qualifying_collection(parents[0],persistent_identity)
                and row['verified_at'] and parents[0]['reserved_at']>row['verified_at'])


def collection_period(rows, persistent_identity, image, row):
    """Current complete reward card matches a previously proven running mission.

    The journal's two running observations must both match the current card's
    stable title/items. The action region is excluded; no pixel hash is a key.
    """
    b=row['row']
    current=image[b.y+6:b.y+b.height-6,b.x+8:b.x+round(b.width*.72)]
    eligible=[]
    for record in rows:
        proof=json.loads(record['before_evidence'])
        after=json.loads(record.get('after_evidence') or '[]')
        if (record['status']!='VERIFIED' or action_kind(record)!='DISPATCH'
                or proof.get('persistent_identity')!=persistent_identity or len(after)!=2):
            continue
        matched=True
        for frame in after:
            if frame.get('state')!='RUNNING' or not frame.get('transitions'):
                matched=False
                break
            saved=cv2.imread(frame['capture'])
            if saved is None:
                matched=False
                break
            if saved.shape[1]>saved.shape[0]:
                saved=cv2.rotate(saved,cv2.ROTATE_90_COUNTERCLOCKWISE)
            matches=0
            for change in frame['transitions']:
                q=change['row']
                crop=saved[q['y']+6:q['y']+q['height']-6,
                           q['x']+8:q['x']+round(q['width']*.72)]
                if crop.shape==current.shape:
                    score=float(cv2.matchTemplate(current,crop,cv2.TM_CCOEFF_NORMED)[0,0])
                    matches+=bool(np.isfinite(score) and score>=.995)
            if matches!=1:
                matched=False
                break
        if matched:
            eligible.append(record)
    if not eligible:
        return 'unknown-period'
    return 'after-expedition-dispatch:'+str(max(eligible,key=lambda r:r['verified_at'])['id'])


def renewed_collection(row, period, rows, persistent_identity):
    if row['status']!='VERIFIED' or action_kind(row)!='COLLECT':
        return False
    prefix='after-expedition-dispatch:'
    if not period.startswith(prefix) or not period[len(prefix):].isdigit():
        return False
    parents=[r for r in rows if r['id']==int(period[len(prefix):])]
    if len(parents)!=1:
        return False
    parent=parents[0]
    proof=json.loads(parent['before_evidence'])
    after=json.loads(parent.get('after_evidence') or '[]')
    return bool(parent['status']=='VERIFIED' and action_kind(parent)=='DISPATCH'
        and proof.get('persistent_identity')==persistent_identity and len(after)==2
        and all(a.get('state')=='RUNNING' and a.get('transitions') for a in after)
        and row['verified_at'] and parent['reserved_at']>row['verified_at'])
