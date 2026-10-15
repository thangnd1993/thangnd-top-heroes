"""Close-only recovery from the qualified Idle modal; never proves a reward."""
from dataclasses import replace

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import NormalizedRect, ScreenState, VisualAnchor
from top_heroes_auto.vision.resources import idle_reward_template_folder, template_folder


def idle_panel_evidence(screen):
    anchors = [replace(a, state=ScreenState.IDLE_REWARD_PANEL, threshold=.98)
               for a in load_anchors(idle_reward_template_folder())
               if a.id in {'idle-title-claimable', 'idle-claim-button'}]
    anchors.append(VisualAnchor('idle-panel-close', ScreenState.IDLE_REWARD_PANEL,
        template_folder().parent/'tasks/phase8/idle-panel/close.png',
        NormalizedRect(0, 0, 1, 1), .98))
    evidence = tuple(unique_current_anchor(screen, a) for a in anchors)
    if not qualified_idle_panel(screen, evidence):
        return ()
    return evidence


def qualified_idle_panel(screen, evidence):
    roles = {e.anchor_id: e for e in evidence}
    if len(evidence) != 3 or set(roles) != {'idle-title-claimable', 'idle-claim-button', 'idle-panel-close'}:
        return False
    if any(not e.matched or e.score < .98 or e.device_box is None for e in evidence):
        return False
    title, claim, close = (roles[k].device_box for k in
                          ('idle-title-claimable', 'idle-claim-button', 'idle-panel-close'))
    w, h = screen.device_size or screen.original_size
    return (title.y < h*.25 and title.y+title.height < claim.y
            and claim.y+claim.height < close.y and close.y > h*.85
            and all(abs(b.center[0]-w*.5) < w*.12 for b in (title, claim, close)))


def idle_panel_close_point(screen, detection):
    if detection.state != ScreenState.IDLE_REWARD_PANEL or not qualified_idle_panel(screen, detection.evidence):
        raise SafetyError('Idle closure requires the current title, claim control and unique close.')
    return next(e.device_box.center for e in detection.evidence if e.anchor_id == 'idle-panel-close')


def adventure_back_evidence(screen, detector):
    """Reuse the existing qualified Idle entry, adding its current Back arrow."""
    detected = detector.detect(screen)
    if detected.state not in {ScreenState.IDLE_ENTRY_AVAILABLE, ScreenState.IDLE_ENTRY_NOT_AVAILABLE}:
        return None
    if not detected.evidence or any(not e.matched or e.score < .95 for e in detected.evidence):
        return None
    anchor = next(a for a in load_anchors(template_folder().parent/'tasks/phase6/fixed-rewards')
                  if a.id == 'back')
    back = unique_current_anchor(screen, replace(anchor, expected_region=NormalizedRect(0,0,.10,1),
                                                 state=detected.state))
    w, h = screen.device_size or screen.original_size
    if (not back.matched or back.device_box is None or back.device_box.center[0] > w*.2
            or back.device_box.y < h*.9):
        return None
    return replace(detected, evidence=(*detected.evidence,back),
                   confidence=min(detected.confidence,back.score))


def adventure_back_point(screen, detection):
    if (detection.state not in {ScreenState.IDLE_ENTRY_AVAILABLE,ScreenState.IDLE_ENTRY_NOT_AVAILABLE}
            or not any(e.anchor_id.startswith('idle-entry-') and e.matched and e.score >= .95
                       for e in detection.evidence)):
        raise SafetyError('Current qualified Idle adventure entry required.')
    backs = [e for e in detection.evidence if e.anchor_id == 'back' and e.matched
             and e.device_box is not None and e.score >= .96]
    if len(backs) != 1:
        raise SafetyError('Current unique adventure Back required.')
    return backs[0].device_box.center
