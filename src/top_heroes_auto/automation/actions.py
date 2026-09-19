from __future__ import annotations

import logging
from collections.abc import Callable

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.models import ScreenDetection, ScreenState

log = logging.getLogger("top_heroes_auto")


class SafeInputService:
    """Dispatch inputs only when current detector evidence identifies the target."""

    def __init__(self, index: int, name: str, dispatch: Callable[[str, tuple[int, ...]], object]):
        self.index = index
        self.name = name
        self.dispatch = dispatch

    def tap_detected_target(self, detection: ScreenDetection, anchor_id: str):
        if detection.state == ScreenState.UNKNOWN:
            raise SafetyError("DO NOT TAP: trạng thái màn hình không xác định.")
        matches = [
            item
            for item in detection.evidence
            if item.anchor_id == anchor_id and item.matched and item.device_box is not None
        ]
        if len(matches) != 1:
            raise SafetyError("DO NOT TAP: thiếu đúng một visual anchor đã xác minh.")
        x, y = matches[0].device_box.center
        log.info(
            "[%s / #%s] Action: tap; state=%s; anchor=%s; coordinate=%s,%s",
            self.name,
            self.index,
            detection.state.value,
            anchor_id,
            x,
            y,
        )
        return self.dispatch("tap", (x, y))

    def key_back(self, detection: ScreenDetection):
        if detection.state == ScreenState.UNKNOWN:
            raise SafetyError("DO NOT PRESS BACK: trạng thái màn hình không xác định.")
        log.info(
            "[%s / #%s] Action: Android Back; state=%s",
            self.name,
            self.index,
            detection.state.value,
        )
        return self.dispatch("keyevent", (4,))
