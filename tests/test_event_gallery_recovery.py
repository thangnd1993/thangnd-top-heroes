from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_recovery import Clock, Port

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.recovery_cli import DiagnosticRecoveryPort
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.recovery import HomeRecoveryEngine, RecoveryStatus
from top_heroes_auto.vision.event_gallery_recovery import gallery_back_point
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


def frame():
    return ScreenshotService(lambda _: Path("tests/fixtures/phase8/menu-mixed-width.png").read_bytes()).take(
        Target(43, "offline", "explicit", "boot")
    )


@pytest.fixture
def found(monkeypatch):
    monkeypatch.setattr(
        "top_heroes_auto.vision.event_gallery_recovery.read_words",
        lambda _: [{"text": "Event gallery 20 Ngay 20 Ngay"}],
    )
    return RecoveryScreenDetector().detect(frame())


def test_paired_gallery_context_and_current_back(found):
    assert found.state == ScreenState.EVENT_GALLERY
    assert found.confidence >= 0.96 and len(found.evidence) == 3
    assert gallery_back_point(frame(), found) == found.evidence[0].device_box.center


def test_conflicting_or_incomplete_gallery_evidence_cannot_tap(found):
    for changed in (
        replace(found, state=ScreenState.UNKNOWN),
        replace(found, evidence=found.evidence[:2]),
        replace(found, confidence=0.9),
    ):
        with pytest.raises(SafetyError):
            gallery_back_point(frame(), changed)


class GalleryPort(Port):
    backs = 0

    def back_from_event_gallery(self, observation):
        self.backs += 1
        return (60, 1230)


def engine():
    c = Clock()
    return HomeRecoveryEngine(clock=c, sleep=c.sleep)


def test_gallery_back_waits_for_fresh_home_and_is_bounded():
    p = GalleryPort(ScreenState.EVENT_GALLERY, ScreenState.GAME_HOME)
    assert engine().ensure_game_home(p).status == RecoveryStatus.SUCCESS and p.backs == 1
    p = GalleryPort(ScreenState.EVENT_GALLERY)
    assert engine().ensure_game_home(p).status == RecoveryStatus.LIMIT_REACHED and p.backs == 2
    p = GalleryPort(ScreenState.EVENT_GALLERY, ScreenState.UNKNOWN, ScreenState.EVENT_GALLERY)
    assert engine().ensure_game_home(p).status == RecoveryStatus.LIMIT_REACHED and p.backs == 1


def test_production_back_consumes_observation_once(found, tmp_path):
    p = object.__new__(DiagnosticRecoveryPort)
    p.index = 43
    p.snapshot = object()
    p._overlay_frame = (object(), frame(), found)
    sent = []
    p.manager = SimpleNamespace(execute=lambda *a, **k: sent.append((a, k)))
    p.save_tap_geometry = lambda *a: None
    observation = SimpleNamespace(detection=found)
    assert p.back_from_event_gallery(observation) == found.evidence[0].device_box.center
    with pytest.raises(SafetyError):
        p.back_from_event_gallery(observation)
    assert len(sent) == 1 and sent[0][0] == (43, "tap")


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows OCR")
def test_saved_gallery_real_ocr_navigation_only():
    found = RecoveryScreenDetector().detect(frame())
    assert found.state == ScreenState.EVENT_GALLERY
    assert gallery_back_point(frame(), found) == found.evidence[0].device_box.center
