"""Known competitive indicators, no fight/reward/menu input permission."""
from dataclasses import asdict

import cv2
import numpy as np

from top_heroes_auto.vision.dynamic_events import badge_counter, body_action_boxes, discover_badges
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.resources import template_folder


def competitive_indicator_contract(image,shell,*,reader):
    if shell.get('permission')!='BACK_ONLY':
        return None
    h,w=image.shape[:2]
    view=cv2.resize(image,(720,1280))
    if body_action_boxes(view):
        return None  # Additional free/paid controls are not covered by this family.
    folder=template_folder().parent/'tasks/phase8/competitive-navigation'
    ref=cv2.imread(str(folder/'free-chest-core.png'))
    if ref is None:
        return None
    scores=cv2.matchTemplate(view,ref,cv2.TM_CCOEFF_NORMED)
    _,score,_,(x,y)=cv2.minMaxLoc(scores)
    th,tw=ref.shape[:2]
    if not np.isfinite(score) or score<.995:
        return None
    scores[max(0,y-th//2):y+th//2+1,max(0,x-tw//2):x+tw//2+1]=-1
    if scores.max()>=.995:
        return None
    roles={k:BoundingBox(round(b['x']*720/w),round(b['y']*1280/h),
        round(b['width']*720/w),round(b['height']*1280/h)) for k,b in shell['functional_anchors'].items()}
    menu,challenge=roles['reward-menu'],roles['challenge']
    if not (x+tw<menu.x and 0<menu.y-y<1280*.06):
        return None
    left,top=x-round(tw*.35),y+th+round(th*.15)
    right,bottom=x+round(tw*1.35),y+th+round(th*.95)
    if min(left,top)<0 or right>720 or bottom>1280:
        return None
    crop=view[top:bottom,left:right]
    mask=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(0,0,180),(179,110,255))
    n,_,stats,_=cv2.connectedComponentsWithStats(mask)
    glyphs=sorted((q for q in stats[1:n] if q[4]>3),key=lambda q:q[0])
    if len(glyphs)!=3:
        return None
    # Positively read zero and fraction punctuation as qualified glyphs. Never
    # repair OCR's ambiguous "013" into "0/3" or assume the denominator value.
    for q,name in zip(glyphs[:2],('zero-core','fraction-slash'),strict=True):
        gx,gy,gw,gh,_=q
        template=cv2.imread(str(folder/f'{name}.png'))
        if template is None or template.shape[:2]!=(gh,gw):
            return None
        expected=cv2.inRange(cv2.cvtColor(template,cv2.COLOR_BGR2HSV),(0,0,180),(179,110,255))
        value=float(cv2.matchTemplate(mask[gy:gy+gh,gx:gx+gw],expected,cv2.TM_CCOEFF_NORMED)[0,0])
        if not np.isfinite(value) or value<.995:
            return None
    q=glyphs[2]
    denominator=badge_counter(view,BoundingBox(left+int(q[0])-2,top+int(q[1])-2,int(q[2])+4,int(q[3])+4),reader=reader)
    if denominator is None or denominator<1:
        return None
    badges=[b for b in discover_badges(view,BoundingBox(0,round(1280*.08),720,1280-round(1280*.08))) if b.qualified]
    battle=[b for b in badges if challenge.x+challenge.width<b.box.center[0]<challenge.x+challenge.width*1.5
            and challenge.y-challenge.height*1.5<b.box.center[1]<challenge.y-challenge.height*.1]
    if len(badges)!=2 or len(battle)!=1:
        return None
    tab=[b for b in badges if b not in battle and b.box.y>1280*.91]
    if len(tab)!=1:
        return None
    hsv=cv2.cvtColor(view,cv2.COLOR_BGR2HSV)
    gold=cv2.inRange(hsv,(10,100,220),(38,255,255))
    gold[:round(1280*.91)]=0
    gold[np.count_nonzero(gold,axis=1)>720*.65]=0
    gold=cv2.morphologyEx(gold,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    selected=[]
    for c in cv2.findContours(gold,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        tx,ty,bw,bh=cv2.boundingRect(c)
        if .09*720<bw<.45*720 and bh>.045*1280:
            selected.append(BoundingBox(tx,ty,bw,bh))
    if len(selected)!=1:
        return None
    b=tab[0].box
    t=selected[0]
    if not (t.x<b.x<b.x+b.width<t.x+t.width and t.y<=b.y<b.y+b.height<t.y+t.height*.5):
        return None
    counts=[badge_counter(view,b.box,reader=reader) for b in (battle[0],tab[0])]
    if counts[0] is None or counts[0]!=counts[1] or counts[0]<1:
        return None
    return dict(state='COMPETITIVE_OUT_OF_SCOPE_INDICATORS',permission='BACK_ONLY',
        chest_progress=0,chest_required=denominator,attempt_counter=counts[0],
        evidence=['paired-functional-navigation','zero-unclaimed-chest-progress',
                  'unique-battle-counter','matching-selected-tab-counter','no-other-notification-or-control'],
        indicators=[asdict(b.box) for b in (battle[0],tab[0])])
