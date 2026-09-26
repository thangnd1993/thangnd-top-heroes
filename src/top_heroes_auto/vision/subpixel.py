"""Strict subpixel render alignment; all boxes still come from the current frame."""
from dataclasses import replace

import cv2
import numpy as np

from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox


def unique_subpixel_anchor(screen, anchor):
    """Small rasterization variants, >=.98 and unique across every render offset."""
    template = cv2.imdecode(np.frombuffer(anchor.template.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    h, w = template.shape[:2]
    height, width = screen.normalized.shape[:2]
    left, top, right, bottom = anchor.expected_region.pixels(width, height)
    region = screen.normalized[top:bottom, left:right]
    threshold = max(.98, anchor.threshold)
    candidates = []
    best = 0.0
    margin = 3
    if min(h,w) <= margin*2 or region.shape[0] < h or region.shape[1] < w:
        return AnchorEvidence(anchor.id, anchor.state, best, threshold, False)
    for scale in (.98, 1., 1.02):
        for dx in (-.5, -.25, 0., .25, .5):
            for dy in (-.5, -.25, 0., .25, .5):
                matrix = cv2.getRotationMatrix2D((w/2, h/2), 0, scale)
                matrix[:,2] += dx, dy
                patch = cv2.warpAffine(template, matrix, (w,h))[margin:-margin,margin:-margin]
                scores = cv2.matchTemplate(region, patch, cv2.TM_CCOEFF_NORMED)
                for _ in range(2):
                    _, score, _, (x,y) = cv2.minMaxLoc(scores)
                    best = max(best,score)
                    if score < threshold:
                        break
                    box = BoundingBox(left+x-margin,top+y-margin,w,h)
                    candidates.append((score,box))
                    scores[max(0,y-h//2):y+h//2+1,max(0,x-w//2):x+w//2+1] = -1
    if not candidates:
        return AnchorEvidence(anchor.id,anchor.state,best,threshold,False)
    score, box = max(candidates,key=lambda v:v[0])
    evidence = AnchorEvidence(anchor.id,anchor.state,score,threshold,True,box,screen.to_device_box(box))
    if box.x < 0 or box.y < 0 or box.x+w > width or box.y+h > height or any(
        abs(other.center[0]-box.center[0]) > w/2 or abs(other.center[1]-box.center[1]) > h/2
        for _, other in candidates
    ):
        return replace(evidence,matched=False,normalized_box=None,device_box=None)
    return evidence
