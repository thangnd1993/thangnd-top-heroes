"""Evidence-qualified recovery states that may appear during app startup."""

from dataclasses import replace

from top_heroes_auto.vision.detector import ScreenDetector, load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import NormalizedRect, ScreenDetection, ScreenState
from top_heroes_auto.vision.resources import template_folder


class RecoveryScreenDetector:
    """Detect known loading/popup variants and require unique live-frame anchors."""

    _unique_anchor_prefixes = ("stranger-loading-", "login-assistance-")

    def __init__(self):
        templates = template_folder()
        self.anchors = load_anchors(templates)
        self.detector = ScreenDetector(self.anchors)
        promo_anchors = load_anchors(templates.parent / "tasks" / "phase6" / "promo")
        promo_cta_anchors = load_anchors(templates.parent / "tasks" / "phase6" / "promo-recovery")
        self.promo_title = self._full_frame_anchor(
            next(anchor for anchor in promo_anchors if anchor.id == "promo-stranger-title"),
            ScreenState.PROMO_BLOCKING,
        )
        self.promo_cta = self._full_frame_anchor(
            next(anchor for anchor in promo_cta_anchors if anchor.id == "promo-stranger-cta"),
            ScreenState.PROMO_BLOCKING,
        )
        loading_title = next(
            anchor for anchor in self.anchors if anchor.id == "stranger-loading-splash-title"
        )
        self.promo_loading_title = self._full_frame_anchor(
            loading_title,
            ScreenState.PROMO_LOADING,
        )

    @staticmethod
    def _full_frame_anchor(anchor, state):
        return replace(
            anchor,
            state=state,
            expected_region=NormalizedRect(0, 0, 1, 1),
            threshold=max(0.96, anchor.threshold),
            required=True,
        )

    def detect(self, screen):
        detected = self.detector.detect(screen)
        promo_title = unique_current_anchor(screen, self.promo_title)
        promo_cta = unique_current_anchor(screen, self.promo_cta)
        if promo_title.matched and promo_cta.matched:
            evidence = (promo_title, promo_cta)
            if detected.state not in {ScreenState.UNKNOWN, ScreenState.POPUP_GENERIC, ScreenState.GAME_LOADING} or (
                detected.state == ScreenState.UNKNOWN and detected.evidence
            ):
                return replace(
                    detected,
                    state=ScreenState.UNKNOWN,
                    confidence=0.0,
                    evidence=(*detected.evidence, *evidence),
                )
            return ScreenDetection(
                ScreenState.PROMO_BLOCKING,
                min(item.score for item in evidence),
                evidence,
                detected.timestamp,
                screen.source_image,
                detected.duration_ms,
            )

        loading_title = unique_current_anchor(screen, self.promo_loading_title)
        if loading_title.matched and detected.state == ScreenState.GAME_LOADING:
            return ScreenDetection(
                ScreenState.PROMO_LOADING,
                loading_title.score,
                (loading_title,),
                detected.timestamp,
                screen.source_image,
                detected.duration_ms,
            )

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
