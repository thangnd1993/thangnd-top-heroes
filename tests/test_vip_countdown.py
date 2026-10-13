from pathlib import Path

import cv2
import pytest

from top_heroes_auto.vision.vip_countdown import countdown_box

FIXTURE=Path(__file__).parent/'fixtures/phase6_vip/daily-disabled-countdown.png'


def test_actual_changed_countdown_reads_without_old_digits():
    box=countdown_box(cv2.imread(str(FIXTURE)))
    assert box.center==(601,880)


@pytest.mark.parametrize('readings', [('08:56:12','08:56:13'),('garbage','garbage'),('25:00:00','25:00:00'),('00:00:00','00:00:00')])
def test_invalid_or_conflicting_clock_fails_closed(readings):
    values=iter(readings)
    assert countdown_box(cv2.imread(str(FIXTURE)),reader=lambda im:[dict(text=next(values))]) is None


def test_colored_claim_button_is_not_disabled():
    image=cv2.imread(str(FIXTURE))
    image[853:908,527:675]=(30,180,120)
    assert countdown_box(image,reader=lambda im:[dict(text='08:56:12')]) is None
