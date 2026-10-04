"""Strict empty War board recognition permits only its current Back control."""
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.resources import template_folder


def war_evidence(screen):
    return tuple(unique_current_anchor(screen, anchor) for anchor in
                 load_anchors(template_folder().parent / 'tasks/phase8/war-recovery'))


def qualified_war(screen, evidence):
    roles = {e.anchor_id: e for e in evidence}
    if len(evidence) != 4 or set(roles) != {'war-title', 'war-tabs', 'war-empty', 'war-back'}:
        return False
    if any(not e.matched or e.score < max(.98, e.threshold) or e.device_box is None for e in evidence):
        return False
    title, tabs, empty, back = (roles[k].device_box for k in ('war-title', 'war-tabs', 'war-empty', 'war-back'))
    width, height = screen.device_size or screen.original_size
    return (title.y+title.height < tabs.y < height*.2
            and height*.35 < empty.center[1] < height*.65
            and back.y > height*.9 and back.center[0] < width*.2
            and all(abs(b.center[0]-width*.5) < width*.08 for b in (title, tabs, empty)))


def war_back_point(screen, detection):
    if (detection.state != ScreenState.WAR_EMPTY or detection.confidence < .98
            or not qualified_war(screen, detection.evidence)):
        raise SafetyError('Back requires current unique War title, tabs, empty-list message and Back.')
    return next(e.device_box.center for e in detection.evidence if e.anchor_id == 'war-back')
