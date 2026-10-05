"""Functional task modal; complete current cards only, no Go/task execution."""
import re
from dataclasses import asdict

import cv2
import numpy as np

from top_heroes_auto.vision.dynamic_events import folded
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.resources import template_folder


def _anchor(view,name):
    ref=cv2.imread(str(template_folder().parent/'tasks/phase8/task-grid'/f'{name}.png'))
    if ref is None:
        return None
    scores=cv2.matchTemplate(view,ref,cv2.TM_CCOEFF_NORMED)
    _,score,_,(x,y)=cv2.minMaxLoc(scores)
    h,w=ref.shape[:2]
    if not np.isfinite(score) or score<.995:
        return None
    scores[max(0,y-h//2):y+h//2+1,max(0,x-w//2):x+w//2+1]=-1
    return BoundingBox(x,y,w,h) if scores.max()<.995 else None


def _contains(a,b):
    return a.x<=b.x and a.y<=b.y and b.x+b.width<=a.x+a.width and b.y+b.height<=a.y+a.height


def grid_label_glyph(image,row):
    crop=image[row.y+round(row.height*.50):row.y+round(row.height*.66),row.x+8:row.x+row.width-8]
    if not crop.size:
        return None
    mask=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(0,0,180),(179,110,255))
    return cv2.resize(mask,(160,56),interpolation=cv2.INTER_NEAREST)


def task_grid_shell(image):
    # Existing event transport uses portrait pixels. Normalize visual inspection,
    # then map every current box back to the actual captured image.
    h,w=image.shape[:2]
    view=cv2.resize(image,(720,1280))
    title,race,core=(_anchor(view,name) for name in ('tasks-word','race-word','close-core'))
    if (title is None or race is None or core is None or title.y>1280*.15 or core.y<1280*.85
            or abs(title.y-race.y)>4 or not 0<=race.x-title.x-title.width<20):
        return None
    edges=cv2.morphologyEx(cv2.Canny(view,40,120),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    panels=[]
    for c in contours:
        x,y,bw,bh=cv2.boundingRect(c)
        b=BoundingBox(x,y,bw,bh)
        if bw>720*.85 and bh>1280*.75 and cv2.contourArea(c)/(bw*bh)>.97 and _contains(b,title) and y+bh<core.y:
            panels.append(b)
    if not panels or any(abs(a.center[0]-b.center[0])>5 or abs(a.center[1]-b.center[1])>5 for a in panels for b in panels):
        return None
    panel=max(panels,key=lambda b:b.width*b.height)
    bottom=panel.y+panel.height-round(1280*.04)
    cards=[]
    for c in contours:
        x,y,bw,bh=cv2.boundingRect(c)
        b=BoundingBox(x,y,bw,bh)
        if (720*.20<bw<720*.30 and 1280*.25<bh<1280*.31 and cv2.contourArea(c)/(bw*bh)>.94
                and panel.y+1280*.25<y and y+bh<=bottom and _contains(panel,b)
                and not any(abs(x-a.x)<8 and abs(y-a.y)<8 for a in cards)):
            cards.append(b)
    if len(cards)<2 or max(b.width for b in cards)-min(b.width for b in cards)>8 or max(b.height for b in cards)-min(b.height for b in cards)>8:
        return None
    hsv=cv2.cvtColor(view,cv2.COLOR_BGR2HSV)
    red=cv2.inRange(hsv,(0,130,160),(9,255,255)) | cv2.inRange(hsv,(170,130,160),(179,255,255))
    closes=[]
    for c in cv2.findContours(red,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(c)
        b=BoundingBox(x,y,bw,bh)
        if .045*1280<bh<.09*1280 and .85<bw/bh<1.15 and cv2.contourArea(c)/(bw*bh)>.70 and _contains(b,core):
            closes.append(b)
    if len(closes)!=1:
        return None
    left=panel.x+round(panel.width*.03)
    right=min(b.x for b in cards)-3
    if right-left<20:
        return None
    scroll=BoundingBox(left,min(b.y for b in cards),right-left,bottom-min(b.y for b in cards))

    def mapped(b):
        return BoundingBox(round(b.x*w/720),round(b.y*h/1280),round(b.width*w/720),round(b.height*h/1280))

    return dict(title='functional-race-task-grid',page='event:functional-race-task-grid:race-task-grid',
        selected=[],tabs=[],back=mapped(closes[0]),permission='TASK_GRID',
        cards=tuple(mapped(b) for b in sorted(cards,key=lambda b:(b.y,b.x))),scroll=mapped(scroll),
        functional_anchors={'tasks-word':asdict(mapped(title)),'race-word':asdict(mapped(race)),'close-core':asdict(mapped(core))})


def _text(crop,reader,*,progress=False):
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(0,0,180),(179,110,255))
    if progress:
        mask |= cv2.inRange(hsv,(20,60,170),(85,255,255))
    rendered=cv2.copyMakeBorder(cv2.cvtColor(255-mask,cv2.COLOR_GRAY2BGR),10,10,10,10,cv2.BORDER_CONSTANT,value=(255,255,255))
    return [folded(' '.join(q['text'] for q in reader(cv2.resize(rendered,None,fx=s,fy=s)))) for s in ((2,3) if progress else (1,2))]


def task_grid_rows(image,shell,*,reader):
    rows=[]
    h,w=image.shape[:2]
    for b in shell['cards']:
        caption=_text(image[b.y+round(b.height*.50):b.y+round(b.height*.66),b.x+8:b.x+b.width-8],reader)
        if caption[0]!=caption[1] or len(caption[0])<10 or not any(c.isalpha() for c in caption[0]):
            continue  # No durable identity from a position, run or whole image hash.
        identity='task-caption:'+caption[0]
        column=BoundingBox(b.x+8,b.y+round(b.height*.80),b.width-16,round(b.height*.20)-3)
        crop=image[column.y:column.y+column.height,column.x:column.x+column.width]
        texts=[folded(' '.join(q['text'] for q in reader(cv2.resize(crop,None,fx=s,fy=s)))) for s in (1,2)]
        if texts[0]!=texts[1] or texts[0] not in {'nhan','mien phi','den','da nhan'}:
            continue
        hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        green=cv2.inRange(hsv,(35,60,80),(85,255,255))
        blue=cv2.inRange(hsv,(85,60,80),(115,255,255))
        unavailable=texts[0] in {'den','da nhan'}
        mask=blue if unavailable else green
        buttons=[]
        for c in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
            x,y,bw,bh=cv2.boundingRect(c)
            if bw>b.width*.60 and .028*h<bh<.07*h and cv2.contourArea(c)/(bw*bh)>.80:
                buttons.append(BoundingBox(column.x+x,column.y+y,bw,bh))
        if len(buttons)!=1:
            continue
        target=buttons[0]
        interior=image[target.y+4:target.y+target.height-4,target.x+4:target.x+target.width-4]
        color=cv2.cvtColor(interior,cv2.COLOR_BGR2HSV)
        unexplained=(color[:,:,1]>=100) & (color[:,:,2]>=160) & ((color[:,:,0]<30) | (color[:,:,0]>90))
        if not unavailable and np.mean(unexplained)>.015:
            continue  # A currency/item-colored cost cannot hide behind the Nhận OCR.
        progress=_text(image[b.y+round(b.height*.66):b.y+round(b.height*.78),b.x+8:b.x+b.width-8],reader,progress=True)
        fractions=[re.findall(r'(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)',t) for t in progress]
        progress_crop=image[b.y+round(b.height*.70):b.y+round(b.height*.80),b.x:b.x+b.width]
        progress_green=cv2.inRange(cv2.cvtColor(progress_crop,cv2.COLOR_BGR2HSV),(35,60,80),(85,255,255))
        bars=[]
        for contour in cv2.findContours(progress_green,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
            _,_,bw,bh=cv2.boundingRect(contour)
            if .75*b.width<bw<.90*b.width and .025*b.height<bh<.07*b.height and cv2.contourArea(contour)/(bw*bh)>.80:
                bars.append(contour)
        complete=(len(fractions[0])==1 and fractions[0]==fractions[1] and len(bars)==1
                  and int(fractions[0][0][0])==int(fractions[0][0][1])>0)
        state='NOT_AVAILABLE' if unavailable else ('AVAILABLE' if complete else 'UNKNOWN')
        rows.append(dict(identity=identity,row=b,box=buttons[0],family='race-task-grid',state=state,
            evidence=('qualified-race-task-grid','qualified-task-grid','complete-reward-card','qualified-control-color','independent-task-caption',
                      'blue-go-no-claim' if unavailable else 'completed-fraction-full-bar-and-free-label')))
    from collections import Counter

    counts=Counter(r['identity'] for r in rows)
    for row in rows:
        if counts[row['identity']]>1:
            row['state']='UNKNOWN'
            row['evidence']=(*row['evidence'],'ambiguous-task-caption')
    return tuple(rows)


def unresolved_grid_actions(image, shell, rows):
    """Do not declare a visible complete green action exhausted after OCR failure."""
    h, _ = image.shape[:2]
    unresolved = []
    for card in shell['cards']:
        column = BoundingBox(card.x+8, card.y+round(card.height*.80),
                             card.width-16, round(card.height*.20)-3)
        crop = image[column.y:column.y+column.height, column.x:column.x+column.width]
        mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (35,60,80), (85,255,255))
        for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            x,y,w,bh = cv2.boundingRect(contour)
            if w > card.width*.60 and .028*h < bh < .07*h:
                box = BoundingBox(column.x+x,column.y+y,w,bh)
                if not any(r['row']==card and _contains(box,r['box']) for r in rows):
                    unresolved.append(box)
    return tuple(unresolved)
