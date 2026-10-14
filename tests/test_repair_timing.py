import threading

import numpy as np
import pytest

from top_heroes_auto.automation import timing
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision import local_ocr


def test_early_postcondition_has_no_deliberate_sleep(monkeypatch):
    waits=[]
    monkeypatch.setattr(timing,'wait',lambda *a,**k:waits.append(a))
    observations=[]
    def observe():
        observations.append('fresh')
        return 'EXPECTED'
    assert timing.poll(observe,lambda r:r=='EXPECTED')=='EXPECTED'
    assert observations==['fresh'] and waits==[]


def test_poll_captures_afresh_and_stops_before_delayed_work(monkeypatch):
    calls=[]
    stopped=False
    def wait(*a,**kw):
        nonlocal stopped
        stopped=True
    monkeypatch.setattr(timing,'wait',wait)
    with pytest.raises(SafetyError,match='cancelled'):
        timing.poll(lambda:calls.append('fresh'),lambda _:False,cancelled=lambda:stopped)
    assert calls==['fresh']


def test_ocr_cache_requires_exact_pixels_and_does_not_share_mutable_state(monkeypatch):
    monkeypatch.setattr(local_ocr.sys,'platform','win32')
    local_ocr._cache.words={}
    from collections import OrderedDict
    local_ocr._cache.words=OrderedDict()
    calls=[]
    monkeypatch.setattr(local_ocr,'_read_words',lambda im:calls.append(im.copy()) or [{'text':'one'}])
    image=np.zeros((20,20,3),np.uint8)
    first=local_ocr.read_words(image)
    first[0]['text']='corrupted'
    assert local_ocr.read_words(image.copy())==[{'text':'one'}]
    image[0,0]=1
    local_ocr.read_words(image)
    assert len(calls)==2


def test_worker_measurements_and_ocr_are_separate(monkeypatch):
    monkeypatch.setattr(local_ocr.sys,'platform','win32')
    calls=[]
    monkeypatch.setattr(local_ocr,'_read_words',lambda im:calls.append(threading.get_ident()) or [])
    barrier=threading.Barrier(2)
    reports=[]
    def worker():
        timing.reset()
        barrier.wait(timeout=3)
        for _ in range(2):
            local_ocr.read_words(np.zeros((11,11,3),np.uint8))
        reports.append(timing.snapshot())
    threads=[threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert len(set(calls))==2 and len(calls)==2
    assert all(r['ocr']['calls']==r['ocr_cache_hit']['calls']==1 for r in reports)
