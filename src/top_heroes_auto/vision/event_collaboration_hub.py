"""Qualified collaboration-map navigation; labels and badges grant no reward permission."""
from functools import lru_cache

import cv2
import numpy as np

from top_heroes_auto.vision.dynamic_events import discover_badges
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.resources import template_folder


def _white(image):
    return cv2.inRange(cv2.cvtColor(image, cv2.COLOR_BGR2HSV), (0, 0, 185), (179, 95, 255))


@lru_cache(maxsize=32)
def _references(name):
    folder = template_folder().parent/'tasks/phase8/collaboration-hub'
    return tuple(_white(cv2.imread(str(path))) for suffix in ('', '-current')
                 if (path := folder/f'{name}{suffix}.png').is_file())


def _unique(view, name):
    found = []
    glyphs = _white(view)
    for reference in _references(name):
        scores = cv2.matchTemplate(glyphs, reference, cv2.TM_CCOEFF_NORMED)
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        h, w = reference.shape[:2]
        if not np.isfinite(score) or score < .995:
            continue
        scores[max(0,y-h//2):y+h//2+1, max(0,x-w//2):x+w//2+1] = -1
        if scores.max() >= .995:
            return None  # A second raster must never rescue a duplicate.
        box = BoundingBox(x,y,w,h)
        if any(abs(box.center[0]-b.center[0]) > 2 or abs(box.center[1]-b.center[1]) > 2 for b in found):
            return None
        found.append(box)
    return found[0] if found else None


def collaboration_hub(image):
    h,w = image.shape[:2]
    view = cv2.resize(image,(720,1280))
    exit_box, preview = (_unique(view,n) for n in ('exit','preview-caption'))
    labels = {n:_unique(view,n) for n in ('training-caption','treasure-caption','collection-caption','training-rewards-caption')}
    if (exit_box is None or preview is None or exit_box.y < 1100 or preview.y > 400
            or abs(exit_box.center[0]-preview.center[0]) > 90
            or not all(labels.values())):
        return None
    badges = [b.box for b in discover_badges(view,BoundingBox(0,0,720,1280)) if b.qualified]
    controls = []
    for name,b in labels.items():
        if b is None:
            continue
        # A unique rimmed notification must be at this current label's upper-right.
        matches = [q for q in badges if b.x+b.width*.65 < q.center[0] < b.x+b.width+35
                   and b.y-90 < q.center[1] < b.y+12]
        if len(matches)==1:
            controls.append((name,b))
    def scaled(b):
        return BoundingBox(round(b.x*w/720),round(b.y*h/1280),round(b.width*w/720),round(b.height*h/1280))
    return dict(page='event:collaboration-hub',title='collaboration-hub',permission='NAVIGATION_HUB',
        back=scaled(exit_box),tabs=[],selected=[],children=[(n,scaled(b)) for n,b in controls],
        evidence=('paired-exit-preview-glyphs','multiple-current-menu-labels','unique-associated-notification'))


def collaboration_training(image):
    """Known combat map: only its explicit exit is qualified, never map chests."""
    h, w = image.shape[:2]
    view = cv2.resize(image, (720, 1280))
    title, stage, back = (_unique(view, n) for n in
                         ('training-page-title', 'training-stage-caption', 'training-back'))
    if (not all((title, stage, back)) or title.y > 90 or not title.y+title.height < stage.y < 190
            or back.y < 1150 or back.x > 140):
        return None
    exit_box = BoundingBox(round(back.x*w/720), round(back.y*h/1280),
                           round(back.width*w/720), round(back.height*h/1280))
    return dict(page='event:collaboration-training', title='collaboration-training',
                permission='KNOWN_BLOCKER_EXIT', back=exit_box, tabs=[], selected=[],
                evidence=('training-page-title', 'training-stage-caption', 'unique-training-back'))
