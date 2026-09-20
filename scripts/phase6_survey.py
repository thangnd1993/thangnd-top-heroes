"""One observed navigation action with fresh target matching, then a new capture.

Development evidence collection only; this is not production task acceptance.
Boxes are supplied from an inspected portrait screenshot of this same account.
No claim automation or retry is provided. All transport work uses Manager.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from top_heroes_auto.adb.client import Target  # noqa: E402
from top_heroes_auto.app.diagnostic import _manager  # noqa: E402
from top_heroes_auto.app.main import data_directory  # noqa: E402
from top_heroes_auto.app.vision_cli import _capture  # noqa: E402
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError  # noqa: E402


def portrait(image):
    return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE) if image.shape[1] > image.shape[0] else image


def locate(current, reference, box):
    x, y, w, h = box
    template = reference[y:y+h, x:x+w]
    if template.shape[:2] != (h, w) or min(w, h) < 10 or float(template.std()) < 2:
        raise SafetyError("Invalid observed anchor crop.")
    scores = cv2.matchTemplate(current, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, (cx, cy) = cv2.minMaxLoc(scores)
    if not np.isfinite(score) or score < 0.97:
        raise SafetyError(f"Observed anchor no longer verified: {score:.4f}")
    scores[max(0, cy-h//2):cy+h//2+1, max(0, cx-w//2):cx+w//2+1] = -1
    if float(scores.max()) >= 0.97:
        raise SafetyError("Observed anchor is ambiguous in current screenshot.")
    return cx+w//2, cy+h//2


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--source", type=Path)
    p.add_argument("--context", nargs=4, type=int)
    p.add_argument("--tap", nargs=4, type=int)
    p.add_argument("--swipe", nargs=5, type=int)
    args = p.parse_args()
    if (args.index, args.name) != (2, "5-Emmmmm"):
        raise SafetyError("This survey is authorized only for 2 / 5-Emmmmm.")
    if args.tap and args.swipe:
        raise SafetyError("Only one navigation action per capture.")
    d = data_directory()
    m = _manager(d)
    identity = m.query(args.index)
    if identity.name != args.name or not m.store.metadata(m.namespace, 0).protected:
        raise SafetyError("Exact target and Queen protection must remain verified.")
    snap = RunSnapshot(m.namespace, ((args.index, args.name),), True)
    s = _capture(m, d, args.index, args.name, args.tag + "-before")
    if args.tap or args.swipe:
        if not args.source or not args.context:
            raise SafetyError("Inspected same-account source and known context required.")
        metadata = json.loads(args.source.with_suffix(".json").read_text(encoding="utf-8"))
        if (metadata["instance"] != {"index": s.index, "name": s.name}
                or metadata["adb_target"] != s.serial or metadata["boot_id"] != s.boot_id):
            raise SafetyError("Reference screenshot belongs to another account or boot.")
        reference = portrait(cv2.imdecode(np.frombuffer(args.source.read_bytes(), np.uint8), 1))
        current = portrait(s.original)
        locate(current, reference, args.context)
        observed = Target(s.index, s.name, s.serial, s.boot_id)
        if args.tap:
            point = locate(current, reference, args.tap)
            m.execute(args.index, "tap", values=point, snapshot=snap, observed_target=observed)
        else:
            x1, y1, x2, y2, duration = args.swipe
            h, w = current.shape[:2]
            if not (0 <= x1 < w and 0 <= x2 < w and 0 <= y1 < h and 0 <= y2 < h
                    and 200 <= duration <= 1000):
                raise SafetyError("Swipe outside observed viewport.")
            m.execute(args.index, "swipe", values=tuple(args.swipe), snapshot=snap, observed_target=observed)
        s = _capture(m, d, args.index, args.name, args.tag + "-after")
    print(json.dumps({"image": str(s.source_image), "adb": s.serial, "boot_id": s.boot_id}))


if __name__ == "__main__":
    main()
