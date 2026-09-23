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
        self.anchors = tuple(
            replace(anchor, template=folder / 'idle-adventure-portal-core.png',
                    expected_region=NormalizedRect(0, 0, 1, 1))
            if anchor.id == 'idle-adventure-portal' else anchor
            for anchor in load_anchors(folder)
        )
        self.detector = ScreenDetector(self.anchors)
        self.home_detector = ScreenDetector.from_folder(template_folder())

    def detect(self, screen):
        detected = self.detector.detect(screen)
        if detected.state != ScreenState.GAME_HOME:
            return detected
        home = self.home_detector.detect(screen)
        portal = unique_current_anchor(screen, next(a for a in self.anchors if a.id == 'idle-adventure-portal'))
        if home.state != ScreenState.GAME_HOME or not portal.matched:
            return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                           evidence=(portal, *home.evidence))
        return replace(detected, confidence=min(portal.score, home.confidence), evidence=(portal, *home.evidence))
