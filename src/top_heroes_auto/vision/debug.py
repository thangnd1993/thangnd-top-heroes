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
    encoded, png_data = cv2.imencode(".png", image)
    if not encoded:
        raise OSError(f"Cannot write debug overlay: {path}")
    path.write_bytes(png_data.tobytes())
    return path


def write_device_tap(captured, point, path):
    """Persist the exact device point on this clean capture before input."""
    image = captured.original.copy()
    if captured.rotated_from_portrait:
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    x, y = point
    h, w = image.shape[:2]
    if captured.device_size != (w, h) or not (0 <= x < w and 0 <= y < h):
        raise ValueError('Tap geometry does not match current device screenshot.')
    cv2.drawMarker(image, (x, y), (0, 0, 255), cv2.MARKER_CROSS, 25, 2)
    cv2.putText(image, f'ADB tap ({x}, {y})', (max(0, min(x-80, w-280)), max(25, y-20)),
                cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 255), 2)
    ok, payload = cv2.imencode('.png', image)
    if not ok:
        raise ValueError('Cannot persist pre-action tap geometry.')
    path.write_bytes(payload.tobytes())
    return str(path)
