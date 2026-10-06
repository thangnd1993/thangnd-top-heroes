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


def decorative_signal_on_new_icon(image, region, candidate):
    """Exclude interior paint with one current owner and strict New-label proof.

    Missing/weak/duplicate New evidence and weak corner signals remain unknown.
    This grants no input permission.
    """
    from top_heroes_auto.vision.resources import template_folder

    if candidate.qualified or candidate.rim_confidence >= .2:
        return None
    h,w=image.shape[:2]
    white=cv2.inRange(cv2.cvtColor(image,cv2.COLOR_BGR2HSV),(0,0,185),(179,85,255))
    bounded=np.zeros_like(white)
    bounded[region.y:region.y+region.height,region.x:region.x+region.width]=white[
        region.y:region.y+region.height,region.x:region.x+region.width]
    contours,_=cv2.findContours(cv2.morphologyEx(bounded,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8)),
                              cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    badge=candidate.box
    owners=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if (.045*w <= bw <= .16*w and .023*h <= bh <= .085*h
                and x+2 <= badge.x and badge.x+badge.width <= x+bw-2
                and y+2 <= badge.y and badge.y+badge.height <= y+bh-2
                and badge.center[0] < x+bw*.75 and badge.center[1] > y+bh*.20):
            owners.append(BoundingBox(x,y,bw,bh))
    if len(owners)!=1:
        return _interior_paint(image, region, candidate)
    owner=owners[0]
    left=max(region.x,round(owner.x+owner.width*.35))
    top=max(region.y,round(owner.y-owner.height*.25))
    right=min(region.x+region.width,round(owner.x+owner.width*1.25))
    bottom=min(region.y+region.height,round(owner.y+owner.height*.50))
    crop=image[top:bottom,left:right]
    template=cv2.imread(str(template_folder().parent/'tasks/phase8/new-ribbon-core.png'))
    th,tw=template.shape[:2]
    if crop.shape[0]<th or crop.shape[1]<tw:
        return None
    scores=cv2.matchTemplate(crop,template,cv2.TM_CCOEFF_NORMED)
    _,score,_,(x,y)=cv2.minMaxLoc(scores)
    if not np.isfinite(score) or score<.98:
        return _interior_paint(image, region, candidate)
    scores[max(0,y-th//2):y+th//2+1,max(0,x-tw//2):x+tw//2+1]=-1
    label=BoundingBox(left+x,top+y,tw,th)
    if (scores.max()>=.98 or badge.center[0]>=label.center[0]-.2*tw
            or badge.center[1]<=label.y+.65*th):
        return None
    return dict(reason='DECORATIVE_RED_ON_NEW_ICON',owner=asdict(owner),
                new_label=asdict(label),new_confidence=float(score),badge=candidate.evidence())


def _interior_paint(image, region, candidate):
    """Complete outline plus deeply interior weak red facet; no input permission."""
    if candidate.qualified or candidate.rim_confidence >= .15:
        return None
    h,w=image.shape[:2]
    badge=candidate.box
    white=cv2.inRange(cv2.cvtColor(image,cv2.COLOR_BGR2HSV),(0,0,185),(179,85,255))
    bounded=np.zeros_like(white)
    bounded[region.y:region.y+region.height,region.x:region.x+region.width]=white[
        region.y:region.y+region.height,region.x:region.x+region.width]
    contours,_=cv2.findContours(cv2.morphologyEx(bounded,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8)),
                               cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    owners=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if (.045*w <= bw <= .16*w and .023*h <= bh <= .085*h
                and cv2.contourArea(contour)/(bw*bh) >= .70
                and x+bw*.15 <= badge.x and badge.x+badge.width <= x+bw*.80
                and y+bh*.20 <= badge.y and badge.y+badge.height <= y+bh*.80
                and badge.width <= bw*.20 and badge.height <= bh*.25):
            owners.append(BoundingBox(x,y,bw,bh))
    if len(owners)!=1:
        return None
    return dict(reason='DECORATIVE_RED_INSIDE_COMPLETE_ICON',
                owner=asdict(owners[0]),badge=candidate.evidence())


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
    # Two qualified glyph styles preserve both clean and antialiased fonts.
    # Each style needs two agreeing renders; competing positive titles fail
    # closed. A failed rendering is not repaired or guessed into another word.
    titles=set()
    for value,saturation,padding in ((205,90,20),(180,110,5)):
        glyphs=cv2.inRange(cv2.cvtColor(header,cv2.COLOR_BGR2HSV),
                          (0,0,value),(179,saturation,255))
        rendered=cv2.copyMakeBorder(cv2.cvtColor(255-glyphs,cv2.COLOR_GRAY2BGR),
            padding,padding,padding,padding,cv2.BORDER_CONSTANT,value=(255,255,255))
        readings=[]
        for scale in (1,2):
            words=reader(cv2.resize(rendered,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC))
            title=folded(' '.join(word['text'] for word in words))
            readings.append(title)
        if (readings[0]==readings[1] and len(readings[0])>=3
                and any(c.isalpha() for c in readings[0])):
            titles.add(readings[0])
    if len(titles)!=1:
        return None
    title=next(iter(titles))
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
    return dict(title=title,page='event:'+title+':'+signature,
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
        fingerprint=menu_art_key(image,b)
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
    return badge_counter(image,badges[0].box,reader=reader)


def badge_counter(image,box,*,reader):
    """Digits in one independently owned current badge; no action permission."""
    from top_heroes_auto.vision.local_ocr import counter

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


def contained_signal_on_known_icon(candidate,candidates,*,image=None):
    """An interior weak red patch adds no separate edge to its known owner."""
    box=candidate.icon_box
    if candidate.qualified or box is None:
        return False
    if candidate.rim_confidence>=.2 and not interior_ribbon_shape(image,candidate):
        return False
    b=candidate.box
    return (box.x<=b.x and b.x+b.width<=box.x+box.width*.8
            and box.y+box.height*.15<=b.y and b.y+b.height<=box.y+box.height
            and sum(c.qualified and c.icon_box==box for c in candidates)==1)


def interior_ribbon_shape(image,candidate):
    """Positive forked ribbon tail; partial/near-qualified circles stay unknown."""
    if image is None or candidate.rim_confidence>=.3:
        return False
    b=candidate.box
    crop=image[b.y:b.y+b.height,b.x:b.x+b.width]
    if crop.shape[:2]!=(b.height,b.width):
        return False
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    red=cv2.inRange(hsv,(0,130,160),(9,255,255)) | cv2.inRange(hsv,(170,130,160),(179,255,255))
    contours,_=cv2.findContours(red,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if len(contours)!=1:
        return False
    c=contours[0]
    polygon=cv2.approxPolyDP(c,cv2.arcLength(c,True)*.04,True).reshape(-1,2)
    if len(polygon)!=6 or cv2.isContourConvex(polygon):
        return False
    for i,(x,y) in enumerate(polygon):
        left,right=polygon[(i-1)%6],polygon[(i+1)%6]
        if left[0]>right[0]:
            left,right=right,left
        if (b.width*.25<x<b.width*.75 and y>b.height*.6
                and min(left[1],right[1])-y>=b.height*.15
                and abs(left[1]-right[1])<b.height*.15
                and left[0]<b.width*.25 and right[0]>b.width*.75):
            return True
    return False


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
        if ((all(len(re.findall(r'\d+\s*(?:ngay|days?)',t))>=2 for t in texts)
                or gallery_timer_evidence(image,gallery,reader=reader))
                and not any(re.search(r'\b(?:vnd|nhan|mien phi|mua ngay|purchase|buy|kich hoat)\b',t)
                            for t in texts)):
            return 'MENU_GRID'
        return 'UNSUPPORTED'
    reputation=reputation_information(image)
    # In the independently qualified summary, 'cá nhân' labels personal standing,
    # not a Nhận control. Do not erase any free/cost wording on other UI families.
    risk_texts=[re.sub(r'\bca nhan\b','',t) for t in texts] if reputation else texts
    if any(re.search(r'\b(?:vnd|nhan|mien phi|purchase|buy|kich hoat)\b',t) for t in risk_texts):
        return 'UNSUPPORTED'
    if guild_reminder_information(image):
        return 'GUILD_REMINDER_OUT_OF_SCOPE'
    if reputation:
        return 'REPUTATION_INFORMATION'
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
    if calendar_timeline(image, buttons, reader=reader):
        return 'SCHEDULE'
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



def gallery_timer_evidence(image,cards,*,reader):
    """Paired timer readings inside current closed cards, independent of artwork."""
    import re

    timers=0
    for b in cards:
        crop=image[b.y+round(b.height*.70):b.y+round(b.height*.86),b.x:b.x+b.width]
        mask=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(0,0,180),(179,100,255))
        rendered=cv2.copyMakeBorder(cv2.cvtColor(255-mask,cv2.COLOR_GRAY2BGR),
            10,10,10,10,cv2.BORDER_CONSTANT,value=(255,255,255))
        readings=[re.findall(r'(\d+)\s*(?:ngay|days?)',folded(' '.join(q['text']
            for q in reader(cv2.resize(rendered,None,fx=scale,fy=scale))))) for scale in (1,2)]
        if len(readings[0])==1 and readings[0]==readings[1]:
            timers+=1
    return timers>=2


def decorative_ribbon_on_icon(image,candidate):
    """Exact forked paint core plus current unique outline; never exposes a control."""
    from top_heroes_auto.vision.resources import template_folder

    box=candidate.icon_box
    if box is None or candidate.qualified or not interior_ribbon_shape(image,candidate):
        return None
    b=candidate.box
    if not (box.x+box.width*.15<=b.x and b.x+b.width<=box.x+box.width*.80
            and box.y+box.height*.20<=b.y and b.y+b.height<=box.y+box.height*.80):
        return None
    template=cv2.imread(str(template_folder().parent/'tasks/phase8/decorative-ribbon-core.png'))
    crop=image[b.y:b.y+b.height,b.x:b.x+b.width]
    if template is None or crop.shape!=template.shape:
        return None
    score=float(cv2.matchTemplate(crop,template,cv2.TM_CCOEFF_NORMED)[0,0])
    if not np.isfinite(score) or score<.995:
        return None
    return dict(reason='DECORATIVE_FORKED_RIBBON',owner=asdict(box),
                core_confidence=score,badge=candidate.evidence())

def guild_reminder_information(image):
    """Qualified Guild-boss reminder, excluded by the Phase8-only scope.

    This exposes no navigation or read-all action. New rows/buttons/notifications
    invalidate the contract rather than being silently declared exhausted.
    """
    names=('reminder-title','reminder-timezone','reminder-guild-boss','reminder-read-all')
    title,zone,boss,read=[body_label_box(image,n) for n in names]
    if not all((title,zone,boss,read)) or not title.y<zone.y<boss.y<read.y:
        return False
    buttons=body_action_boxes(image)
    if len(buttons)!=2:
        return False
    read_buttons=[b for b in buttons if b.x<read.x and read.x+read.width<b.x+b.width
                  and b.y<read.y and read.y+read.height<b.y+b.height]
    go_buttons=[b for b in buttons if b.x>boss.x+boss.width
                and b.y<=boss.y+boss.height and boss.y<b.y+b.height]
    if len(read_buttons)!=1 or len(go_buttons)!=1 or read_buttons==go_buttons:
        return False
    for b in buttons:
        crop=image[b.y:b.y+b.height,b.x:b.x+b.width]
        blue=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(85,60,80),(115,255,255))
        if np.mean(blue>0)<.65:
            return False
    h,w=image.shape[:2]
    badges=[b for b in discover_badges(image,BoundingBox(0,round(h*.08),w,round(h*.83)))
            if b.qualified]
    go=go_buttons[0]
    return len(badges)<=1 and all(go.x+go.width*.75<b.box.center[0]<go.x+go.width+10
        and go.y-10<b.box.center[1]<go.y+go.height*.25 for b in badges)


def side_task_navigation(image):
    """Paired functional clipboard/Tasks label plus one owned current badge."""
    label=body_label_box(image,'side-tasks-label')
    core=body_label_box(image,'side-tasks-core')
    if not (label and core and core.y+core.height<=label.y and
            0<label.y-core.y-core.height<core.height and
            abs(label.center[0]-core.center[0])<label.width*.3):
        return None
    h,w=image.shape[:2]
    if not h*.08<core.y<label.y<h*.85:
        return None
    region=BoundingBox(max(0,core.x-core.width),max(0,core.y-core.height),
                       min(w-core.x+core.width,core.width*3),core.height*2)
    badges=[b for b in discover_badges(image,region) if b.qualified]
    owned=[b for b in badges if core.x+core.width*.5<b.box.center[0]<core.x+core.width*1.5
           and core.y-core.height*.7<b.box.center[1]<core.y+core.height*.1]
    if len(badges)!=1 or len(owned)!=1:
        return None
    return dict(box=core,badge=owned[0],evidence=('functional-tasks-label',
                'unique-clipboard-core','unique-owned-attention-badge'))


def reputation_information(image):
    """Generic reputation summary UI; conversion controls never authorize input."""
    names=('reputation-level','reputation-current','reputation-bonus','reputation-personal')
    boxes=[body_label_box(image,name) for name in names]
    if (not all(boxes) or body_action_boxes(image)
            or not all(a.y+a.height<b.y for a,b in zip(boxes,boxes[1:]))):
        return False
    nav=side_task_navigation(image)
    h,w=image.shape[:2]
    badges=[b for b in discover_badges(image,BoundingBox(0,round(h*.08),w,round(h*.83)))
            if b.qualified]
    return not badges or (nav is not None and len(badges)==1 and badges[0].box==nav['badge'].box)


def calendar_timeline(image, buttons, *, reader):
    """Current seven-day grid and arrow banners; no input permission.

    A green rectangular control is never treated as an informational banner.
    All candidate controls must lie inside the paired calendar/footer surfaces.
    """
    import re

    h,w=image.shape[:2]
    utc=body_label_box(image,'schedule-utc')
    rewards=body_label_box(image,'schedule-rewards')
    value=body_label_box(image,'schedule-value') or body_label_box(image,'schedule-value-orange')
    footer=body_label_box(image,'schedule-footer')
    if not (utc and rewards and value and footer and
            utc.y<rewards.y<value.y<footer.y<h*.91):
        return False
    dates=image[utc.y+utc.height+20:rewards.y-20]
    if not dates.size:
        return False
    for scale in (1,2):
        text=folded(' '.join(q['text'] for q in reader(cv2.resize(dates,None,fx=scale,fy=scale))))
        if len(re.findall(r'(?<!\d)\d{1,2}/\d{2}(?!\d)',text))<4:
            return False
    table=image[rewards.y+rewards.height+10:value.y-10]
    if not table.size:
        return False
    lines=cv2.morphologyEx(cv2.Canny(table,20,60),cv2.MORPH_OPEN,
                          np.ones((max(1,round(table.shape[0]*.1)),1),np.uint8))
    xs=np.flatnonzero(np.count_nonzero(lines,axis=0)>table.shape[0]*.15)
    groups=np.split(xs,np.flatnonzero(np.diff(xs)>4)+1)
    positions=[round(float(np.mean(g))) for g in groups if len(g)]
    # Banners can cover later columns. Require five consecutive evenly spaced
    # grid boundaries, plus independently readable dates and all three labels.
    groups_of_five=[np.diff(positions[i:i+5]) for i in range(len(positions)-4)]
    if not any(np.min(g)>.10*w and np.max(g)<.17*w and np.ptp(g)<6
               for g in groups_of_five):
        return False
    for b in buttons:
        if not rewards.y+rewards.height<b.y<b.y+b.height<footer.y:
            return False
        crop=image[b.y:b.y+b.height,b.x:b.x+b.width]
        green=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(35,60,80),(85,255,255))
        if np.mean(green>0)>.15:
            if b.y<value.y+value.height or not right_arrow_banner(green):
                return False
    return True


def right_arrow_banner(mask):
    """Positive pointed timeline shape; rounded/rectangular actions fail closed."""
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return False
    contour=max(contours,key=cv2.contourArea)
    filled=np.zeros_like(mask)
    cv2.drawContours(filled,[contour],-1,255,-1)
    h,w=mask.shape
    ends=[]
    for y in (round(h*.15),round(h*.5),round(h*.85)):
        xs=np.flatnonzero(filled[y])
        if not len(xs):
            return False
        ends.append(xs[-1])
    return bool(ends[1]-max(ends[0],ends[2])>h*.25 and abs(ends[0]-ends[2])<h*.15)


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
    components=cv2.connectedComponents((scores>=.98).astype(np.uint8))[0]
    if components>2:
        return None
    color_box=(BoundingBox(*where,template.shape[1],template.shape[0])
               if np.isfinite(score) and score>=.98 and components==2 else None)
    # Qualified functional glyph variants exclude animated artwork behind text.
    # Paired screen/clipboard roles are still required by the caller; this alone
    # grants no claim, page or navigation permission. Seasonal titles are absent.
    limits={'reputation-level':((15,100,150),(40,255,255)),
            'side-tasks-label':((0,0,180),(179,110,255))}.get(name)
    if limits is None:
        return color_box
    glyph=cv2.imread(str(template_folder().parent/'tasks/phase8'/f'{name}-glyph.png'),cv2.IMREAD_GRAYSCALE)
    if glyph is None or np.count_nonzero(glyph)<100:
        return color_box
    mask=cv2.inRange(cv2.cvtColor(image,cv2.COLOR_BGR2HSV),*limits)
    scores=cv2.matchTemplate(mask,glyph,cv2.TM_CCOEFF_NORMED)
    _,score,_,where=cv2.minMaxLoc(scores)
    components=cv2.connectedComponents((scores>=.995).astype(np.uint8))[0]
    if components>2:
        return None
    if not np.isfinite(score) or score<.995 or components!=2:
        return color_box
    glyph_box=BoundingBox(*where,glyph.shape[1],glyph.shape[0])
    if color_box and (abs(color_box.x-glyph_box.x)>4 or abs(color_box.y-glyph_box.y)>4):
        return None
    return glyph_box


def menu_art_image(image,box):
    """Current card core, excluding changing timer and corner notification."""
    core=image[box.y+round(box.height*.35):box.y+round(box.height*.75),
               box.x+round(box.width*.20):box.x+round(box.width*.80)]
    return cv2.resize(core,(24,24))


def menu_art_key(image,box):
    return hashlib.sha256((menu_art_image(image,box)//16).tobytes()).hexdigest()


def menu_view_key(image):
    """Same geometry with new artwork is a new view; ticking clocks are not."""
    cards=sorted(menu_card_boxes(image),key=lambda b:(b.y,b.x))
    return hashlib.sha256(repr([(b.x,b.y,b.width,b.height,menu_art_key(image,b))
                                for b in cards]).encode()).hexdigest()


def competitive_navigation_shell(image, back):
    """Functional competition chrome qualifies Back only, never a free reward.

    No title/artwork catalog. The challenge and reward menus do not constitute
    free-claim proof; unknown chest/counter semantics remain unsupported content.
    """
    from top_heroes_auto.vision.resources import template_folder

    h,w=image.shape[:2]
    if back is None or back.y<h*.90 or back.center[0]>w*.20:
        return None
    view=cv2.resize(image,(720,1280))
    boxes={}
    for role in ('reward-menu','personal-record','challenge'):
        template=cv2.imread(str(template_folder().parent/'tasks/phase8/competitive-navigation'/f'{role}.png'))
        if template is None:
            return None
        th,tw=template.shape[:2]
        # Match glyphs only so dynamic background/season art is irrelevant.
        def glyph(im):
            return cv2.inRange(cv2.cvtColor(im,cv2.COLOR_BGR2HSV),(0,0,185),(179,100,255))
        scores=cv2.matchTemplate(glyph(view),glyph(template),cv2.TM_CCOEFF_NORMED)
        _,score,_,(x,y)=cv2.minMaxLoc(scores)
        if not np.isfinite(score) or score<.98:
            return None
        scores[max(0,y-th//2):y+th//2+1,max(0,x-tw//2):x+tw//2+1]=-1
        if scores.max()>=.98:
            return None
        boxes[role]=BoundingBox(round(x*w/720),round(y*h/1280),round(tw*w/720),round(th*h/1280))
    reward,record,challenge=(boxes[k] for k in ('reward-menu','personal-record','challenge'))
    if (not h*.08 < reward.y < h*.25 or abs(reward.y-record.y)>h*.025
            or reward.x+reward.width>record.x or record.x+record.width>w*.6
            or not h*.75 < challenge.y < h*.9 or not w*.35 < challenge.center[0] < w*.7):
        return None
    return dict(title='competitive-structure',page='event:competitive:unqualified-rewards',
                selected=[],tabs=[],back=back,permission='BACK_ONLY',
                functional_anchors={k:asdict(v) for k,v in boxes.items()})


def competitive_rank_transition(image):
    """Bright rank word above dimmed functional chrome qualifies capture-only wait.

    The reusable word is not an Event title or reward identity. No announcement,
    challenge, gift, Back or dismissal input is authorized by this detector.
    """
    from top_heroes_auto.vision.resources import template_folder

    h,w=image.shape[:2]
    view=cv2.resize(image,(720,1280))
    gray=cv2.cvtColor(view,cv2.COLOR_BGR2GRAY)
    anchors={}
    confidences={}
    folder=template_folder().parent/'tasks/phase8/competitive-navigation'
    for role in ('personal-record','challenge'):
        template=cv2.imread(str(folder/f'{role}.png'))
        if template is None:
            return None
        th,tw=template.shape[:2]
        scores=cv2.matchTemplate(gray,cv2.cvtColor(template,cv2.COLOR_BGR2GRAY),cv2.TM_CCOEFF_NORMED)
        _,score,_,(x,y)=cv2.minMaxLoc(scores)
        if not np.isfinite(score) or score<.98:
            return None
        scores[max(0,y-th//2):y+th//2+1,max(0,x-tw//2):x+tw//2+1]=-1
        if scores.max()>=.98:
            return None
        anchors[role]=BoundingBox(x,y,tw,th)
        confidences[role]=float(score)
    record,challenge=(anchors[k] for k in ('personal-record','challenge'))
    if (not 1280*.08<record.y<1280*.25 or record.x+record.width>720*.6
            or not 1280*.75<challenge.y<1280*.9):
        return None

    def glyph(a):
        return cv2.inRange(cv2.cvtColor(a,cv2.COLOR_BGR2HSV),(10,50,185),(40,255,255))

    mask=glyph(view)
    matches=[]
    for variant in ('large','small'):
        template=cv2.imread(str(folder/f'rank-word-{variant}.png'))
        if template is None:
            return None
        th,tw=template.shape[:2]
        scores=cv2.matchTemplate(mask,glyph(template),cv2.TM_CCOEFF_NORMED)
        _,score,_,(x,y)=cv2.minMaxLoc(scores)
        if not np.isfinite(score) or score<.98:
            continue
        scores[max(0,y-th//2):y+th//2+1,max(0,x-tw//2):x+tw//2+1]=-1
        if scores.max()>=.98:
            return None
        if not 720*.15<x<x+tw<720*.85 or not 1280*.3<y<y+th<1280*.75:
            return None
        matches.append((score,BoundingBox(x,y,tw,th)))
    if not matches or any(abs(a[1].center[0]-b[1].center[0])>5 or
                          abs(a[1].center[1]-b[1].center[1])>5 for a in matches for b in matches):
        return None
    score,word=max(matches,key=lambda m:m[0])
    # Foreground/underlying contrast separates this announcement from normal UI.
    if np.mean(gray[record.y:record.y+record.height,record.x:record.x+record.width])>=140:
        return None
    anchors['rank-word']=word
    confidences['rank-word']=float(score)
    return dict(state='COMPETITIVE_RANK_TRANSITION',permission='WAIT_ONLY',
                confidence=min(confidences.values()),anchor_confidences=confidences,
                anchors={k:asdict(BoundingBox(round(b.x*w/720),round(b.y*h/1280),
                        round(b.width*w/720),round(b.height*h/1280))) for k,b in anchors.items()})


def achievement_navigation(image):
    """Qualified trophy + functional label + owned badge; navigation only.

    Current evidence has this nested reward entry on an unsupported body. Body
    coverage remains blocked; the entry never grants reward/paid input permission.
    """
    core = body_label_box(image, 'achievement-trophy-core')
    label = body_label_box(image, 'achievement-label')
    if not (core and label and core.y + core.height <= label.y
            and label.y - core.y - core.height < core.height
            and abs(core.center[0] - label.center[0]) < label.width * .2):
        return None
    h, w = image.shape[:2]
    left, top = max(0, core.x - core.width), max(0, core.y - core.height)
    right, bottom = min(w, core.x + core.width * 2), min(h, core.y + core.height)
    if not h * .08 < core.y < label.y < h * .85:
        return None
    badges = [b for b in discover_badges(image, BoundingBox(left, top, right-left, bottom-top))
              if b.qualified]
    if (len(badges) != 1 or not
            (core.x + core.width * .5 < badges[0].box.center[0] < core.x + core.width * 1.5
             and core.y - core.height < badges[0].box.center[1] < core.y)):
        return None
    return dict(box=core, badge=badges[0], evidence=(
        'unique-trophy-core', 'paired-achievement-label', 'owned-attention-badge', 'navigation-only'))
