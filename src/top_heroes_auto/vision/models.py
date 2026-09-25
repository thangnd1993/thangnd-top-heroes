from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

import numpy as np


class ScreenState(StrEnum):
    UNKNOWN = "UNKNOWN"
    ANDROID_HOME = "ANDROID_HOME"
    GAME_LOADING = "GAME_LOADING"
    PROMO_LOADING = "PROMO_LOADING"
    PROMO_BLOCKING = "PROMO_BLOCKING"
    PROMO_AD = "PROMO_AD"
    EVENT_PROMO = "EVENT_PROMO"
    REWARD_RECEIPT = "REWARD_RECEIPT"
    GAME_HOME = "GAME_HOME"
    HOME_OVERLAY = "HOME_OVERLAY"
    POPUP_GENERIC = "POPUP_GENERIC"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    UPDATE_NOTICE = "UPDATE_NOTICE"
    FREE_REWARD_PAGE = "FREE_REWARD_PAGE"
    IDLE_ENTRY_AVAILABLE = "IDLE_ENTRY_AVAILABLE"
    IDLE_ENTRY_NOT_AVAILABLE = "IDLE_ENTRY_NOT_AVAILABLE"
    IDLE_REWARD_CLAIMABLE = "IDLE_REWARD_CLAIMABLE"
    IDLE_REWARD_NOT_CLAIMABLE = "IDLE_REWARD_NOT_CLAIMABLE"
    IDLE_REWARD_CLAIMED = "IDLE_REWARD_CLAIMED"


@dataclass(frozen=True)
class NormalizedRect:
    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self):
        if not (0 <= self.left < self.right <= 1 and 0 <= self.top < self.bottom <= 1):
            raise ValueError("Normalized rectangle must be inside 0..1.")

    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (
            round(self.left * width),
            round(self.top * height),
            round(self.right * width),
            round(self.bottom * height),
        )


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    def normalized(self, width: int, height: int) -> NormalizedRect:
        return NormalizedRect(self.x / width, self.y / height, (self.x + self.width) / width, (self.y + self.height) / height)

    def scale(self, scale_x: float, scale_y: float) -> BoundingBox:
        return BoundingBox(
            round(self.x * scale_x),
            round(self.y * scale_y),
            round(self.width * scale_x),
            round(self.height * scale_y),
        )


@dataclass(frozen=True)
class CapturedScreen:
    index: int
    name: str
    serial: str
    boot_id: str
    original: np.ndarray = field(repr=False, compare=False)
    normalized: np.ndarray = field(repr=False, compare=False)
    original_size: tuple[int, int]
    normalized_size: tuple[int, int]
    scale_to_original: tuple[float, float]
    source_image: Path | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    device_size: tuple[int, int] | None = None
    rotated_from_portrait: bool = False

    def to_device_box(self, normalized_box: BoundingBox) -> BoundingBox:
        box = normalized_box.scale(*self.scale_to_original)
        if not self.rotated_from_portrait:
            return box
        if self.device_size is None:
            raise ValueError("Portrait capture is missing device dimensions.")
        _, device_height = self.device_size
        return BoundingBox(
            box.y,
            device_height - box.x - box.width,
            box.height,
            box.width,
        )


@dataclass(frozen=True)
class VisualAnchor:
    id: str
    state: ScreenState
    template: Path
    expected_region: NormalizedRect
    threshold: float
    required: bool = True
    weight: float = 1.0
    variant: str = "default"


@dataclass(frozen=True)
class AnchorEvidence:
    anchor_id: str
    state: ScreenState
    score: float
    threshold: float
    matched: bool
    normalized_box: BoundingBox | None = None
    device_box: BoundingBox | None = None

    def as_dict(self) -> dict:
        return {
            "anchor": self.anchor_id,
            "state": self.state.value,
            "score": round(self.score, 6),
            "threshold": self.threshold,
            "matched": self.matched,
            "normalized_box": vars(self.normalized_box) if self.normalized_box else None,
            "device_box": vars(self.device_box) if self.device_box else None,
        }


@dataclass(frozen=True)
class ScreenDetection:
    state: ScreenState
    confidence: float
    evidence: tuple[AnchorEvidence, ...]
    timestamp: str
    source_image: Path | None
    duration_ms: float

    def as_dict(self) -> dict:
        return {
            "state": self.state.value,
            "confidence": round(self.confidence, 6),
            "evidence": [item.as_dict() for item in self.evidence],
            "timestamp": self.timestamp,
            "source_image": str(self.source_image) if self.source_image else None,
            "duration_ms": round(self.duration_ms, 3),
        }
