"""Independent disabled VIP countdown, excluding changing digits from visual geometry."""
import re

import cv2

from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.local_ocr import read_words
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox


def countdown_box(image, *, reader=read_words):
    h,w=image.shape[:2]
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    gray=cv2.inRange(hsv,(0,0,135),(179,20,210))
    candidates=[]
    for c in cv2.findContours(gray,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,bw,bh=cv2.boundingRect(c)
        if not (.18*w<bw<.23*w and .038*h<bh<.055*h and 2.3<bw/bh<2.9
                and cv2.contourArea(c)/(bw*bh)>.90):
            continue
        crop=image[y+5:y+bh-6,x+round(bw*.12):x+bw-round(bw*.10)]
        text=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(0,0,185),(179,85,255))
        rendered=cv2.copyMakeBorder(cv2.cvtColor(255-text,cv2.COLOR_GRAY2BGR),20,20,20,20,
                                    cv2.BORDER_CONSTANT,value=(255,255,255))
        readings=[' '.join(q['text'] for q in reader(cv2.resize(rendered,None,fx=s,fy=s))) for s in (2,3)]
        # Run20: Windows OCR returns NO text at 2x on the disabled clock,
        # while 3x reads it cleanly. Padding the SAME complete glyphs gives
        # a second reading. Never replace conflicting/nonempty invalid text.
        if not readings[0] and re.fullmatch(r'\d{2}:\d{2}:\d{2}',readings[1]):
            padded=cv2.copyMakeBorder(rendered,10,10,10,10,cv2.BORDER_CONSTANT,value=(255,255,255))
            readings=[readings[1], ' '.join(q['text'] for q in reader(
                cv2.resize(padded,None,fx=3,fy=3)))]
        if readings[0]!=readings[1] or not re.fullmatch(r'\d{2}:\d{2}:\d{2}',readings[0]):
            continue
        hours,minutes,seconds=map(int,readings[0].split(':'))
        if not (hours<24 and minutes<60 and seconds<60 and hours+minutes+seconds>0):
            continue
        candidates.append(BoundingBox(x,y,bw,bh))
    return candidates[0] if len(candidates)==1 else None


def vip_anchor_match(screen,anchor):
    original=unique_current_anchor(screen,anchor)
    if anchor.id!='vip-post' or original.matched:
        return original
    view=cv2.rotate(screen.normalized,cv2.ROTATE_90_COUNTERCLOCKWISE)
    box=countdown_box(view)
    if box is None:
        return original
    # Boolean composite qualification: disabled rectangle AND two exact clock
    # readings. The adapter additionally requires VIP and absent claim controls.
    normalized=BoundingBox(view.shape[0]-box.y-box.height,box.x,box.height,box.width)
    return AnchorEvidence(anchor.id,anchor.state,1.0,anchor.threshold,True,
                          normalized,screen.to_device_box(normalized))
