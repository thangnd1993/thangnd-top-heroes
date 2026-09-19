from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.vision.matcher import match_anchor
from top_heroes_auto.vision.models import (
    NormalizedRect,
    ScreenDetection,
    ScreenState,
    VisualAnchor,
)


def load_anchors(folder: Path) -> tuple[VisualAnchor, ...]:
    anchors = []
    for metadata in sorted(folder.rglob("*.json")) if folder.is_dir() else ():
        item = json.loads(metadata.read_text(encoding="utf-8"))
        template = metadata.parent / item["template"]
        anchors.append(
            VisualAnchor(
                item["id"],
                ScreenState(item["state"]),
                template,
                NormalizedRect(*item["expected_region"]),
                float(item["threshold"]),
                bool(item.get("required", True)),
                float(item.get("weight", 1.0)),
            )
        )
    ids = [anchor.id for anchor in anchors]
    if len(ids) != len(set(ids)):
        raise ValueError("Vision anchor IDs must be unique.")
    return tuple(anchors)


class ScreenDetector:
    def __init__(self, anchors: tuple[VisualAnchor, ...], conflict_margin: float = 0.03):
        self.anchors = anchors
        self.conflict_margin = conflict_margin

    @classmethod
    def from_folder(cls, folder: Path):
        return cls(load_anchors(folder))

    def detect(self, screen) -> ScreenDetection:
        started = time.perf_counter()
        grouped = defaultdict(list)
        weights = {anchor.id: anchor.weight for anchor in self.anchors}
        required = {anchor.id for anchor in self.anchors if anchor.required}
        for anchor in self.anchors:
            grouped[anchor.state].append(match_anchor(screen, anchor))
        candidates = []
        for state, evidence in grouped.items():
            if any(item.anchor_id in required and not item.matched for item in evidence):
                continue
            total = sum(weights[item.anchor_id] for item in evidence)
            confidence = sum(item.score * weights[item.anchor_id] for item in evidence) / total
            candidates.append((confidence, state, tuple(evidence)))
        candidates.sort(key=lambda item: item[0], reverse=True)
        state, confidence, evidence = ScreenState.UNKNOWN, 0.0, ()
        if candidates:
            confidence, state, evidence = candidates[0]
            if len(candidates) > 1 and candidates[1][0] >= confidence - self.conflict_margin:
                state = ScreenState.UNKNOWN
                evidence = candidates[0][2] + candidates[1][2]
        duration = (time.perf_counter() - started) * 1000
        return ScreenDetection(
            state,
            float(confidence),
            tuple(evidence),
            datetime.now(timezone.utc).isoformat(),
            screen.source_image,
            duration,
        )
