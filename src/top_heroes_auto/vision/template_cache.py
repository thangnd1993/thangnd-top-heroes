"""Bounded decoded static assets. Screenshots and visual decisions are never cached."""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np


@lru_cache(maxsize=256)
def _decode(path, modified, size):
    image = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'Template cannot be decoded: {path}')
    image.setflags(write=False)
    return image


def read_template(path):
    path = Path(path).resolve()
    stat = path.stat()  # Removed/replaced local assets never silently reuse old bytes.
    return _decode(str(path), stat.st_mtime_ns, stat.st_size)
