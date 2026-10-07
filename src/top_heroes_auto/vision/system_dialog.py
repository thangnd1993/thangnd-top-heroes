"""Opaque Android dialog blocks input; recognition never authorizes dismissal."""
import re

import cv2

from top_heroes_auto.vision.dynamic_events import folded
from top_heroes_auto.vision.models import BoundingBox


def system_dialog(image, *, reader):
    h, w = image.shape[:2]
    white = cv2.inRange(image, (245, 245, 245), (255, 255, 255))
    panels = []
    for contour in cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(contour)
        if (.55*w < bw < .90*w and .12*h < bh < .40*h
                and .25*h < y < .70*h and abs(x+bw/2-w/2) < .08*w
                and cv2.contourArea(contour)/(bw*bh) > .90):
            panels.append(BoundingBox(x, y, bw, bh))
    if not panels:
        return None
    # Unreadable opaque dialogs cannot become empty Home scans either.
    reason = 'BLOCKING_SYSTEM_DIALOG'
    if len(panels) == 1:
        b = panels[0]
        crop = image[b.y:b.y+b.height, b.x:b.x+b.width]
        texts = [folded(' '.join(q['text'] for q in reader(cv2.resize(crop, None, fx=s, fy=s))))
                 for s in (1, 2)]
        # Windows OCR renders the font's capital I as lowercase l. This only
        # labels a blocker; it never grants input or relaxes claim evidence.
        if (all(re.search(r"system u[il] isn't responding", t) and 'close app' in t for t in texts)
                and any('wait' in t for t in texts)):
            reason = 'SYSTEM_UI_NOT_RESPONDING'
    return dict(reason=reason, panels=panels, input_allowed=False)
