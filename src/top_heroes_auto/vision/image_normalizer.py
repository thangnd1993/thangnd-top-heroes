from __future__ import annotations

import cv2
import numpy as np

from top_heroes_auto.automation.guard import SafetyError


class ScreenshotInvalid(SafetyError):
    code = "SCREENSHOT_INVALID"

    def __init__(self, detail: str, *, blank_frame: bool = False):
        super().__init__(f"{self.code}: {detail}")
        self.blank_frame = blank_frame


class ImageNormalizer:
    def __init__(self, reference_size: tuple[int, int] = (1280, 720), blank_stddev: float = 2.0):
        self.reference_size = reference_size
        self.blank_stddev = blank_stddev

    def decode_with_orientation(self, png: bytes) -> tuple[np.ndarray, tuple[int, int], bool]:
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ScreenshotInvalid("ADB payload is not PNG.")
        image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            raise ScreenshotInvalid("PNG cannot be decoded.")
        height, width = image.shape[:2]
        if width <= 0 or height <= 0:
            raise ScreenshotInvalid("Image dimensions are empty.")
        device_size = (width, height)
        rotated_from_portrait = height > width
        if rotated_from_portrait:
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
            height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if float(gray.mean()) < 1.0 or float(gray.std()) < self.blank_stddev:
            raise ScreenshotInvalid("Image is blank or effectively uniform.", blank_frame=True)
        if width < height:
            raise ScreenshotInvalid("Landscape orientation is required.")
        return image, device_size, rotated_from_portrait

    def decode(self, png: bytes) -> np.ndarray:
        image, _, _ = self.decode_with_orientation(png)
        return image

    def normalize(self, image: np.ndarray) -> tuple[np.ndarray, tuple[float, float]]:
        height, width = image.shape[:2]
        target_width, target_height = self.reference_size
        normalized = cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)
        return normalized, (width / target_width, height / target_height)
