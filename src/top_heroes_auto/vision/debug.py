from pathlib import Path

import cv2


def write_overlay(screen, detection, path: Path) -> Path:
    image = screen.normalized.copy()
    for item in detection.evidence:
        if item.normalized_box:
            box = item.normalized_box
            color = (30, 210, 30) if item.matched else (20, 20, 230)
            cv2.rectangle(image, (box.x, box.y), (box.x + box.width, box.y + box.height), color, 2)
            cv2.putText(
                image,
                f"{item.anchor_id} {item.score:.3f}",
                (box.x, max(18, box.y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                cv2.LINE_AA,
            )
    cv2.putText(image, f"{detection.state.value} {detection.confidence:.3f}", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 220, 30), 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise OSError(f"Cannot write debug overlay: {path}")
    return path
