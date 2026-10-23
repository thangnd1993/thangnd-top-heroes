"""Evidence-qualified recovery states that may appear during app startup."""

from dataclasses import replace

import cv2

from top_heroes_auto.automation.timing import measured
from top_heroes_auto.vision.detail_anchor import unique_detail_anchor
from top_heroes_auto.vision.detector import ScreenDetector, load_anchors
from top_heroes_auto.vision.event_gallery_recovery import gallery_evidence
from top_heroes_auto.vision.event_promo import event_promo_evidence
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.hanging_reward import hanging_evidence, qualified_hanging
from top_heroes_auto.vision.idle_detector import IdleRewardDetector
from top_heroes_auto.vision.idle_panel_recovery import adventure_back_evidence, idle_panel_evidence
from top_heroes_auto.vision.loading_progress import loading_progress_evidence
from top_heroes_auto.vision.local_ocr import read_words
from top_heroes_auto.vision.login_notice import assistance_close
from top_heroes_auto.vision.models import AnchorEvidence, NormalizedRect, ScreenDetection, ScreenState
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.subpixel import unique_subpixel_anchor
from top_heroes_auto.vision.system_dialog import system_dialog
from top_heroes_auto.vision.war_recovery import qualified_war, war_evidence
from top_heroes_auto.vision.world_recovery import qualified_world, world_evidence


