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
