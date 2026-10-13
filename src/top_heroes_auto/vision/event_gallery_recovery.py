"""Recognized Event gallery permits only its current visual Back control."""

from dataclasses import replace

import cv2

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.dynamic_events import event_body_contract, event_shell, menu_card_boxes
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.local_ocr import read_words
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, ScreenState
from top_heroes_auto.vision.resources import template_folder


def gallery_evidence(screen):
    image = (
        cv2.rotate(screen.original, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if screen.rotated_from_portrait
        else screen.original
    )
    if len(menu_card_boxes(image)) < 3:
        return ()
    folder = template_folder().parent / "tasks/phase6/fixed-rewards"
    anchor = next(a for a in load_anchors(folder) if a.id == "back")
    back = unique_current_anchor(screen, replace(anchor, state=ScreenState.EVENT_GALLERY))
    if not back.matched or back.device_box is None:
        return ()
    shell = event_shell(image, back.device_box, reader=read_words)
    template = cv2.imread(str(template_folder().parent / "tasks/phase8/personal-task-tab.png"))
    if not shell or event_body_contract(image, (), template, reader=read_words) != "MENU_GRID":
        return ()
    h, w = image.shape[:2]
    return (
        replace(back, anchor_id="event-gallery-back"),
        AnchorEvidence(
            "event-gallery-title:" + shell["title"],
            ScreenState.EVENT_GALLERY,
            1,
            0.98,
            True,
            device_box=BoundingBox(0, 0, w, round(h * 0.07)),
        ),
        AnchorEvidence(
            "event-gallery-closed-cards-and-timers",
            ScreenState.EVENT_GALLERY,
            1,
            0.98,
            True,
            device_box=BoundingBox(0, round(h * 0.08), w, round(h * 0.82)),
        ),
    )


def gallery_back_point(screen, detection):
    evidence = detection.evidence
    if (
        detection.state != ScreenState.EVENT_GALLERY
        or detection.confidence < .96
        or len(evidence) != 3
        or any(not e.matched or e.score < e.threshold or e.state != ScreenState.EVENT_GALLERY for e in evidence)
        or evidence[0].anchor_id != "event-gallery-back"
        or evidence[0].device_box is None
        or not evidence[1].anchor_id.startswith("event-gallery-title:")
        or evidence[2].anchor_id != "event-gallery-closed-cards-and-timers"
    ):
        raise SafetyError("No qualified current Event gallery Back.")
    w, h = screen.device_size or screen.original_size
    point = evidence[0].device_box.center
    if not (0 < point[0] < w * 0.18 and h * 0.90 < point[1] < h):
        raise SafetyError("Event gallery Back outside current footer.")
    return point