class RecoveryScreenDetector:
    """Detect known loading/popup variants and require unique live-frame anchors."""

    _unique_anchor_prefixes = ("stranger-loading-", "login-assistance-")

    @staticmethod
    def _paired(screen, anchors, *, always=()):
        """Reject an absent required title before scanning its detail controls.

        All competing title groups still run. Shared close controls remain
        independent, and all phase alternatives run when their title qualifies.
        """
        titles=[a for a in anchors if a.id.endswith('-title')]
        found = {}
        for anchor in titles:
            if anchor.id == 'large-receipt-title' and screen.rotated_from_portrait:
                # _receipt_layout already REQUIRES this entire title above
                # the upper fifth. A cheap rejection there cannot discard a
                # valid receipt. Any hit still gets the ORIGINAL full search,
                # preserving duplicate rejection everywhere in the frame.
                probe = unique_current_anchor(screen, replace(anchor,
                    expected_region=NormalizedRect(.80, 0, 1, 1)))
                if not probe.matched:
                    found[anchor.id] = probe
                    continue
            found[anchor.id] = unique_current_anchor(screen, anchor)
        qualified=bool(titles) and all(e.matched for e in found.values())
        for anchor in anchors:
            if anchor.id not in found and (qualified or anchor.id in always):
                found[anchor.id]=unique_current_anchor(screen,anchor)
        return tuple(found[a.id] for a in anchors if a.id in found)

    def __init__(self):
        templates = template_folder()
        self.anchors = load_anchors(templates)
        self.detector = ScreenDetector(self.anchors)
        self.idle_detector = IdleRewardDetector()
        self.receipt_anchors = load_anchors(templates.parent / "tasks" / "phase6" / "overlays")
        self.notice_anchors = load_anchors(templates.parent / 'tasks/phase8/notice-overlays')
        self.territory_notice_anchors = load_anchors(templates.parent / 'tasks/phase8/territory-notice')
        self.rank_notice_anchors = load_anchors(templates.parent / 'tasks/phase8/rank-notice')
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

    @measured('recovery_detection')
    def detect(self, screen):
        detected = self._detect_existing(screen)
        image=(cv2.rotate(screen.original,cv2.ROTATE_90_COUNTERCLOCKWISE)
               if screen.rotated_from_portrait else screen.original)
        dialog=system_dialog(image,reader=read_words)
        if dialog:
            evidence=tuple(AnchorEvidence(dialog['reason'],ScreenState.SYSTEM_BLOCKING,
                                          1,.98,True,device_box=b) for b in dialog['panels'])
            return replace(detected,state=ScreenState.SYSTEM_BLOCKING,confidence=1,evidence=evidence)
        rank = self._paired(screen, self.rank_notice_anchors)
        if len(rank) == 3 and all(e.matched for e in rank):
            boxes = {e.anchor_id: e.device_box for e in rank}
            title, body, dismiss = (boxes['guild-rank-notice-'+key] for key in ('title','body','dismiss'))
            width, height = screen.device_size or screen.original_size
            layout = (title.y+title.height < body.y < dismiss.y and title.y < height*.3
                      and dismiss.y > height*.7 and abs(title.center[0]-dismiss.center[0]) < width*.1)
            if layout and (detected.state == ScreenState.HOME_OVERLAY or
                           detected.state == ScreenState.UNKNOWN and not detected.evidence):
                # An informational rank notice is dismissible, never a reward
                # receipt or independent proof that any claim succeeded.
                return replace(detected, state=ScreenState.EVENT_PROMO,
                               confidence=min(e.score for e in rank), evidence=rank)
            return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                           evidence=(*detected.evidence, *rank))
        evidence = idle_panel_evidence(screen)
        if evidence:
            if detected.state != ScreenState.UNKNOWN or detected.evidence:
                return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                               evidence=(*detected.evidence, *evidence))
            return replace(detected, state=ScreenState.IDLE_REWARD_PANEL,
                           confidence=min(e.score for e in evidence), evidence=evidence)
        evidence = event_promo_evidence(screen)
        if evidence:
            # A foreground promo naturally coexists with a dimmed Home HUD.
            # Both independently authorize the same bounded dismissal. Other
            # screen evidence (loading, receipt, dialog, etc.) still conflicts.
            compatible = {ScreenState.HOME_OVERLAY, ScreenState.EVENT_PROMO}
            if (detected.state not in compatible | {ScreenState.UNKNOWN} or
                    any(e.state not in compatible for e in detected.evidence)):
                return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                               evidence=(*detected.evidence, *evidence))
            return replace(detected, state=ScreenState.EVENT_PROMO,
                           confidence=min(e.score for e in evidence), evidence=evidence)
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
        evidence = world_evidence(screen)
        if qualified_world(screen, evidence):
            if detected.state != ScreenState.UNKNOWN or detected.evidence:
                return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                               evidence=(*detected.evidence, *evidence))
            return replace(detected, state=ScreenState.GAME_WORLD,
                           confidence=min(e.score for e in evidence), evidence=evidence)
        evidence = loading_progress_evidence(screen)
        if evidence:
            if detected.state not in {ScreenState.UNKNOWN, ScreenState.GAME_LOADING}:
                return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                               evidence=(*detected.evidence,*evidence))
            return replace(detected, state=ScreenState.GAME_LOADING,
                           confidence=min(e.score for e in evidence),evidence=evidence)
        evidence = gallery_evidence(screen)
        if evidence:
            if detected.state != ScreenState.UNKNOWN or detected.evidence:
                return replace(detected,state=ScreenState.UNKNOWN,confidence=0,
                               evidence=(*detected.evidence,*evidence))
            return replace(detected,state=ScreenState.EVENT_GALLERY,
                           confidence=min(e.score for e in evidence),evidence=evidence)
        if detected.state == ScreenState.UNKNOWN and not detected.evidence:
            adventure = adventure_back_evidence(screen, self.idle_detector)
            if adventure is not None:
                return adventure
        return detected

    def _detect_existing(self, screen):
        detected = self.detector.detect(screen)
        promo_title = unique_current_anchor(screen, self.promo_title)
        promo_cta = (unique_current_anchor(screen, self.promo_cta) if promo_title.matched else
                     AnchorEvidence(self.promo_cta.id,self.promo_cta.state,0,self.promo_cta.threshold,False))
        event = self._paired(screen,self.event_anchors)
        event_visible = bool(event) and all(e.matched for e in event)
        event_qualified = event_visible
        if event_qualified:
            boxes = {e.anchor_id: e.device_box for e in event}
            title, started, close = (boxes[k] for k in ('blood-night-title', 'blood-night-started', 'blood-night-close'))
            layout = title.y+title.height < started.y < close.y and abs(started.center[0]-close.center[0]) < started.width*.3
            event_qualified = layout
        notice = self._paired(screen,self.notice_anchors,always=('match-notice-close',))
        notice_visible = len(notice) == 3 and all(e.matched for e in notice)
        territory = self._paired(screen,self.territory_notice_anchors)
        close = next((e for e in notice if e.anchor_id == 'match-notice-close'), None)
        territory_title = next(e for e in territory if e.anchor_id == 'territory-notice-title')
        territory_labels = [e for e in territory if e.anchor_id != 'territory-notice-title']
        labels = [e for e in territory_labels if e.matched]
        if (territory_title.matched and close and close.matched
                and (len(labels) > 1 or any(e.score >= e.threshold and not e.matched
                                           for e in territory_labels))):
            return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                           evidence=(*territory, close))
        territory_visible = (territory_title.matched and len(labels) == 1
                             and all(e.matched or e.score < e.threshold for e in territory_labels)
                             and close and close.matched)
        if territory_visible:
            if notice_visible:
                return replace(detected, state=ScreenState.UNKNOWN, confidence=0,
                               evidence=(*detected.evidence, *notice, *territory))
            # Reuse the exact known close and layout guard, never the blue Go CTA.
            notice = (territory_title, labels[0], close)
            notice_visible = True
        variants = {}
        for anchor in self.receipt_anchors:
            variants.setdefault(anchor.variant, []).append(anchor)
        groups={key:list(self._paired(screen,anchors)) for key,anchors in variants.items()
                if key!='continue-alternative'}
        if any(e.anchor_id=='receipt-title' and e.matched for e in groups.get('default',[])):
            groups['continue-alternative']=[unique_current_anchor(screen,a)
                for a in variants.get('continue-alternative',[])]
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
        # The expedition report receipt already has the qualified large title.
        # Only its continuation's blurred background differs. Reuse the same
        # strict glyph-detail matcher; do not add an overlapping receipt group
        # that could rescue duplicate titles or conflict with existing receipts.
        large = groups.get('large-receipt', [])
        title = next((e for e in large if e.anchor_id == 'large-receipt-title'), None)
        continuation = next((e for e in large if e.anchor_id == 'large-receipt-continue'), None)
        if (title and title.matched and continuation and not continuation.matched
                and continuation.score < continuation.threshold):
            anchor = next(a for a in self.receipt_anchors if a.id == 'large-receipt-continue')
            detail = unique_detail_anchor(screen, anchor)
            if detail.matched:
                groups['large-receipt'] = [detail if e is continuation else e for e in large]
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
            title = next(b for k,b in boxes.items() if k.endswith('-title'))
            preparing = next(b for k,b in boxes.items() if k.endswith(('-preparing', '-battle')))
            close = next(b for k,b in boxes.items() if k.endswith('-close'))
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

        loading_title = (unique_current_anchor(screen,self.promo_loading_title)
                         if detected.state==ScreenState.GAME_LOADING else None)
        if loading_title and loading_title.matched:
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
        if (detected.state == ScreenState.POPUP_GENERIC
                and {e.anchor_id for e in detected.evidence} == {
                    'login-assistance-title', 'login-assistance-banner'}
                and close is not None and not event_visible and not notice_visible
                and not (promo_title.matched and promo_cta.matched)):
            assistance = (*detected.evidence, close)
            if assistance_close(screen, assistance) is not None:
                return replace(detected, state=ScreenState.LOGIN_ASSISTANCE,
                               confidence=min(e.score for e in assistance), evidence=assistance)

        return detected

    @staticmethod
    def _receipt_layout(screen, variant, items):
        if variant == 'large-receipt':
            boxes = {e.anchor_id: e.device_box for e in items}
            title = boxes['large-receipt-title']
            continuation = boxes['large-receipt-continue']
            width, height = screen.device_size or screen.original_size
            # Expedition receipts add helper reports below the rewards; the
            # same unique title sits lower, still above the upper fifth.
            return (title.y + title.height < height*.20
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
