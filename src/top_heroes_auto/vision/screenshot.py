from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import cv2

from top_heroes_auto.adb.client import Target
from top_heroes_auto.vision.image_normalizer import ImageNormalizer
from top_heroes_auto.vision.models import CapturedScreen


class ScreenshotService:
    """Capture once from a verified Target, validate, normalize, and optionally persist."""

    def __init__(self, capture: Callable[[str], bytes], normalizer: ImageNormalizer | None = None):
        self.capture = capture
        self.normalizer = normalizer or ImageNormalizer()

    def take(self, target: Target, folder: Path | None = None, tag: str = "capture") -> CapturedScreen:
        image = self.normalizer.decode(self.capture(target.serial))
        normalized, scale = self.normalizer.normalize(image)
        height, width = image.shape[:2]
        safe_tag = "".join(char if char.isalnum() or char in "-_" else "-" for char in tag).strip("-")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
        source = None
        if folder is not None:
            folder.mkdir(parents=True, exist_ok=True)
            source = folder / f"{stamp}-{safe_tag or 'capture'}.png"
            encoded, png_data = cv2.imencode(".png", image)
            if not encoded:
                raise OSError(f"Cannot persist screenshot: {source}")
            source.write_bytes(png_data.tobytes())
            metadata = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "instance": {"index": target.index, "name": target.name},
                "adb_target": target.serial,
                "boot_id": target.boot_id,
                "original_resolution": [width, height],
                "normalized_resolution": list(self.normalizer.reference_size),
                "scale_to_original": list(scale),
                "source_image": str(source),
            }
            source.with_suffix(".json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return CapturedScreen(
            target.index,
            target.name,
            target.serial,
            target.boot_id,
            image,
            normalized,
            (width, height),
            self.normalizer.reference_size,
            scale,
            source,
        )
