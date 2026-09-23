"""Idle Home entry requires an independent Home state and one movable portal.

The portal core is a crop of the original clean Phase 5 template, excluding
the account-dependent progress ring, level label and background. Crop geometry
is asset provenance, never a runtime tap coordinate.
"""
from dataclasses import replace

from top_heroes_auto.vision.detector import ScreenDetector, load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import NormalizedRect, ScreenState
from top_heroes_auto.vision.resources import idle_reward_template_folder, template_folder


class IdleRewardDetector:
    def __init__(self):
        folder = idle_reward_template_folder()
        entry_ids = {
            'idle-entry-available',
            'idle-entry-available-open',
            'idle-entry-not-available',
        }
        self.anchors = tuple(
            replace(
                anchor,
                template=folder / f'{anchor.id}-core.png',
                expected_region=NormalizedRect(0, 0, 1, 1),
                threshold=0.95,
            )
            if anchor.id in entry_ids else
            replace(
                anchor,
                template=folder / 'idle-adventure-portal-core.png',
                expected_region=NormalizedRect(0, 0, 1, 1),
            )
            if anchor.id == 'idle-adventure-portal' else anchor
            for anchor in load_anchors(folder)
        )
        self.overlay_anchor = next(
            anchor for anchor in self.anchors if anchor.id == 'idle-adventure-auto-overlay'
        )
        self.detector = ScreenDetector(
            tuple(anchor for anchor in self.anchors if anchor.id != self.overlay_anchor.id)
        )
        self.home_detector = ScreenDetector.from_folder(template_folder())

    def detect(self, screen):
        overlay = unique_current_anchor(screen, self.overlay_anchor)
        if overlay.score >= self.overlay_anchor.threshold - self.detector.conflict_margin:
            if not overlay.matched:
                detected = self.detector.detect(screen)
                return replace(
                    detected,
                    state=ScreenState.UNKNOWN,
                    confidence=0,
                    evidence=(*detected.evidence, overlay),
                )
            detected = self.detector.detect(screen)
            return replace(
                detected,
                state=ScreenState.POPUP_GENERIC,
                confidence=overlay.score,
                evidence=(overlay,),
            )
        detected = self.detector.detect(screen)
        if detected.state != ScreenState.GAME_HOME:
            if detected.state in {
                ScreenState.IDLE_ENTRY_AVAILABLE,
                ScreenState.IDLE_ENTRY_NOT_AVAILABLE,
            }:
                unique_evidence = tuple(
                    unique_current_anchor(
                        screen,
                        next(anchor for anchor in self.anchors if anchor.id == item.anchor_id),
                    )
                    for item in detected.evidence
                )
                if not unique_evidence or any(not item.matched for item in unique_evidence):
                    return replace(
                        detected,
                        state=ScreenState.UNKNOWN,
                        confidence=0,
                        evidence=unique_evidence or detected.evidence,
                    )
                return replace(
                    detected,
                    confidence=min(item.score for item in unique_evidence),
                    evidence=unique_evidence,
                )
            return detected
        home = self.home_detector.detect(screen)
        portal = unique_current_anchor(screen, next(a for a in self.anchors if a.id == 'idle-adventure-portal'))
        if home.state != ScreenState.GAME_HOME or not portal.matched:
            return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                           evidence=(portal, *home.evidence))
        return replace(detected, confidence=min(portal.score, home.confidence), evidence=(portal, *home.evidence))
