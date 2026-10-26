"""Local Windows counter reader. OCR alone never authorizes an input."""
import json
import re
import subprocess
import sys
import tempfile
import threading
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import cv2

from top_heroes_auto.automation.timing import measure
from top_heroes_auto.vision.resources import template_folder

_cache = threading.local()


def read_words(image):
    if sys.platform != 'win32' or image.size == 0:
        return []
    # Exact bytes only: never reuse an old frame, approximate glyph or result
    # from another worker. Cache contains OCR text, never availability/permission.
    key = (image.shape, image.dtype.str, sha256(image.tobytes()).digest())
    if not hasattr(_cache, 'words'):
        _cache.words = OrderedDict()
    if key in _cache.words:
        _cache.words.move_to_end(key)
        with measure('ocr_cache_hit'):
            return deepcopy(_cache.words[key])
    with measure('ocr'):
        words = _read_words(image)
    _cache.words[key] = deepcopy(words)
    if len(_cache.words) > 256:
        _cache.words.popitem(last=False)
    return words


class _OcrServer:
    """One persistent ocr-server.ps1 per worker thread (run24: 0.61 s/call was PowerShell+WinRT start-up).

    Same engine/script logic as the one-shot reader. Any protocol error, timeout or
    engine error closes the server and the caller falls back to the one-shot script.
    """
    TIMEOUT = 35.0

    def __init__(self):
        import queue

        script = template_folder().parent / 'tools/ocr-server.ps1'
        self.process = subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8', bufsize=1)
        self.replies = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.temp = tempfile.TemporaryDirectory(prefix='top-heroes-ocr-')

    def _pump(self):
        for line in self.process.stdout:
            self.replies.put(line)
        self.replies.put(None)

    def read(self, image):
        import queue

        # WinRT may keep the previous StorageFile open; never overwrite it.
        self.count = getattr(self, 'count', 0) + 1
        path = Path(self.temp.name) / f'counter-{self.count}.png'
        path.write_bytes(cv2.imencode('.png', image)[1].tobytes())
        previous = Path(self.temp.name) / f'counter-{self.count-1}.png'
        try:
            previous.unlink(missing_ok=True)
        except OSError:
            pass  # Still held by WinRT; removed with the temporary directory.
        self.process.stdin.write(str(path)+'\n')
        self.process.stdin.flush()
        try:
            line = self.replies.get(timeout=self.TIMEOUT)
        except queue.Empty as exc:
            raise TimeoutError('OCR server timeout') from exc
        if line is None:
            raise OSError('OCR server ended')
        data = json.loads(line.lstrip('﻿'))
        if data.get('engine') != 'Windows.Media.Ocr':
            raise ValueError(data.get('error') or 'Unrecognized local OCR engine.')
        return data['words']

    def close(self):
        try:
            self.process.kill()
        except OSError:
            pass
        self.temp.cleanup()

    __del__ = close  # A finished worker thread's server ends with its thread-local state.


def _server_words(image):
    server = getattr(_cache, 'server', None)
    if server is None:
        server = _cache.server = _OcrServer()
    try:
        return server.read(image)
    except Exception:
        _cache.server = None
        server.close()
        raise


def _read_words(image):
    try:
        return _server_words(image)
    except Exception:  # noqa: BLE001 - fall back to the original one-shot reader
        return _read_words_once(image)


def _read_words_once(image):
    script = template_folder().parent / 'tools/read-image-text.ps1'
    with tempfile.TemporaryDirectory(prefix='top-heroes-ocr-') as temp:
        path = Path(temp) / 'counter.png'
        path.write_bytes(cv2.imencode('.png', image)[1].tobytes())
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
             '-File', str(script), '-ImagePath', str(path)],
            capture_output=True, timeout=35, creationflags=subprocess.CREATE_NO_WINDOW,
            check=True, encoding='utf-8-sig',
        )
        data = json.loads(result.stdout)
        if data.get('engine') != 'Windows.Media.Ocr':
            raise ValueError('Unrecognized local OCR engine.')
        return data['words']


def counter(image, *, denominator=None, maximum=9999, reader=read_words):
    """Two renderings must agree on exactly one number; no O-to-0 repairs/guesses."""
    if image is None or not image.size:
        return None
    # Padding preserves the source background and keeps edge digits visible to OCR.
    image = cv2.copyMakeBorder(image, 15, 15, 15, 15, cv2.BORDER_CONSTANT,
                               value=tuple(int(v) for v in image[0,0]))
    values = []
    for scale in (2, 3):
        enlarged = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        text = ' '.join(w['text'] for w in reader(enlarged))
        if denominator is None:
            tokens = re.findall(r'(?<![\w/])\d+(?![\w/])', text)
            found = [int(v) for v in tokens]
        else:
            pairs = re.findall(r'(?<![\w/])(\d+)\s*/\s*(\d+)(?![\w/])', text)
            found = [int(a) for a, b in pairs if int(b) == denominator]
        if len(found) != 1 or not 0 <= found[0] <= maximum:
            return None
        values.append(found[0])
    return values[0] if values[0] == values[1] else None


def fraction_line_counter(image, *, denominator, maximum, reader=read_words):
    """Read 'N/D' from a whole counter line when the lone number crop is unreadable.

    Run23: Windows OCR returns nothing for a single-digit crop ('3') but reads the
    full line as '3120' / '18120' / '10120' - the slash consistently rendered as '1'.
    Accept exactly one 'N/D' or 'N1D' token per rendering, two renderings agreeing.
    """
    if image is None or not image.size:
        return None
    image = cv2.copyMakeBorder(image, 15, 15, 15, 15, cv2.BORDER_CONSTANT,
                               value=tuple(int(v) for v in image[0,0]))
    pattern = re.compile(rf'^(\d+)(?:/|1){denominator}$')
    values = []
    for scale in (2, 3):
        enlarged = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        found = [int(m.group(1)) for w in reader(enlarged)
                 if (m := pattern.match(w['text'].replace(' ', '')))]
        if len(found) != 1 or not 0 <= found[0] <= maximum:
            return None
        values.append(found[0])
    return values[0] if values[0] == values[1] else None
