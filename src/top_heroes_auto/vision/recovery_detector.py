"""Evidence-qualified recovery states that may appear during app startup."""

from dataclasses import replace

from top_heroes_auto.vision.detector import ScreenDetector, load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.resources import template_folder


class RecoveryScreenDetector:
    """Detect known loading/popup variants and require unique live-frame anchors."""

    _unique_anchor_prefixes = ("stranger-loading-", "login-assistance-")

    def __init__(self):
        self.anchors = load_anchors(template_folder())
        self.detector = ScreenDetector(self.anchors)

    def detect(self, screen):
        detected = self.detector.detect(screen)
        if detected.state not in {ScreenState.GAME_LOADING, ScreenState.POPUP_GENERIC}:
            return detected
        if not any(
            item.anchor_id.startswith(self._unique_anchor_prefixes)
            for item in detected.evidence
        ):
            return detected

        anchors = {anchor.id: anchor for anchor in self.anchors}
        evidence = tuple(
            unique_current_anchor(screen, anchors[item.anchor_id])
            for item in detected.evidence
        )
        if not evidence or any(not item.matched for item in evidence):
            return replace(
                detected,
                state=ScreenState.UNKNOWN,
                confidence=0,
                evidence=evidence or detected.evidence,
            )
        return replace(
            detected,
            confidence=min(item.score for item in evidence),
            evidence=evidence,
        )
