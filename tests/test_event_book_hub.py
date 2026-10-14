from pathlib import Path

import cv2
import numpy as np

from top_heroes_auto.vision.event_book_objectives import book_context, book_rows
from top_heroes_auto.vision.event_collaboration_hub import collaboration_hub, collaboration_training

FIXTURES=Path(__file__).parent/'fixtures/phase8'


def test_training_map_qualifies_only_current_exit_not_rewards():
    image = cv2.imread(str(FIXTURES/'collaboration-training.png'))
    result = collaboration_training(image)
    assert result['permission'] == 'KNOWN_BLOCKER_EXIT'
    assert not result['tabs'] and not result['selected']
    assert result['back'].center == (64, 1233)
    assert 'rewards' not in result and 'children' not in result
    image[20:68, 190:531] = 0
    assert collaboration_training(image) is None


def test_training_exit_rejects_other_page_and_duplicate_back():
    assert collaboration_training(cv2.imread(str(FIXTURES/'collaboration-hub.png'))) is None
    image = cv2.imread(str(FIXTURES/'collaboration-training.png'))
    image[900:955, 36:93] = image[1206:1261, 36:93]
    assert collaboration_training(image) is None


def test_hub_is_navigation_only_with_four_indicated_edges():
    image=cv2.imread(str(FIXTURES/'collaboration-hub.png'))
    result=collaboration_hub(image)
    assert result['permission']=='NAVIGATION_HUB'
    assert len(result['children'])==4
    assert all('caption' in name for name,_ in result['children'])
    assert not any('claim' in key or 'reward'==key for key in result)
    assert result['back'].center==(70,1212)


def test_hub_missing_exit_or_duplicate_exit_fails_closed():
    image=cv2.imread(str(FIXTURES/'collaboration-hub.png'))
    missing=image.copy()
    missing[1174:1251,32:109]=0
    assert collaboration_hub(missing) is None
    duplicate=image.copy()
    duplicate[800:877,32:109]=image[1174:1251,32:109]
    assert collaboration_hub(duplicate) is None


def test_unrelated_page_is_not_hub():
    assert collaboration_hub(cv2.imread(str(FIXTURES/'season-objectives.png'))) is None


def test_book_completed_one_has_one_current_free_target():
    image=cv2.imread(str(FIXTURES/'season-objectives.png'))
    rows=book_rows(image,reader=lambda im: [])
    assert len(rows)==1
    assert rows[0]['box'].center==(567,854)
    assert rows[0]['state']=='AVAILABLE'
    assert 'completed-objective-fraction' in rows[0]['evidence']
    shifted=cv2.warpAffine(image,np.float32([[1,0,15],[0,1,0]]),(720,1280))
    moved=book_rows(shifted,reader=lambda im: [])
    assert len(moved)==1
    assert moved[0]['box'].center==(582,854)
    assert moved[0]['identity']==rows[0]['identity']


def test_book_unproven_fraction_or_foreign_cost_cannot_claim():
    image=cv2.imread(str(FIXTURES/'season-objectives.png'))
    missing=image.copy()
    missing[825:869,398:448]=image[820,400]
    assert not book_rows(missing,reader=lambda im: [])
    paid=image.copy()
    paid[843:863,515:535]=(255,80,0)
    assert not book_rows(paid,reader=lambda im: [])
    gray=image.copy()
    gray[824:884,488:647]=100
    assert not book_rows(gray,reader=lambda im: [])


def test_book_requires_paired_context_and_rejects_other_ui():
    image=cv2.imread(str(FIXTURES/'season-objectives.png'))
    image[502:536,92:527]=0
    assert book_context(image) is None
    assert not book_rows(image,reader=lambda im: [])
    assert book_context(cv2.imread(str(FIXTURES/'collaboration-hub.png'))) is None
