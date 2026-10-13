"""Book objective UI: paired functional anchors, completed fraction, sole free control."""
import hashlib
import re

import cv2
import numpy as np

from top_heroes_auto.vision.dynamic_events import folded
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.resources import template_folder


def _ref(name):
    return cv2.imread(str(template_folder().parent/'tasks/phase8/season-objectives'/f'{name}.png'))


def _match(image,name,threshold=.995):
    ref=_ref(name)
    if ref is None or min(image.shape[0]-ref.shape[0],image.shape[1]-ref.shape[1])<0:
        return None
    scores=cv2.matchTemplate(image,ref,cv2.TM_CCOEFF_NORMED)
    _,score,_,(x,y)=cv2.minMaxLoc(scores)
    h,w=ref.shape[:2]
    if not np.isfinite(score) or score<threshold:
        return None
    scores[max(0,y-h//2):y+h//2+1,max(0,x-w//2):x+w//2+1]=-1
    return BoundingBox(x,y,w,h) if scores.max()<threshold else None


def book_context(image):
    # Fixed functional chrome, never Event art, day/count or account layout.
    daily,long,ledger=(_match(image,n) for n in ('daily-tab','long-tab','ledger-label'))
    if (not all((daily,long,ledger)) or abs(daily.y-long.y)>10
            or not daily.x+daily.width<long.x+10 or ledger.y>=daily.y-300):
        return None
    return dict(daily=daily,long=long,ledger=ledger,
        scroll=BoundingBox(ledger.x,ledger.y+ledger.height+150,round(image.shape[1]*.40),daily.y-ledger.y-ledger.height-180))


def book_label_glyph(image,row):
    crop=image[row.y:row.y+row.height,row.x:row.x+round(row.width*.69)]
    if not crop.size:
        return None
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(0,110,60),(24,240,205))
    points=cv2.findNonZero(mask)
    if points is None or len(points)<100:
        return None
    x,y,w,h=cv2.boundingRect(points)
    return cv2.resize(mask[y:y+h,x:x+w],(480,64),interpolation=cv2.INTER_NEAREST)


def book_rows(image,*,reader):
    context=book_context(image)
    if context is None:
        return ()
    h,w=image.shape[:2]
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    green=cv2.inRange(hsv,(35,65,90),(85,255,255))
    rows=[]
    for c in cv2.findContours(green,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(c)
        if not (w*.19<bw<w*.24 and h*.036<bh<h*.051 and x>w*.6
                and context['ledger'].y+100<y and y+bh<context['daily'].y-25
                and cv2.contourArea(c)/(bw*bh)>.70):
            continue
        box=BoundingBox(x,y,bw,bh)
        label=_match(image[y:y+bh,x:x+bw],'claim-label')
        if label is None:
            continue
        inside=hsv[y+5:y+bh-5,x+25:x+bw-25]
        # The action surface must contain only green plus white/dark caption.
        foreign=(inside[:,:,1]>110)&(inside[:,:,2]>120)&((inside[:,:,0]<30)|(inside[:,:,0]>90))
        if foreign.mean()>.01:
            continue
        left=context['ledger'].x-20
        row=BoundingBox(left,y-round(bh*.65),x+bw-left,round(bh*1.65)+8)
        caption=image[row.y:row.y+row.height,row.x:x-20]
        texts=[folded(' '.join(q['text'] for q in reader(cv2.resize(caption,None,fx=s,fy=s)))) for s in (2,3)]
        fractions=[re.findall(r'(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)',t) for t in texts]
        complete=(fractions[0]==fractions[1] and len(fractions[0])==1
                  and int(fractions[0][0][0])==int(fractions[0][0][1])>0)
        # Windows OCR renders the proven 1/1 glyph as l/l; exact colored glyph
        # evidence handles that variant without changing letters into numbers.
        complete=complete or _match(caption,'completed-one') is not None
        glyph=book_label_glyph(image,row)
        if not complete or glyph is None:
            continue
        rows.append(dict(identity=hashlib.sha256(glyph.tobytes()).hexdigest(),row=row,box=box,
            state='AVAILABLE',evidence=('qualified-book-objectives','complete-reward-card',
                'paired-functional-book-chrome','completed-objective-fraction','sole-no-cost-claim-label','qualified-control-color')))
    if len({r['identity'] for r in rows})!=len(rows):
        return ()
    return tuple(rows)
