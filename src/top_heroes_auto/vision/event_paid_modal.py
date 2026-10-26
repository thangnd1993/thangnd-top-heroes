"""Qualified purchase modal permits only closing; content stays BLOCKED."""

import cv2
import numpy as np

from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.resources import template_folder


def _match(mask, name):
    # Raster variants are crops of real frames (run24 #3 added close '-raster2' and the VND
    # '-raster'); each still needs >=.995, uniqueness and positional agreement.
    names = {'close-red-core': (name, name+'-raster', name+'-raster2'),
             'purchase-remaining': (name, name+'-raster'),
             'vnd-word': (name, name+'-raster')}.get(name, (name,))
    matches=[]
    for variant in names:
        box, ambiguous = _match_variant(mask,variant)
        if ambiguous:
            return None
        if box is not None:
            matches.append(box)
    if not matches:
        return None
    first=matches[0]
    if any(abs(b.center[0]-first.center[0]) > first.width*.25 or
           abs(b.center[1]-first.center[1]) > first.height*.25 for b in matches):
        return None
    return first


def _match_variant(mask, name):
    ref = cv2.imdecode(
        np.frombuffer(
            (template_folder().parent / "tasks/phase8/paid-modal" / (name + ".png")).read_bytes(), np.uint8
        ),
        0,
    )
    if (
        ref is None
        or min(mask.shape) <= 0
        or any(a > b for a, b in zip(ref.shape, mask.shape))
        or ref.std() < 1
    ):
        return None, False
    scores = cv2.matchTemplate(mask, ref, cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(scores)
    h, w = ref.shape
    if not np.isfinite(score) or score < 0.995:
        return None, False
    scores[max(0, y - h // 2) : y + h // 2 + 1, max(0, x - w // 2) : x + w // 2 + 1] = -1
    if scores.max() >= 0.995:
        return None, True
    return BoundingBox(x, y, w, h), False


def contains(a, b):
    return a.x <= b.x and a.y <= b.y and b.x + b.width <= a.x + a.width and b.y + b.height <= a.y + a.height


def paid_modal_navigation(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 130, 120), (9, 255, 255)) | cv2.inRange(hsv, (170, 130, 120), (179, 255, 255))
    brown = cv2.inRange(hsv, (0, 90, 70), (25, 255, 220))
    white = cv2.inRange(hsv, (0, 0, 180), (179, 110, 255))
    close = _match(red, "close-red-core")
    remaining = _match(brown, "purchase-remaining")
    vnd = _match(white, "vnd-word")
    if not all((close, remaining, vnd)):
        return multi_offer_navigation(image,red,brown,white)
    h, w = image.shape[:2]
    edge = cv2.morphologyEx(cv2.Canny(image, 40, 120), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    panels = []
    for contour in cv2.findContours(edge, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(contour)
        box = BoundingBox(x, y, bw, bh)
        if (
            bw > w * 0.85
            and h * 0.60 < bh < h * 0.90
            and cv2.contourArea(contour) / (bw * bh) > 0.90
            and all(contains(box, b) for b in (close, remaining, vnd))
        ):
            panels.append(box)
    if len(panels) != 1:
        return None
    panel = panels[0]
    if not (
        close.x > panel.x + panel.width * 0.80
        and close.y < panel.y + panel.height * 0.12
        and panel.y + panel.height * 0.75 < remaining.y < vnd.y
    ):
        return None
    orange = cv2.inRange(hsv, (10, 100, 100), (35, 255, 255))
    prices = []
    for contour in cv2.findContours(orange, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(contour)
        b = BoundingBox(x, y, bw, bh)
        if (
            w * 0.20 < bw < w * 0.50
            and h * 0.03 < bh < h * 0.10
            and cv2.contourArea(contour) / (bw * bh) > 0.80
            and contains(b, vnd)
            and contains(panel, b)
        ):
            prices.append(b)
    if not prices:
        # A price tooltip can join the orange component to a decorative bubble.
        # The actual closed button contour must still contain VND, sit below
        # the purchase label, and have a strongly orange rectangular interior.
        for contour in cv2.findContours(edge, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
            x,y,bw,bh=cv2.boundingRect(contour)
            b=BoundingBox(x,y,bw,bh)
            if (w*.20 < bw < w*.50 and h*.03 < bh < h*.10
                    and cv2.contourArea(contour)/(bw*bh) > .90
                    and float(np.mean(orange[y:y+bh,x:x+bw] > 0)) > .80
                    and contains(b,vnd) and contains(panel,b)
                    and remaining.y+remaining.height <= b.y):
                prices.append(b)
    if len(prices) != 1 or not remaining.y + remaining.height <= prices[0].y:
        return None
    return dict(
        close=close,
        paid_region=prices[0],
        permission="NAVIGATION_ONLY",
        coverage_known=False,
        claim_authorized=False,
    )


def _all_glyphs(mask,name):
    ref=cv2.imread(str(template_folder().parent/'tasks/phase8/paid-modal'/f'{name}.png'),0)
    if ref is None or any(a>b for a,b in zip(ref.shape,mask.shape)):
        return ()
    scores=cv2.matchTemplate(mask,ref,cv2.TM_CCOEFF_NORMED)
    h,w=ref.shape
    boxes=[]
    for _ in range(8):
        _,score,_,(x,y)=cv2.minMaxLoc(scores)
        if not np.isfinite(score) or score<.995:
            return tuple(boxes)
        boxes.append(BoundingBox(x,y,w,h))
        scores[max(0,y-h//2):y+h//2+1,max(0,x-w//2):x+w//2+1]=-1
    return ()  # Repeated/unbounded texture is not a qualified offer layout.


def multi_offer_navigation(image,red,brown,white):
    """Only X: functional paid-offer label + explicit currency + owned panel."""
    close,ambiguous=_match_variant(red,'multi-close')
    labels=_all_glyphs(brown,'multi-offer-label')
    currency=(*_all_glyphs(white,'multi-vnd-word'),*_all_glyphs(white,'multi-vnd-old'))
    if close is None or ambiguous or not labels or not currency:
        return None
    for name in ('close-red-core','close-red-core-raster'):
        other,conflict=_match_variant(red,name)
        if conflict or (other is not None and
                       (abs(other.center[0]-close.center[0])>close.width*.25 or
                        abs(other.center[1]-close.center[1])>close.height*.25)):
            return None
    h,w=image.shape[:2]
    labels=sorted(labels,key=lambda b:b.y)
    if (max(b.x for b in labels)-min(b.x for b in labels)>5
            or any(not .10*h<b.y-a.y<.20*h for a,b in zip(labels,labels[1:]))):
        return None
    edge=cv2.morphologyEx(cv2.Canny(image,40,120),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    panels=[]
    for contour in cv2.findContours(edge,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(contour)
        panel=BoundingBox(x,y,bw,bh)
        if (bw>w*.85 and h*.60<bh<h*.90 and cv2.contourArea(contour)/(bw*bh)>.90
                and all(contains(panel,b) for b in (close,*labels,*currency))):
            panels.append(panel)
    if len(panels)!=1:
        return None
    panel=panels[0]
    if (close.x<panel.x+panel.width*.80 or close.y>panel.y+panel.height*.12
            or labels[0].y<panel.y+panel.height*.35
            or any(b.x>panel.x+panel.width*.30 for b in labels)
            or not all(any(c.x>label.x+panel.width*.45 and
                              .04*h<c.y-label.y<.12*h for label in labels) for c in currency)):
        return None
    # Exclude the entire content, including the unqualified upper gift.
    top=close.y+close.height+5
    return dict(close=close,paid_region=BoundingBox(panel.x,top,panel.width,panel.y+panel.height-top),
                permission='NAVIGATION_ONLY',coverage_known=False,claim_authorized=False)
