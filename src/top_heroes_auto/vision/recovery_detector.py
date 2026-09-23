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
        self.receipt_anchors = load_anchors(templates.parent / "tasks" / "phase6" / "overlays")
        promo_anchors = load_anchors(templates.parent / "tasks" / "phase6" / "promo")
        promo_cta_anchors = load_anchors(templates.parent / "tasks" / "phase6" / "promo-recovery")
        self.promo_title = self._full_frame_anchor(
            next(anchor for anchor in promo_anchors if anchor.id == "promo-stranger-title"),
            ScreenState.EVENT_PROMO,
        )
        self.promo_cta = self._full_frame_anchor(
            next(anchor for anchor in promo_cta_anchors if anchor.id == "promo-stranger-cta"),
            ScreenState.EVENT_PROMO,
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
        groups = {}
        for anchor in self.receipt_anchors:
            groups.setdefault(anchor.variant, []).append(unique_current_anchor(screen, anchor))
        qualified_receipts = [tuple(items) for items in groups.values()
                              if len(items) >= 2 and all(e.matched for e in items)]
        if len(qualified_receipts) > 1:
            return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                           evidence=tuple(e for items in qualified_receipts for e in items))
        if qualified_receipts:
            receipt = qualified_receipts[0]
            if detected.state != ScreenState.UNKNOWN or detected.evidence or (promo_title.matched and promo_cta.matched):
                return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                               evidence=(*detected.evidence, *receipt))
            return replace(detected, state=ScreenState.REWARD_RECEIPT,
                           confidence=min(e.score for e in receipt), evidence=receipt)
        if detected.state in {ScreenState.GAME_LOADING, ScreenState.POPUP_GENERIC} and any(
            item.anchor_id.startswith(self._unique_anchor_prefixes)
            for item in detected.evidence
        ):
            anchors = {anchor.id: anchor for anchor in self.anchors}
            evidence = tuple(
                unique_current_anchor(screen, anchors[item.anchor_id])
                for item in detected.evidence
            )
            if not evidence or any(not item.matched for item in evidence):
                detected = replace(
                    detected,
                    state=ScreenState.UNKNOWN,
                    confidence=0,
                    evidence=evidence or detected.evidence,
                )
            else:
                detected = replace(
                    detected,
                    confidence=min(item.score for item in evidence),
                    evidence=evidence,
                )

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
                ScreenState.EVENT_PROMO,
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
        return detected
