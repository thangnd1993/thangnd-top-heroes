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
    expanded=cv2.morphologyEx(bounded,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    extra_contours,_=cv2.findContours(expanded,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    extra_icons=[]
    for contour in extra_contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if .045*w <= bw <= .16*w and .023*h <= bh <= .085*h:
            extra_icons.append(BoundingBox(x,y,bw,bh))
    result=[]
    for badge in badges:
        cx,cy=badge.box.center
        matches=[box for box in icons if box.x+box.width*.55 <= cx <= box.x+box.width
                 and box.y <= cy <= box.y+box.height*.45
                 and box.y+box.height > badge.box.y+badge.box.height+8]
        if not matches and badge.qualified:
            matches=[box for box in extra_icons if box.x+box.width*.55 <= cx <= box.x+box.width
                     and box.y <= cy <= box.y+box.height*.45
                     and box.y+box.height > badge.box.y+badge.box.height+8]
        box=matches[0] if len(matches)==1 else None
        key=icon_core_key(image,box) if box else badge.fingerprint
        result.append(replace(badge,qualified=badge.qualified and len(matches)==1,
                              icon_box=box,fingerprint=key))
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
        signature=icon_core_key(image,b)
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


def menu_card_boxes(image):
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
    badges=discover_badges(image,region)
    known=list(cards)
    for badge in badges:
        if not badge.qualified or len(known)<3:
            continue
        cx,cy=badge.box.center
        for row in known:
            for column in known:
                if (abs(row.width-column.width)>5 or abs(row.height-column.height)>5
                        or abs(row.x-column.x)<row.width*.8 or abs(row.y-column.y)<row.height*.8):
                    continue
                b=BoundingBox(column.x,row.y,row.width,row.height)
                if (b.x<0 or b.x+b.width>w or b.y+b.height>region.y+region.height or
                        not (b.x+b.width*.85<=cx<=b.x+b.width+5 and b.y-5<=cy<=b.y+b.height*.12)):
                    continue
                mx,my=round(b.width*.05),round(b.height*.05)
                top_end=min(b.x+b.width-mx,badge.box.x-4)
                right_start=max(b.y+my,badge.box.y+badge.box.height+4)
                sides=[(edges[b.y-3:b.y+4,b.x+mx:top_end],0),
                    (edges[b.y+b.height-4:b.y+b.height+3,b.x+mx:b.x+b.width-mx],0),
                    (edges[b.y+my:b.y+b.height-my,b.x-3:b.x+4],1),
                    (edges[right_start:b.y+b.height-my,b.x+b.width-4:b.x+b.width+3],1)]
                if (top_end-b.x< b.width*.65 or any(not a.size or np.mean(np.any(a>0,axis=axis))<.95
                                                   for a,axis in sides)):
                    continue
                if not any(abs(b.x-q.x)<8 and abs(b.y-q.y)<8 for q in cards):
                    cards.append(b)
    return tuple(cards)


def discover_menu_tiles(image):
    """Unique current gallery card and notification; never a claim permission."""
    h,w=image.shape[:2]
    region=BoundingBox(0,round(h*.08),w,round(h*.90)-round(h*.08))
    cards=menu_card_boxes(image)
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


def task_context_box(image,template):
    if image.shape[1]!=720 or template is None:
        return None
    scores=cv2.matchTemplate(image,template,cv2.TM_CCOEFF_NORMED)
    _,score,_,where=cv2.minMaxLoc(scores)
    if score<.98 or cv2.connectedComponents((scores>=.98).astype(np.uint8))[0]!=2:
        return None
    return BoundingBox(*where,template.shape[1],template.shape[0])


def task_label_glyph(image, row):
    """Normalized caption glyphs, excluding action, amounts and background."""
    label = image[row.y+8:row.y+round(row.height*.30),
                  row.x+10:row.x+round(row.width*.72)]
    if not label.size:
        return None
    glyph = cv2.inRange(cv2.cvtColor(label, cv2.COLOR_BGR2HSV),
                        (0,45,25), (30,255,150))
    points = cv2.findNonZero(glyph)
    if points is None:
        return None
    x,y,w,h = cv2.boundingRect(points)
    if w < 80 or h < 10:
        return None
    return cv2.resize(glyph[y:y+h,x:x+w], (160,24), interpolation=cv2.INTER_NEAREST)


def task_reward_rows(image,context_template,*,reader):
    """Supported free task-card schema, independent of seasonal name/artwork.

    Exact selected task context, complete rounded row, reward inventory cells,
    a sole claim label in its separate right column and a green control must
    agree. Paid/other labels and attached numeric prices remain unqualified.
    Blue Go/grey claim state is unavailable only on the same qualified card.
    """
    h,w=image.shape[:2]
    context=task_context_box(image,context_template)
    if context is None:
        return ()
    below=context.y+context.height
    edges=cv2.morphologyEx(cv2.Canny(image,40,120),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    rows=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if not (.90*w<bw<.97*w and .10*h<bh<.15*h and
                below<y and y+bh<h*.82 and cv2.contourArea(contour)/(bw*bh)>.97):
            continue
        row=BoundingBox(x,y,bw,bh)
        glyph = task_label_glyph(image, row)
        if glyph is None:
            continue
        identity = hashlib.sha256(glyph.tobytes()).hexdigest()
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


def selected_task_badge_count(image, selected, *, reader):
    """Read a uniquely attached active-tab badge, never a claim permission.

    A letter-only OCR cue prevents Windows OCR dropping isolated small digits.
    The cue supplies no numeric value. Two renderings must agree on the sole
    original number; dots/exclamations/partial or conflicting glyphs fail closed.
    """
    from top_heroes_auto.vision.local_ocr import counter

    if len(selected) != 1:
        return None
    tab = selected[0]
    if isinstance(tab, dict):
        tab = BoundingBox(**tab)
    badges = [b for b in discover_badges(image, tab)
              if b.box.center[0] > tab.x+tab.width*.6
              and b.box.center[1] < tab.y+tab.height*.4]
    if len(badges) != 1 or not badges[0].qualified:
        return None
    box = badges[0].box
    inset = max(2, round(box.height*.14))
    crop = image[box.y+inset:box.y+box.height-inset,
                 box.x+inset:box.x+box.width-inset]
    if not crop.size:
        return None
    glyph = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (0,0,185), (179,90,255))
    n,_,stats,_ = cv2.connectedComponentsWithStats(glyph)
    components = [a for a in stats[1:n] if a[4] > 2]
    if not components:
        return None
    for a in components:
        for b in components:
            if a is b:
                continue
            overlap = min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0])
            if overlap > min(a[2],b[2])*.5 and (a[1]+a[3] <= b[1] or b[1]+b[3] <= a[1]):
                return None
    glyph = cv2.resize(cv2.cvtColor(255-glyph, cv2.COLOR_GRAY2BGR), None,
                       fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    canvas = np.full((max(160,glyph.shape[0]+100),max(460,glyph.shape[1]+370),3),255,np.uint8)
    cv2.putText(canvas,'Count',(20,95),cv2.FONT_HERSHEY_SIMPLEX,2,(0,0,0),3)
    canvas[50:50+glyph.shape[0],270:270+glyph.shape[1]] = glyph
    return counter(canvas, reader=reader, maximum=999)


def blank_event_render(image):
    """A blank render surface permits only bounded fresh captures, never input."""
    if image is None or image.ndim != 3:
        return False
    h,w=image.shape[:2]
    canvas=image[round(h*.02):round(h*.98),round(w*.08):round(w*.98)]
    if not canvas.size:
        return False
    return bool(np.mean(np.all(canvas >= 250,axis=2)) >= .999)


def icon_core_image(image,box):
    """Opposite-corner artwork excludes animation edges and notification digits."""
    core=image[box.y+round(box.height*.30):box.y+round(box.height*.70),
               box.x+round(box.width*.10):box.x+round(box.width*.50)]
    return cv2.resize(core,(24,24))


def icon_core_key(image,box):
    """Run-local artwork retrieval, never a durable reward/reset identity."""
    return hashlib.sha256((icon_core_image(image,box)//16).tobytes()).hexdigest()


def matching_icon_cores(core,known):
    """Strict pixel evidence, not identity permission; caller still proves live icon."""
    if float(np.std(core))<8:
        return ()
    return tuple(key for key,reference in known.items() if float(np.std(reference))>=8
                 and float(cv2.matchTemplate(core,reference,cv2.TM_CCOEFF_NORMED)[0,0])>=.995)


def contained_signal_on_known_icon(candidate,candidates):
    """An interior weak red patch adds no separate edge to its known owner."""
    box=candidate.icon_box
    if candidate.qualified or box is None or candidate.rim_confidence>=.2:
        return False
    b=candidate.box
    return (box.x<=b.x and b.x+b.width<=box.x+box.width*.8
            and box.y+box.height*.15<=b.y and b.y+b.height<=box.y+box.height
            and any(c.qualified and c.icon_box==box for c in candidates))


def task_card_boxes(image,template):
    context=task_context_box(image,template)
    if context is None:
        return ()
    h,w=image.shape[:2]
    edges=cv2.morphologyEx(cv2.Canny(image,40,120),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if (.90*w<bw<.97*w and .10*h<bh<.15*h and context.y+context.height<y
                and y+bh<h*.82 and cv2.contourArea(contour)/(bw*bh)>.97):
            box=BoundingBox(x,y,bw,bh)
            if not any(abs(x-b.x)<8 and abs(y-b.y)<8 for b in boxes):
                boxes.append(box)
    return tuple(boxes)


def body_action_boxes(image):
    """Potential button geometry is exclusion evidence, never claim permission."""
    h,w=image.shape[:2]
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    boxes=[]
    for low,high in [((10,100,185),(38,255,255)),((35,60,80),(85,255,255)),
                     ((85,60,80),(115,255,255))]:
        mask=cv2.inRange(hsv,low,high)
        mask[:round(h*.08)]=0
        mask[round(h*.91):]=0
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            x,y,bw,bh=cv2.boundingRect(c)
            if (.18*w<bw<.6*w and .035*h<bh<.09*h and cv2.contourArea(c)/(bw*bh)>.9):
                boxes.append(BoundingBox(x,y,bw,bh))
    return tuple(boxes)


def event_body_contract(image,rows,template,*,reader):
    """Positive reusable UI families; uninterpreted content remains unsupported."""
    h,w=image.shape[:2]
    cards=task_card_boxes(image,template)
    if cards:
        if len(cards)==len(rows) and all(r['state'] in {'AVAILABLE','NOT_AVAILABLE'} for r in rows):
            return 'TASK_LIST'
        return 'UNSUPPORTED'
    gallery=menu_card_boxes(image)
    buttons=body_action_boxes(image)
    body=BoundingBox(0,round(h*.08),w,round(h*.91)-round(h*.08))
    texts=[]
    region=image[body.y:body.y+body.height]
    for scale in (1,2):
        text=folded(' '.join(q['text'] for q in reader(cv2.resize(region,None,fx=scale,fy=scale))))
        texts.append(text)
    import re

    if len(gallery)>=3 and not any(any(overlap_boxes(b,c) for c in gallery) for b in buttons):
        if (all(len(re.findall(r'\d+\s*(?:ngay|days?)',t))>=2 for t in texts)
                and not any(re.search(r'\b(?:vnd|nhan|mien phi|mua ngay|purchase|buy|kich hoat)\b',t)
                            for t in texts)):
            return 'MENU_GRID'
        return 'UNSUPPORTED'
    if any(re.search(r'\b(?:vnd|nhan|mien phi|purchase|buy|kich hoat)\b',t) for t in texts):
        return 'UNSUPPORTED'
    if any(b.qualified for b in discover_badges(image,body)):
        return 'UNSUPPORTED'
    if all('sap bat dau' in t for t in texts) and len(buttons)==1:
        crop=image[buttons[0].y:buttons[0].y+buttons[0].height,
                   buttons[0].x:buttons[0].x+buttons[0].width]
        blue=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(85,60,80),(115,255,255))
        label=body_label_box(image,'world-list-label')
        if (np.count_nonzero(blue)/blue.size>.65 and label is not None
                and buttons[0].x<=label.center[0]<=buttons[0].x+buttons[0].width
                and buttons[0].y<=label.center[1]<=buttons[0].y+buttons[0].height):
            return 'COUNTDOWN_INFORMATION'
    utc=body_label_box(image,'schedule-utc')
    rewards=body_label_box(image,'schedule-rewards')
    value=body_label_box(image,'schedule-value')
    if (utc and rewards and value and utc.y<rewards.y<value.y
            and not any(np.mean(cv2.inRange(cv2.cvtColor(
                image[b.y:b.y+b.height,b.x:b.x+b.width],cv2.COLOR_BGR2HSV),
                (35,60,80),(85,255,255))>0)>.15 for b in buttons)):
        dates=image[utc.y+utc.height+20:rewards.y-20]
        date_texts=[folded(' '.join(q['text'] for q in reader(cv2.resize(dates,None,fx=s,fy=s))))
                    for s in (1,2)]
        table=image[rewards.y+rewards.height+10:value.y-10]
        lines=cv2.morphologyEx(cv2.Canny(table,20,60),cv2.MORPH_OPEN,
            np.ones((max(1,round(table.shape[0]*.1)),1),np.uint8))
        xs=np.flatnonzero(np.count_nonzero(lines,axis=0)>table.shape[0]*.35)
        groups=np.split(xs,np.flatnonzero(np.diff(xs)>4)+1)
        positions=[round(float(np.mean(g))) for g in groups if len(g)]
        gaps=np.diff(positions)
        if (all(len(re.findall(r'(?<!\d)\d{1,2}/\d{2}(?!\d)',t))>=4 for t in date_texts)
                and len(gaps)>=4 and np.min(gaps)>.10*w and np.max(gaps)<.17*w
                and np.max(gaps)-np.min(gaps)<6
                and all(rewards.y<b.y and b.y+b.height<value.y for b in buttons)):
            return 'SCHEDULE'
    return 'UNSUPPORTED'


def overlap_boxes(a,b):
    return a.x<b.x+b.width and b.x<a.x+a.width and a.y<b.y+b.height and b.y<a.y+a.height


def body_label_box(image,name):
    """Unique strict functional UI text anchor; never a seasonal title or action."""
    from top_heroes_auto.vision.resources import template_folder

    template=cv2.imread(str(template_folder().parent/'tasks/phase8'/f'{name}.png'))
    if template is None or template.shape[0]>image.shape[0] or template.shape[1]>image.shape[1]:
        return None
    scores=cv2.matchTemplate(image,template,cv2.TM_CCOEFF_NORMED)
    _,score,_,where=cv2.minMaxLoc(scores)
    if score<.98 or cv2.connectedComponents((scores>=.98).astype(np.uint8))[0]!=2:
        return None
    return BoundingBox(*where,template.shape[1],template.shape[0])
