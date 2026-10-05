"""World HUD recognition authorizes only the current Return City view control."""
import cv2
import numpy as np

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, ScreenState
from top_heroes_auto.vision.resources import template_folder


def _hud_icon(screen, anchor):
    # Fixed bright, unsaturated icon strokes exclude changing map artwork.
    def strokes(image):
        return ((image.min(2) > 150) & (np.ptp(image, axis=2) < 70)).astype(np.uint8)*255

    template = cv2.imdecode(np.frombuffer(anchor.template.read_bytes(), np.uint8), 1)
    h, w = template.shape[:2]
    threshold = max(.99, anchor.threshold)
    image = screen.normalized
    if h > image.shape[0] or w > image.shape[1] or strokes(template).std() < 1:
        return AnchorEvidence(anchor.id, anchor.state, 0, threshold, False)
    scores = cv2.matchTemplate(strokes(image), strokes(template), cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(scores)
    if not np.isfinite(score) or score < threshold:
        return AnchorEvidence(anchor.id, anchor.state, float(score), threshold, False)
    scores[max(0,y-h//2):y+h//2+1, max(0,x-w//2):x+w//2+1] = -1
    if float(scores.max()) >= threshold:
        return AnchorEvidence(anchor.id, anchor.state, float(score), threshold, False)
    box = BoundingBox(x, y, w, h)
    return AnchorEvidence(anchor.id, anchor.state, float(score), threshold, True,
                          box, screen.to_device_box(box))


def world_evidence(screen):
    anchors = load_anchors(template_folder().parent / 'tasks/phase8/world-recovery')
    return tuple((_hud_icon if a.id in {'world-search', 'world-locator'}
                  else unique_current_anchor)(screen, a) for a in anchors)


def qualified_world(screen, evidence):
    roles = {e.anchor_id: e for e in evidence}
    if len(evidence) != 4 or set(roles) != {
        'world-return-label', 'world-return-castle', 'world-search', 'world-locator'
    }:
        return False
    if any(not e.matched or e.score < max(.99, e.threshold) or e.device_box is None for e in evidence):
        return False
    label, castle, search, locator = (roles[k].device_box for k in
                                    ('world-return-label', 'world-return-castle', 'world-search', 'world-locator'))
    width, height = screen.device_size or screen.original_size
    return (castle.center[0] > width*.8 and castle.y > height*.85
            and 0 <= label.y-(castle.y+castle.height) < height*.03
            and abs(label.center[0]-castle.center[0]) < width*.035
            and search.center[0] < width*.2 and height*.6 < search.y < height*.8
            and 0 < locator.y-(search.y+search.height) < height*.08
            and abs(locator.center[0]-search.center[0]) < width*.04)


def world_return_point(screen, detection):
    if (detection.state != ScreenState.GAME_WORLD or detection.confidence < .99
            or not qualified_world(screen, detection.evidence)):
        raise SafetyError('Return City requires current unique label, castle, search and locator HUD.')
    return next(e.device_box.center for e in detection.evidence if e.anchor_id == 'world-return-castle')
