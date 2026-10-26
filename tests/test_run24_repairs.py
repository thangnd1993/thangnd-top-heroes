"""Run24 repairs: paid-pack close variant (Event traversal), OCR server, recognition speed."""
import sys
from pathlib import Path

import cv2
import pytest
from test_complete_repair import capture

from top_heroes_auto.adb.client import Target
from top_heroes_auto.vision.screenshot import ScreenshotService

FIXTURES = Path(__file__).parent/'fixtures'


def shot(name):
    path = FIXTURES/f'{name}.png'
    return ScreenshotService(lambda _: path.read_bytes()).take(Target(1, 'fixture', 'serial', 'boot'))


# --- Event traversal: run24 #3 "Gói Quân Trang Phe" paid pack was UNKNOWN, so the last Event was never visited.
@pytest.mark.parametrize('account', ['2', '3'])
def test_run24_paid_pack_variants_get_only_their_qualified_close(account):
    from top_heroes_auto.vision.event_paid_modal import paid_modal_navigation

    result = paid_modal_navigation(cv2.imread(str(FIXTURES/f'run22/run24-paid-pack-{account}.png')))
    assert result is not None and result['permission'] == 'NAVIGATION_ONLY'
    assert not result['claim_authorized'] and result['coverage_known'] is False
    close, paid = result['close'], result['paid_region']
    assert close.x > 600 and close.y < 200          # red X, never the price button
    assert paid.y > 900 and not (paid.x <= close.x <= paid.x+paid.width)


@pytest.mark.parametrize('name', ['run22/run23-gallery-before', 'run22/event-unqualified-child',
                                  'run22/shop-monthly-unowned', 'run22/run23-technology-3of20'])
def test_new_raster_variants_do_not_qualify_unrelated_pages(name):
    from top_heroes_auto.vision.event_paid_modal import paid_modal_navigation

    image = cv2.imread(str(FIXTURES/f'{name}.png'))
    assert paid_modal_navigation(image) is None


# --- Recognition speed without semantic change.
def test_adventure_prefilter_keeps_the_real_positive():
    from top_heroes_auto.vision.idle_detector import IdleRewardDetector
    from top_heroes_auto.vision.idle_panel_recovery import adventure_back_evidence

    evidence = adventure_back_evidence(shot('phase8/idle-adventure-return'), IdleRewardDetector())
    assert evidence is not None and any(e.anchor_id == 'back' for e in evidence.evidence)


def test_adventure_prefilter_skips_full_idle_detector_on_feature_pages():
    from top_heroes_auto.vision.idle_detector import IdleRewardDetector
    from top_heroes_auto.vision.idle_panel_recovery import adventure_back_evidence

    detector = IdleRewardDetector()
    calls = []
    original = detector.detect
    detector.detect = lambda screen: calls.append(1) or original(screen)
    for name in ('run22/shop-monthly-unowned', 'run22/run23-technology-3of20', 'run22/run23-gallery-before'):
        assert adventure_back_evidence(shot(name), detector) is None
    assert calls == []


def test_parallel_fixed_reward_search_is_identical_to_serial(monkeypatch):
    import top_heroes_auto.vision.fixed_rewards as module

    detector = module.FixedRewardDetector()
    frames = [capture(n) for n in ('run22/shop-monthly-unowned', 'phase7_resume/shop-monthly-owned',
                                   'phase6_finalization/monthly-daily-received')]

    def signature(observation):
        return (observation.page, list(observation.anchors),
                {k: (v.matched, round(v.score, 6), v.device_box) for k, v in observation.anchors.items()})

    parallel = [signature(detector.observe(f)) for f in frames]

    class Serial:
        @staticmethod
        def map(fn, items):
            return list(map(fn, items))

    monkeypatch.setattr(module, 'anchor_pool', lambda: Serial())
    assert [signature(detector.observe(f)) for f in frames] == parallel


# --- OCR: a persistent reader replaces a PowerShell start-up per call (run24: 0.61 s each, 131-195 calls).
def test_ocr_falls_back_to_one_shot_reader_when_server_fails(monkeypatch):
    from top_heroes_auto.vision import local_ocr

    def broken(_image):
        raise TimeoutError('server stalled')

    monkeypatch.setattr(local_ocr, '_server_words', broken)
    monkeypatch.setattr(local_ocr, '_read_words_once', lambda image: [dict(text='3/20')])
    assert local_ocr._read_words(cv2.imread(str(FIXTURES/'run22/run23-technology-3of20.png'))) == [dict(text='3/20')]


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows OCR')
def test_ocr_server_returns_exactly_the_one_shot_words():
    from top_heroes_auto.vision import local_ocr

    image = cv2.imread(str(FIXTURES/'run22/run23-technology-3of20.png'))
    crops = [cv2.resize(image[960:1010, 380:630], None, fx=2, fy=2),
             cv2.resize(image[0:120, 0:720], None, fx=2, fy=2)]
    for crop in crops:
        assert local_ocr._server_words(crop) == local_ocr._read_words_once(crop)
