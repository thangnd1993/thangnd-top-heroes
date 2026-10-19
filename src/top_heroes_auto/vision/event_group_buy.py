"""Public completed objectives below a separately identified paid group-buy offer."""
import hashlib
import re
from collections import Counter

import cv2
import numpy as np

from top_heroes_auto.vision.dynamic_events import body_label_box, folded
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.template_cache import read_template


def group_buy_rows(image, *, reader, glyph_reader):
    h,w=image.shape[:2]
    title=body_label_box(image,'group-buy-title')
    package=body_label_box(image,'group-buy-package')
    if not title or not package or not title.y+title.height<package.y<h*.5:
        return ()
    edges=cv2.morphologyEx(cv2.Canny(image,40,120),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    headers,bodies=[],[]
    for c in cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(c)
        if (bw<w*.75 or bw>w*.9 or x<w*.1 or y<package.y+package.height
                or y+bh>h*.92 or cv2.contourArea(c)/(bw*bh)<.9):
            continue
        box=BoundingBox(x,y,bw,bh)
        target=headers if .025*h<bh<.055*h else bodies if .075*h<bh<.12*h else None
        if target is not None and not any(abs(x-b.x)<4 and abs(y-b.y)<4 for b in target):
            target.append(box)
    rows=[]
    for head in headers:
        below=[b for b in bodies if abs(b.x-head.x)<3 and abs(b.width-head.width)<3
               and abs(b.y-head.y-head.height)<4]
        if len(below)!=1:
            continue
        body=below[0]
        row=BoundingBox(head.x,head.y,head.width,body.y+body.height-head.y)
        header=image[head.y:head.y+head.height,head.x:head.x+head.width]
        paired=[]
        for name in ('prefix','suffix'):
            ref=read_template(template_folder().parent/'tasks/phase8'/f'group-buy-unlock-{name}.png')
            if ref is None or header.shape[0]<ref.shape[0] or header.shape[1]<ref.shape[1]:
                break
            score=cv2.matchTemplate(header,ref,cv2.TM_CCOEFF_NORMED)
            _,value,_,point=cv2.minMaxLoc(score)
            if not np.isfinite(value) or value<.98:
                break
            paired.append((point,ref.shape[1]))
        if len(paired)!=2 or paired[0][0][0]+paired[0][1]>=paired[1][0][0]:
            continue
        green_text=cv2.inRange(cv2.cvtColor(header,cv2.COLOR_BGR2HSV),(30,60,45),(85,255,220))
        points=cv2.findNonZero(green_text)
        if points is None:
            continue
        x,y,bw,bh=cv2.boundingRect(points)
        if x<=paired[1][0][0]+paired[1][1] or bh<12:
            continue
        digits=green_text[y:y+bh,x:x+bw]
        separators=set()
        for name in ('group-buy-counter-slash','group-buy-counter-slash-alt'):
            slash=read_template(template_folder().parent/'tasks/phase8'/f'{name}.png')
            if slash is None:
                continue
            slash=cv2.cvtColor(slash,cv2.COLOR_BGR2GRAY)
            if digits.shape[0]<slash.shape[0] or digits.shape[1]<slash.shape[1]:
                continue
            scores=cv2.matchTemplate(digits,slash,cv2.TM_CCOEFF_NORMED)
            _,score,_,(sx,sy)=cv2.minMaxLoc(scores)
            scores[max(0,sy-5):sy+6,max(0,sx-3):sx+4]=-1
            if score>=.995 and scores.max()<.995 and 5<sx and sx+slash.shape[1]<bw-5:
                separators.add((sx,slash.shape[1]))
        if len(separators)!=1:
            continue
        sx,sw=separators.pop()
        values=[]
        for part in (digits[:,:sx],digits[:,sx+sw:]):
            rendered=cv2.copyMakeBorder(cv2.cvtColor(255-part,cv2.COLOR_GRAY2BGR),
                15,15,15,15,cv2.BORDER_CONSTANT,value=(255,255,255))
            texts=[folded(' '.join(q['text'] for q in reader(cv2.resize(rendered,None,fx=s,fy=s)))) for s in (2,3)]
            if texts[0]!=texts[1] or not re.fullmatch(r'\d+',texts[0]):
                break
            values.append(int(texts[0]))
        if len(values)!=2:
            continue
        current,goal=values
        if not 0<=current<=goal or goal==0:
            continue
        glyph=glyph_reader(image,row)
        if glyph is None:
            continue
        column=BoundingBox(body.x+round(body.width*.65),body.y+8,
                           round(body.width*.34),body.height-16)
        crop=image[column.y:column.y+column.height,column.x:column.x+column.width]
        green=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(35,60,80),(85,255,255))
        buttons=[]
        for c in cv2.findContours(green,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
            x,y,bw,bh=cv2.boundingRect(c)
            if bw>column.width*.75 and .5*body.height<bh<.8*body.height and cv2.contourArea(c)/(bw*bh)>.9:
                buttons.append(BoundingBox(column.x+x,column.y+y,bw,bh))
        evidence=('qualified-inline-objectives','qualified-group-buy-objectives','complete-reward-card',
                  'paired-group-buy-functional-titles','public-objective-caption','separate-paid-package')
        state='UNKNOWN'
        box=column
        if len(buttons)==1 and current==goal:
            b=buttons[0]
            hsv=cv2.cvtColor(image[b.y+5:b.y+b.height-5,b.x+5:b.x+b.width-5],cv2.COLOR_BGR2HSV)
            white=cv2.inRange(hsv,(0,0,185),(179,90,255))
            foreign=(hsv[:,:,1]>100)&(hsv[:,:,2]>120)&((hsv[:,:,0]<30)|(hsv[:,:,0]>85))
            foreign &= cv2.dilate(white,np.ones((5,5),np.uint8))==0
            rendered=cv2.copyMakeBorder(cv2.cvtColor(255-white,cv2.COLOR_GRAY2BGR),15,15,15,15,
                                       cv2.BORDER_CONSTANT,value=(255,255,255))
            labels=[folded(' '.join(q['text'] for q in reader(cv2.resize(rendered,None,fx=s,fy=s)))) for s in (1,2)]
            if labels==['nhan','nhan'] and np.mean(foreign)<.015:
                state,box='AVAILABLE',b
                evidence+=('qualified-control-color','completed-objective-fraction','sole-no-cost-claim-label')
        elif not np.count_nonzero(green):
            labels=[folded(' '.join(q['text'] for q in reader(cv2.resize(crop,None,fx=s,fy=s)))) for s in (2,3)]
            if labels==['da nhan','da nhan']:
                state='NOT_AVAILABLE'
                evidence+=('explicit-claimed-label','original-green-control-absent')
            elif current<goal and labels==['chua dat','chua dat']:
                state='NOT_AVAILABLE'
                evidence+=('unmet-objective',)
        rows.append(dict(identity=hashlib.sha256(glyph.tobytes()).hexdigest(),row=row,box=box,
                         state=state,evidence=evidence))
    counts=Counter(r['identity'] for r in rows)
    for r in rows:
        if counts[r['identity']]!=1:
            r['state']='UNKNOWN'
    return tuple(sorted(rows,key=lambda r:r['row'].y))
