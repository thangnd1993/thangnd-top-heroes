"""Functional event-promo footer pair; no seasonal artwork or timer templates."""
import cv2
import numpy as np

from top_heroes_auto.vision.models import (
    AnchorEvidence,
    BoundingBox,
    ScreenState,
)
from top_heroes_auto.vision.resources import template_folder


def event_promo_evidence(screen):
    image = (cv2.rotate(screen.original, cv2.ROTATE_90_COUNTERCLOCKWISE)
             if screen.rotated_from_portrait else screen.original)
    h, w = image.shape[:2]
    if abs(w/h-720/1280) > .03:
        return ()
    normalized = cv2.resize(image, (720,1280))
    evidence = []
    # These two separate UI controls must be unique and form the annotated
    # footer. Neither control is tapped; the existing overlay dismissal owns input.
    for role in ('go','hide-during-event'):
        variants = ('go','go-raster') if role == 'go' else (role,)
        matches = []
        for variant in variants:
            template = cv2.imread(str(template_folder().parent/'tasks/phase8/event-promo'/f'{variant}.png'))
            if template is None:
                return ()
            scores = cv2.matchTemplate(cv2.cvtColor(normalized,cv2.COLOR_BGR2GRAY),
                cv2.cvtColor(template,cv2.COLOR_BGR2GRAY),cv2.TM_CCOEFF_NORMED)
            _, score, _, (x,y) = cv2.minMaxLoc(scores)
            th, tw = template.shape[:2]
            if not np.isfinite(score) or score < .99:
                continue
            scores[max(0,y-th//2):y+th//2+1,max(0,x-tw//2):x+tw//2+1] = -1
            if scores.max() >= .99:
                return ()
            box = BoundingBox(round(x*w/720),round(y*h/1280),round(tw*w/720),round(th*h/1280))
            matches.append((float(score),box))
        if not matches:
            return ()
        score, box = max(matches,key=lambda m:m[0])
        if any(abs(b.center[0]-box.center[0]) > box.width/2 or
               abs(b.center[1]-box.center[1]) > box.height/2 for _,b in matches):
            return ()
        evidence.append(AnchorEvidence('event-promo-'+role,ScreenState.EVENT_PROMO,
            score,.99,True,device_box=box))
    go, hide = (e.device_box for e in evidence)
    if not (h*.79 < go.y < h*.88 and go.y+go.height < hide.y < h*.94
            and all(abs(b.center[0]-w*.5) < w*.08 for b in (go,hide))):
        return ()
    return tuple(evidence)
