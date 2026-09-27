"""Unique text detail, excluding the low-frequency background behind a label."""
import cv2
import numpy as np

from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox


def unique_detail_anchor(screen, anchor):
    """One fixed high-pass transform, >=.98, and two-candidate ambiguity check.

    This is only supporting evidence: callers still require an independent
    page/title or a complete local badge. It never authorizes a tap by itself.
    """
    template = cv2.imdecode(np.frombuffer(anchor.template.read_bytes(), np.uint8), 1)
    height, width = screen.normalized.shape[:2]
    left, top, right, bottom = anchor.expected_region.pixels(width, height)
    region = screen.normalized[top:bottom, left:right]
    h, w = template.shape[:2]
    threshold = max(.98, anchor.threshold)
    if h > region.shape[0] or w > region.shape[1]:
        return AnchorEvidence(anchor.id, anchor.state, 0, threshold, False)

    def detail(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
        return gray-cv2.GaussianBlur(gray, (0,0), 2)

    scores = cv2.matchTemplate(detail(region), detail(template), cv2.TM_CCOEFF_NORMED)
    _, score, _, (x,y) = cv2.minMaxLoc(scores)
    if not np.isfinite(score) or score < threshold:
        return AnchorEvidence(anchor.id, anchor.state, float(score), threshold, False)
    scores[max(0,y-h//2):y+h//2+1,max(0,x-w//2):x+w//2+1] = -1
    if float(scores.max()) >= threshold:
        return AnchorEvidence(anchor.id, anchor.state, float(score), threshold, False)
    box = BoundingBox(left+x,top+y,w,h)
    return AnchorEvidence(anchor.id,anchor.state,float(score),threshold,True,box,screen.to_device_box(box))
