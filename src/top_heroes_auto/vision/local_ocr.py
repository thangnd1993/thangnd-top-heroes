"""Local Windows counter reader. OCR alone never authorizes an input."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2

from top_heroes_auto.vision.resources import template_folder


def read_words(image):
    if sys.platform != 'win32' or image.size == 0:
        return []
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
