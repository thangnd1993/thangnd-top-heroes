"""Evidence-qualified recovery states that may appear during app startup."""

from dataclasses import replace

import cv2

from top_heroes_auto.vision.detail_anchor import unique_detail_anchor
from top_heroes_auto.vision.detector import ScreenDetector, load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.hanging_reward import hanging_evidence, qualified_hanging
from top_heroes_auto.vision.loading_progress import loading_progress_evidence
from top_heroes_auto.vision.models import NormalizedRect, ScreenDetection, ScreenState
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.subpixel import unique_subpixel_anchor
from top_heroes_auto.vision.war_recovery import qualified_war, war_evidence


class RecoveryScreenDetector:
    """Detect known loading/popup variants and require unique live-frame anchors."""

    _unique_anchor_prefixes = ("stranger-loading-", "login-assistance-")

    def __init__(self):
        templates = template_folder()
        self.anchors = load_anchors(templates)
        self.detector = ScreenDetector(self.anchors)
        self.receipt_anchors = load_anchors(templates.parent / "tasks" / "phase6" / "overlays")
        self.notice_anchors = load_anchors(templates.parent / 'tasks/phase8/notice-overlays')
        self.event_anchors = load_anchors(templates.parent / 'tasks/phase6/event-overlays')
        self.home_overlay_anchors = load_anchors(templates.parent / 'tasks/phase6/home-overlays')
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
        detected = self._detect_existing(screen)
        evidence = hanging_evidence(screen)
        if qualified_hanging(screen, evidence):
            if detected.state != ScreenState.UNKNOWN or detected.evidence:
                return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                               evidence=(*detected.evidence, *evidence))
            return replace(detected, state=ScreenState.TREO_THUONG,
                           confidence=min(e.score for e in evidence), evidence=evidence)
        evidence = war_evidence(screen)
        if qualified_war(screen, evidence):
            if detected.state != ScreenState.UNKNOWN or detected.evidence:
                return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                               evidence=(*detected.evidence, *evidence))
            return replace(detected, state=ScreenState.WAR_EMPTY,
                           confidence=min(e.score for e in evidence), evidence=evidence)
        evidence = loading_progress_evidence(screen)
        if evidence:
            if detected.state not in {ScreenState.UNKNOWN, ScreenState.GAME_LOADING}:
                return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                               evidence=(*detected.evidence,*evidence))
            return replace(detected, state=ScreenState.GAME_LOADING,
                           confidence=min(e.score for e in evidence),evidence=evidence)
        return detected

    def _detect_existing(self, screen):
        detected = self.detector.detect(screen)
        promo_title = unique_current_anchor(screen, self.promo_title)
        promo_cta = unique_current_anchor(screen, self.promo_cta)
        event = tuple(unique_current_anchor(screen, a) for a in self.event_anchors)
        event_visible = bool(event) and all(e.matched for e in event)
        event_qualified = event_visible
        if event_qualified:
            boxes = {e.anchor_id: e.device_box for e in event}
            title, started, close = (boxes[k] for k in ('blood-night-title', 'blood-night-started', 'blood-night-close'))
            layout = title.y+title.height < started.y < close.y and abs(started.center[0]-close.center[0]) < started.width*.3
            event_qualified = layout
        notice = tuple(unique_current_anchor(screen, a) for a in self.notice_anchors)
        notice_visible = len(notice) == 3 and all(e.matched for e in notice)
        groups = {}
        for anchor in self.receipt_anchors:
            groups.setdefault(anchor.variant, []).append(unique_current_anchor(screen, anchor))
        alternatives = groups.pop('continue-alternative', [])
        if alternatives:
            default = groups.get('default', [])
            continuation = next((e for e in default if e.anchor_id == 'receipt-continue'), None)
            alternative = alternatives[0]
            title = next((e for e in default if e.anchor_id == 'receipt-title'), None)
            # The same dim text can land between device pixels. Align only this
            # known paired receipt, retaining >=.98 and cross-offset uniqueness.
            # A raw duplicate (score >= threshold but unmatched) is never rescued.
            if (title and title.matched and .85 <= alternative.score < alternative.threshold):
                anchor = next(a for a in self.receipt_anchors if a.id == alternative.anchor_id)
                alternative = unique_subpixel_anchor(screen, anchor)
            # Legitimate opacity variant; never rescue duplicate/conflicting text.
            if continuation and not continuation.matched and continuation.score < continuation.threshold and alternative.matched:
                groups['default'] = [alternative if e is continuation else e for e in default]
            elif continuation and continuation.matched and alternative.matched and (
                abs(continuation.device_box.center[0]-alternative.device_box.center[0]) > continuation.device_box.width*.5
                or abs(continuation.device_box.center[1]-alternative.device_box.center[1]) > continuation.device_box.height
            ):
                groups['default'] = []
            elif alternative.score >= alternative.threshold and not alternative.matched:
                groups['default'] = []
        # The continuation text is rendered over different blurred pages.
        # Keep the same glyphs, remove only low-frequency background, and require
        # the independent title. Never rescue any raw duplicate/conflict.
        default = groups.get('default', [])
        title = next((e for e in default if e.anchor_id == 'receipt-title'), None)
        continuation = next((e for e in default if e.anchor_id.startswith('receipt-continue')), None)
        if (title and title.matched and continuation and not continuation.matched
                and all(e.matched or e.score < e.threshold for e in (*default,*alternatives))):
            anchor = next(a for a in self.receipt_anchors if a.id == 'receipt-continue')
            detail = unique_detail_anchor(screen, anchor)
            if detail.matched:
                groups['default'] = [detail if e is continuation else e for e in default]
        qualified_receipts = [tuple(items) for variant, items in groups.items()
                              if len(items) >= 2 and all(e.matched for e in items)
                              and self._receipt_layout(screen, variant, items)]
        if len(qualified_receipts) > 1:
            return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                           evidence=tuple(e for items in qualified_receipts for e in items))
        if qualified_receipts:
            receipt = qualified_receipts[0]
            if detected.state != ScreenState.UNKNOWN or detected.evidence or event_visible or notice_visible or (promo_title.matched and promo_cta.matched):
                return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                               evidence=(*detected.evidence, *receipt))
            return replace(detected, state=ScreenState.REWARD_RECEIPT,
                           confidence=min(e.score for e in receipt), evidence=receipt)
        if notice_visible:
            boxes = {e.anchor_id: e.device_box for e in notice}
            title, preparing, close = (boxes[k] for k in
                ('match-notice-title', 'match-notice-preparing', 'match-notice-close'))
            width, height = screen.device_size or screen.original_size
            layout = (title.y+title.height < preparing.y < close.y and title.y < height*.15
                      and close.y > height*.85 and all(abs(b.center[0]-width*.5) < width*.12
                      for b in (title, preparing, close)))
            if (layout and detected.state == ScreenState.UNKNOWN and not detected.evidence
                    and not event_visible and not (promo_title.matched and promo_cta.matched)):
                return replace(detected, state=ScreenState.EVENT_PROMO,
                               confidence=min(e.score for e in notice), evidence=notice)
            return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                           evidence=(*detected.evidence, *notice))
        if event_visible:
            if event_qualified and detected.state == ScreenState.UNKNOWN and not detected.evidence and not (promo_title.matched and promo_cta.matched):
                return replace(detected, state=ScreenState.EVENT_PROMO, confidence=min(e.score for e in event), evidence=event)
            return replace(detected, state=ScreenState.UNKNOWN, confidence=0, evidence=(*detected.evidence, *event))
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
        # Artwork-independent Home overlay: opposite Home HUD corners remain
        # dimmed/blurred while an ordinary foreground panel is sharp. This does
        # not reinterpret loading, login dialogs or an arbitrary gameplay page.
        if detected.state in {ScreenState.UNKNOWN, ScreenState.GAME_HOME, ScreenState.POPUP_GENERIC} and not (
                detected.state == ScreenState.UNKNOWN and detected.evidence):
            covered = tuple(unique_current_anchor(screen, a) for a in self.home_overlay_anchors)
            if len(covered) == 2 and all(e.matched for e in covered):
                gray = cv2.cvtColor(screen.normalized, cv2.COLOR_BGR2GRAY)
                height, width = gray.shape
                foreground = gray[round(height*.12):round(height*.88), round(width*.2):round(width*.8)]
                corners = [gray[e.normalized_box.y:e.normalized_box.y+e.normalized_box.height,
                                e.normalized_box.x:e.normalized_box.x+e.normalized_box.width] for e in covered]
                sharpness = float(cv2.Laplacian(foreground, cv2.CV_64F).var())
                background = max(float(cv2.Laplacian(c, cv2.CV_64F).var()) for c in corners)
                if sharpness > max(15, background*3):
                    return replace(detected, state=ScreenState.HOME_OVERLAY,
                                   confidence=min(e.score for e in covered), evidence=covered)
        return detected

    @staticmethod
    def _receipt_layout(screen, variant, items):
        if variant == 'large-receipt':
            boxes = {e.anchor_id: e.device_box for e in items}
            title = boxes['large-receipt-title']
            continuation = boxes['large-receipt-continue']
            width, height = screen.device_size or screen.original_size
            return (title.y + title.height < height*.12
                    and continuation.y > height*.85
                    and continuation.y-title.y > height*.70
                    and all(abs(b.center[0]-width*.5) < width*.10
                            for b in (title, continuation)))
        if variant != 'ranking-receipt':
            return True
        boxes = {e.anchor_id: e.device_box for e in items}
        title = boxes['ranking-receipt-title']
        gem = boxes['ranking-receipt-gem']
        continuation = boxes['ranking-receipt-continue']
        if not all((title, gem, continuation)):
            return False
        width, height = screen.device_size or screen.original_size
        return (title.y+title.height < gem.y < continuation.y
                and continuation.y-gem.y > height*.2
                and all(abs(b.center[0]-width*.5) < width*.15 for b in (title, gem, continuation)))
