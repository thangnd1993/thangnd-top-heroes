"""Paired stable loading utility labels plus current progress-bar geometry.

No seasonal artwork, percentages or moving fill are templates. Recognition
permits waiting only; utility buttons are never actionable recovery controls.
"""
import cv2
import numpy as np

from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, ScreenState
from top_heroes_auto.vision.resources import template_folder


def loading_progress_evidence(screen):
    image=(cv2.rotate(screen.original,cv2.ROTATE_90_COUNTERCLOCKWISE)
           if screen.rotated_from_portrait else screen.original)
    h,w=image.shape[:2]
    if abs(w/h-720/1280)>.03:
        return ()
    image=cv2.resize(image,(720,1280))
    crop=image[:round(1280*.27),:round(720*.30)]
    evidence=[]
    boxes=[]
    for role in ('loading-help','loading-network'):
        template=cv2.imread(str(template_folder().parent/'tasks/phase8/loading'/f'{role}.png'))
        if template is None:
            return ()
        th,tw=template.shape[:2]
        def glyph(im):
            return cv2.inRange(cv2.cvtColor(im,cv2.COLOR_BGR2HSV),(0,0,185),(179,100,255))
        scores=cv2.matchTemplate(glyph(crop),glyph(template),cv2.TM_CCOEFF_NORMED)
        _,score,_,(x,y)=cv2.minMaxLoc(scores)
        if not np.isfinite(score) or score<.98:
            return ()
        scores[max(0,y-th//2):y+th//2+1,max(0,x-tw//2):x+tw//2+1]=-1
        if scores.max()>=.98:
            return ()
        box=BoundingBox(round(x*w/720),round(y*h/1280),round(tw*w/720),round(th*h/1280))
        boxes.append(box)
        evidence.append(AnchorEvidence(role,ScreenState.GAME_LOADING,float(score),.98,True,
                                       device_box=box))
    if not (boxes[0].y+boxes[0].height < boxes[1].y < h*.27):
        return ()
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,(10,100,170),(38,255,255))
    mask[:round(1280*.85)]=0
    mask[round(1280*.92):]=0
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    bars=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if (.55*720 < bw < .9*720 and 8 <= bh <= .035*1280
                and cv2.contourArea(contour)/(bw*bh)>.7 and .05*720 < x < .2*720):
            bars.append(BoundingBox(round(x*w/720),round(y*h/1280),round(bw*w/720),round(bh*h/1280)))
    if len(bars)!=1:
        return ()
    evidence.append(AnchorEvidence('loading-progress-bar',ScreenState.GAME_LOADING,1,.98,True,
                                  device_box=bars[0]))
    return tuple(evidence)


def progressing_stage(detection):
    return (detection.state==ScreenState.GAME_LOADING and
            {e.anchor_id for e in detection.evidence if e.matched and e.score>=.98}
            >= {'loading-help','loading-network','loading-progress-bar'})
