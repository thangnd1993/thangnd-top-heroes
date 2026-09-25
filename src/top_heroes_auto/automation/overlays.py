"""User-qualified bottom-left dismissal, only for positively known overlays."""

import math
from collections import Counter

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.models import ScreenState

DISMISSIBLE = frozenset({ScreenState.PROMO_AD, ScreenState.EVENT_PROMO, ScreenState.REWARD_RECEIPT,
                         ScreenState.HOME_OVERLAY, ScreenState.PROMO_BLOCKING})


def overlay_signature(detection):
    return (detection.state, tuple(sorted(e.anchor_id for e in detection.evidence if e.matched)))


def dismiss_overlay_bottom_left(screen, detection):
    """Calculate in actual device orientation; never in the rotated template plane."""
    if detection.state not in DISMISSIBLE or not math.isfinite(detection.confidence) or detection.confidence < .96:
        raise SafetyError("Screen is not a qualified dismissible overlay.")
    evidence = detection.evidence
    if len(evidence) < 2 or any(
        not e.matched or e.device_box is None or not math.isfinite(e.score)
        or e.score < max(.96, e.threshold) for e in evidence
    ):
        raise SafetyError("Overlay requires independent, confident current-frame anchors.")
    width, height = screen.device_size or screen.original_size
    if width <= 0 or height <= 0:
        raise SafetyError("Missing current screenshot dimensions.")
    return round(width * .08), round(height * .94)


class OverlayBudget:
    """Four total dismissals, at most one retry per positively recognized overlay."""

    def __init__(self, max_total=4, max_same=2):
        self.max_total = max_total
        self.max_same = max_same
        self.counts = Counter()
        self.total = 0

    def reserve(self, detection):
        signature = overlay_signature(detection)
        if detection.state not in DISMISSIBLE:
            raise SafetyError("Generic dismissal forbidden for this screen class.")
        if self.total >= self.max_total or self.counts[signature] >= self.max_same:
            raise SafetyError("Qualified overlay dismissal limit reached.")
        self.total += 1
        self.counts[signature] += 1
