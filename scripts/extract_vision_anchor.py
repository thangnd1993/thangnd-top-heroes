"""Crop a real diagnostic screenshot into a compact versioned visual anchor."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--id", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--crop", required=True, help="x,y,width,height")
    parser.add_argument("--region", required=True, help="normalized left,top,right,bottom")
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--optional", action="store_true")
    parser.add_argument("--variant", default="default")
    parser.add_argument("--notes", default="Cropped from a verified real Android screenshot.")
    args = parser.parse_args()
    image = cv2.imdecode(np.frombuffer(args.image.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Source screenshot cannot be decoded.")
    x, y, width, height = (int(value) for value in args.crop.split(","))
    crop = image[y : y + height, x : x + width]
    if crop.size == 0 or crop.shape[:2] != (height, width):
        raise ValueError("Crop is outside source screenshot.")
    args.output.mkdir(parents=True, exist_ok=True)
    png_path = args.output / f"{args.id}.png"
    encoded, payload = cv2.imencode(".png", crop)
    if not encoded:
        raise ValueError("Anchor cannot be encoded.")
    png_path.write_bytes(payload.tobytes())
    metadata = {
        "id": args.id,
        "state": args.state,
        "template": png_path.name,
        "expected_region": [float(value) for value in args.region.split(",")],
        "threshold": args.threshold,
        "required": not args.optional,
        "weight": 1.0,
        "variant": args.variant,
        "reference_resolution": [1280, 720],
        "notes": args.notes,
    }
    png_path.with_suffix(".json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
