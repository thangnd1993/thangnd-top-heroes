"""Current-frame event notification discovery; no seasonal icon/name catalog."""
import hashlib
from dataclasses import asdict, dataclass, replace

import cv2
import numpy as np

from top_heroes_auto.vision.models import BoundingBox


@dataclass(frozen=True)
class BadgeCandidate:
    box: BoundingBox
    fingerprint: str
    rim_confidence: float
    qualified: bool
    icon_box: BoundingBox | None = None

    def evidence(self):
        return asdict(self)


def discover_badges(image, region):
    """Notification geometry only. Caller must prove Home/event-region context."""
    h, w = image.shape[:2]
    if (region.x < 0 or region.y < 0 or region.x+region.width > w or
            region.y+region.height > h or min(region.width, region.height) <= 0):
        raise ValueError('Discovery region must be inside current screenshot.')
    area = image[region.y:region.y+region.height, region.x:region.x+region.width]
    hsv = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 130, 160), (9, 255, 255)) | cv2.inRange(hsv, (170, 130, 160), (179, 255, 255))
    contours, _ = cv2.findContours(red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if not (.007*w <= bw <= .065*w and .007*w <= bh <= .045*w and .7 <= bw/bh <= 2.4):
            continue
        perimeter, size = cv2.arcLength(contour, True), cv2.contourArea(contour)
        if not perimeter or size/(bw*bh) < .5 or 4*np.pi*size/perimeter**2 < .55:
            continue
        mask = np.zeros(red.shape, np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, cv2.FILLED)
        outer = cv2.dilate(mask, np.ones((5,5), np.uint8))
        ring = (outer > 0) & (mask == 0)
        white = (hsv[:,:,1] < 85) & (hsv[:,:,2] > 185)
        confidence = float(np.count_nonzero(ring & white)/max(1, np.count_nonzero(ring)))
        bx, by = region.x+x, region.y+y
        # Run-local retrieval hint only, NEVER a journal/reset identity.
        side = max(2, round(w*.055))
        core = image[max(0,by+bh):min(h,by+bh+side), max(0,bx-side):bx]
        if not core.size:
            continue
        small = cv2.resize(cv2.cvtColor(core, cv2.COLOR_BGR2GRAY), (16,16))
        fingerprint = hashlib.sha256((small//16).tobytes()).hexdigest()
        candidates.append(BadgeCandidate(BoundingBox(bx,by,bw,bh), fingerprint,
                                         confidence, confidence >= .45))
    return tuple(sorted(candidates, key=lambda c: (c.box.y, c.box.x)))


def discover_events(image, region):
    """Associate a notification with ONE outlined current icon, never a red pixel alone."""
    h,w=image.shape[:2]
    badges=discover_badges(image,region)
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    white=cv2.inRange(hsv,(0,0,185),(179,85,255))
    bounded=np.zeros_like(white)
    bounded[region.y:region.y+region.height,region.x:region.x+region.width]=white[
        region.y:region.y+region.height,region.x:region.x+region.width]
    bounded=cv2.morphologyEx(bounded,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(bounded,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    icons=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if .045*w <= bw <= .16*w and .023*h <= bh <= .085*h:
            icons.append(BoundingBox(x,y,bw,bh))
    result=[]
    for badge in badges:
        cx,cy=badge.box.center
        matches=[box for box in icons if box.x+box.width*.55 <= cx <= box.x+box.width
                 and box.y <= cy <= box.y+box.height*.45
                 and box.y+box.height > badge.box.y+badge.box.height+8]
        result.append(replace(badge,qualified=badge.qualified and len(matches)==1,
                              icon_box=matches[0] if len(matches)==1 else None))
    return tuple(result)


def folded(text):
    import unicodedata

    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',text.lower())
                           if not unicodedata.combining(c)).split())


def event_shell(image, back, *, reader):
    """Shared gold-header/Back/tab chrome, independent of event names/artwork.

    This qualifies safe navigation only. Uninterpreted body content is never
    classified empty or free. Header OCR must agree on two independent renders.
    """
    h,w=image.shape[:2]
    if back is None or back.x > w*.18 or back.y < h*.90:
        return None
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    gold=cv2.inRange(hsv,(10,85,185),(38,255,255))
    # A full-width top header is separate evidence from its readable title.
    if np.count_nonzero(gold[:round(h*.07)])/(round(h*.07)*w) < .65:
        return None
    # Long translated titles extend beyond the old central 60% crop. Isolate
    # light glyph interiors from gold artwork before OCR. This is only a
    # run-local navigation identity, never a semantic reward/journal key.
    header=image[:round(h*.07),round(w*.08):round(w*.92)]
    glyphs=cv2.inRange(cv2.cvtColor(header,cv2.COLOR_BGR2HSV),(0,0,205),(179,90,255))
    header=cv2.copyMakeBorder(cv2.cvtColor(255-glyphs,cv2.COLOR_GRAY2BGR),
                             20,20,20,20,cv2.BORDER_CONSTANT,value=(255,255,255))
    titles=[]
    for scale in (1,2):
        words=reader(cv2.resize(header,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC))
        title=folded(' '.join(word['text'] for word in words))
        if len(title)<3 or not any(c.isalpha() for c in title):
            return None
        titles.append(title)
    if titles[0]!=titles[1]:
        return None
    # Current highlighted tab supplies a local page identity, never reward/reset identity.
    bottom=round(h*.91)
    bar=cv2.inRange(hsv,(10,100,220),(38,255,255))[bottom:]
    bar[np.count_nonzero(bar,axis=1)>w*.65]=0
    bar=cv2.morphologyEx(bar,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    contours,_=cv2.findContours(bar,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    selected=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if .09*w < bw < .45*w and bh > .045*h:
            selected.append(BoundingBox(x,bottom+y,bw,bh))
    if len(selected)>1:
        return None
    signature='single-page'
    if selected:
        b=selected[0]
        core=image[b.y+round(b.height*.15):b.y+round(b.height*.75),
                   b.x+round(b.width*.25):b.x+round(b.width*.75)]
        signature=hashlib.sha256((cv2.resize(core,(24,24))//16).tobytes()).hexdigest()
    region=BoundingBox(round(w*.18),bottom,w-round(w*.18),h-bottom)
    tabs=[]
    for candidate in discover_events(image,region):
        if not candidate.qualified or not selected:
            continue
        box=candidate.icon_box
        if any(b.x <= box.center[0] <= b.x+b.width for b in selected):
            continue  # Never re-tap the currently selected tab's badge.
        tabs.append(candidate)
    return dict(title=titles[0],page='event:'+titles[0]+':'+signature,
                selected=[asdict(b) for b in selected],tabs=sorted(tabs,key=lambda c:c.icon_box.x),back=back)


def discover_menu_tiles(image):
    """Qualified rectangular seasonal menu grid, never a reward permission.

    Require multiple closed card outlines and one notification uniquely attached
    to a card corner. Partial cards remain unqualified; artwork/names are unused.
    Caller separately proves event-shell ownership before exposing these edges.
    """
    h,w=image.shape[:2]
    region=BoundingBox(0,round(h*.08),w,round(h*.90)-round(h*.08))
    edges=cv2.morphologyEx(cv2.Canny(image,40,120),cv2.MORPH_CLOSE,
                          cv2.getStructuringElement(cv2.MORPH_RECT,(5,5)))
    contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    cards=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if (.25*w < bw < .55*w and .12*h < bh < .35*h and
                region.y <= y and y+bh <= region.y+region.height and
                cv2.contourArea(contour)/(bw*bh) > .94):
            box=BoundingBox(x,y,bw,bh)
            if not any(abs(box.x-b.x)<8 and abs(box.y-b.y)<8 for b in cards):
                cards.append(box)
    if len(cards)<2:
        return ()
    result=[]
    for badge in discover_badges(image,region):
        cx,cy=badge.box.center
        matches=[b for b in cards if b.x+b.width*.85 <= cx <= b.x+b.width+5
                 and b.y-5 <= cy <= b.y+b.height*.12]
        if not badge.qualified or len(matches)!=1:
            continue
        b=matches[0]
        # Exclude changing timer and attention digits; retrieval is run-local.
        core=image[b.y+round(b.height*.35):b.y+round(b.height*.75),
                   b.x+round(b.width*.2):b.x+round(b.width*.8)]
        fingerprint=hashlib.sha256((cv2.resize(core,(24,24))//16).tobytes()).hexdigest()
        result.append(replace(badge,icon_box=b,fingerprint=fingerprint))
    return tuple(sorted(result,key=lambda c:(c.icon_box.y,c.icon_box.x)))


def task_reward_rows(image,context_template,*,reader):
    """Supported free task-card schema, independent of seasonal name/artwork.

    Exact selected task context, complete rounded row, reward inventory cells,
    a sole claim label in its separate right column and a green control must
    agree. Paid/other labels and attached numeric prices remain unqualified.
    Blue Go/grey claim state is unavailable only on the same qualified card.
    """
    h,w=image.shape[:2]
    if w != 720 or context_template is None:
        return ()  # Require the qualified portrait scale, not guessed scaling.
    scores=cv2.matchTemplate(image,context_template,cv2.TM_CCOEFF_NORMED)
    _,score,_,where=cv2.minMaxLoc(scores)
    if score<.98:
        return ()
    # Require one context, not two conflicting task panels.
    hits=(scores>=.98).astype(np.uint8)
    if cv2.connectedComponents(hits)[0]!=2:
        return ()
    below=where[1]+context_template.shape[0]
    edges=cv2.morphologyEx(cv2.Canny(image,40,120),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    rows=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if not (.90*w<bw<.97*w and .10*h<bh<.15*h and
                below<y and y+bh<h*.82 and cv2.contourArea(contour)/(bw*bh)>.97):
            continue
        row=BoundingBox(x,y,bw,bh)
        label=image[y+8:y+round(bh*.30),x+10:x+round(bw*.72)]
        # Stable text silhouette excludes reward counts, animation and position.
        glyph=cv2.inRange(cv2.cvtColor(label,cv2.COLOR_BGR2HSV),(0,45,25),(30,255,150))
        points=cv2.findNonZero(glyph)
        if points is None:
            continue
        lx,ly,lw,lh=cv2.boundingRect(points)
        if lw<80 or lh<10:
            continue
        identity=hashlib.sha256(cv2.resize(glyph[ly:ly+lh,lx:lx+lw],(160,24),
                                         interpolation=cv2.INTER_NEAREST).tobytes()).hexdigest()
        column=BoundingBox(x+round(bw*.76),y+round(bh*.30),round(bw*.23),round(bh*.65))
        crop=image[column.y:column.y+column.height,column.x:column.x+column.width]
        labels=[]
        for scale in (1,2):
            labels.append(folded(' '.join(q['text'] for q in reader(cv2.resize(crop,None,fx=scale,fy=scale)))))
        if labels[0]!=labels[1] or labels[0] not in {'nhan','nhan nhanh','mien phi','den','da nhan'}:
            continue  # Cost text, digits, purchase requirement or noisy OCR.
        hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        green=cv2.inRange(hsv,(35,60,80),(85,255,255))
        blue=cv2.inRange(hsv,(85,60,80),(115,255,255))
        masks=green if labels[0] not in {'den','da nhan'} else blue
        cs,_=cv2.findContours(masks,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        boxes=[]
        for c in cs:
            bx,by,bww,bhh=cv2.boundingRect(c)
            if bww>.18*w and .035*h<bhh<.075*h and cv2.contourArea(c)/(bww*bhh)>.80:
                boxes.append(BoundingBox(column.x+bx,column.y+by,bww,bhh))
        if len(boxes)!=1:
            continue
        # Positive inventory evidence: at least three closed item tiles to the
        # LEFT of the separate action column. Contents are rewards, not costs.
        items=[]
        for c in contours:
            ix,iy,iw,ih=cv2.boundingRect(c)
            if (x+round(bw*.13)<ix and ix+iw<column.x and y+bh*.35<iy<y+bh*.55
                    and .08*w<iw<.14*w and .85<iw/ih<1.15
                    and cv2.contourArea(c)/(iw*ih)>.80):
                if not any(abs(ix-a)<8 for a in items):
                    items.append(ix)
        if len(items)<3:
            continue
        box=boxes[0]
        # All visible chromatic content in the action is green/white lettering
        # or its dark outline; an attached currency/item icon invalidates it.
        area=image[box.y+5:box.y+box.height-5,box.x+5:box.x+box.width-5]
        ah=cv2.cvtColor(area,cv2.COLOR_BGR2HSV)
        foreign=((ah[:,:,1]>100)&(ah[:,:,2]>120)&((ah[:,:,0]<30)|(ah[:,:,0]>85)))
        if labels[0]!='den' and np.count_nonzero(foreign)/foreign.size>.015:
            continue
        rows.append(dict(identity=identity,row=row,box=box,state='NOT_AVAILABLE' if labels[0] in {'den','da nhan'} else 'AVAILABLE',
                         evidence=('selected-task-context','complete-reward-card','inventory-reward-items',
                                   'sole-no-cost-action-label','qualified-control-color')))
    return tuple(sorted(rows,key=lambda r:r['row'].y))
