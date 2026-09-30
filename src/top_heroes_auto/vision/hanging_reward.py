"""Qualified navigation out of the known bounty board; no reward action."""
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.resources import template_folder


def hanging_evidence(screen):
    anchors = load_anchors(template_folder().parent / "tasks/phase7/hanging-recovery")
    return tuple(unique_current_anchor(screen, a) for a in anchors)


def qualified_hanging(screen, evidence):
    roles = {e.anchor_id: e for e in evidence}
    if set(roles) != {"hanging-title", "hanging-tasks", "hanging-back"} or len(evidence) != 3:
        return False
    if any(not e.matched or e.score < max(.98, e.threshold) or e.device_box is None for e in evidence):
        return False
    title, tasks, back = (roles[k].device_box for k in ("hanging-title", "hanging-tasks", "hanging-back"))
    width, height = screen.device_size or screen.original_size
    return (title.y + title.height < tasks.y < height * .25
            and back.y > height * .85
            and all(b.center[0] < width * .35 for b in (title, tasks, back))
            and abs(title.x - tasks.x) < title.width * .25
            and abs(back.center[0] - title.x) < title.width)


def hanging_back_point(screen, detection):
    if (detection.state != ScreenState.TREO_THUONG or detection.confidence < .98
            or not qualified_hanging(screen, detection.evidence)):
        raise SafetyError("Back requires current qualified Treo Thuong title, task label and Back control.")
    return next(e.device_box.center for e in detection.evidence if e.anchor_id == "hanging-back")
