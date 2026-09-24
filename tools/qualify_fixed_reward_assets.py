"""Extract only clean UI pixels; local qualification helper, never a runtime route."""
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "diagnostics/phase6-clean-20260923"
DEST = ROOT / "assets/tasks/phase6/fixed-rewards"


def extract(name, source, box, *, width=720, saved_normalized=False):
    image = cv2.imdecode(np.frombuffer(source.read_bytes(), np.uint8), 1)
    if saved_normalized:
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    x, y, w, h = box
    if width != 720:
        sx, sy = 720/image.shape[1], 1280/image.shape[0]
        image = cv2.resize(image, (720, 1280), interpolation=cv2.INTER_AREA)
        x, y, w, h = round(x*sx), round(y*sy), round(w*sx), round(h*sy)
    crop = image[y:y+h, x:x+w]
    crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / f"{name}.png").write_bytes(cv2.imencode(".png", crop)[1].tobytes())
    (DEST / f"{name}.json").write_text(json.dumps(dict(
        id=name, state="FREE_REWARD_PAGE", template=f"{name}.png",
        expected_region=[0, 0, 1, 1], threshold=.96, required=False,
        notes=f"Clean UI crop from {source.name}; no annotations or account text."
    ), indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    for name, source, box in (
        ("profile-title", "12-profile.png", (176, 24, 368, 40)),
        ("profile-bxh", "12-profile.png", (460, 1200, 57, 72)),
        ("back", "12-profile.png", (35, 1215, 52, 47)),
        ("ranking-title", "14-bxh.png", (324, 115, 72, 34)),
        ("ranking-tab", "14-bxh.png", (111, 223, 80, 26)),
        ("ranking-chest", "14-bxh.png", (110, 119, 57, 42)),
        ("ranking-attention", "14-bxh.png", (164, 104, 15, 15)),
        ("ranking-close", "14-bxh.png", (332, 1177, 53, 42)),
        ("shop-title", "06-shop-entry.png", (313, 25, 96, 47)),
        ("daily-title", "06-shop-entry.png", (35, 136, 301, 47)),
        ("shop-gift", "06-shop-entry.png", (606, 231, 52, 41)),
        ("shop-attention", "06-shop-entry.png", (657, 214, 16, 23)),
        ("daily-tab", "06-shop-entry.png", (174, 1220, 53, 30)),
        ("weekly-tab", "06-shop-entry.png", (660, 1219, 33, 34)),
    ):
        extract(name, SOURCE / source, box)
    # This text-only rectangle contains no blue/red annotation pixels.
    extract("weekly-title", Path(r"C:\Users\ADMIN\Desktop\TIỆM1.png"),
            (25, 112, 260, 34), width=565)
    extract("shop-title-reference", Path(r"C:\Users\ADMIN\Desktop\TIỆM1.png"),
            (244, 23, 75, 37), width=565)
    soup = Path(r"C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\tasks\bxh-shop-fixed\20260924-162405-406610Z\8")
    extract('weekly-title', soup/'20260924-162626-792592Z-bxh-shop.png', (34, 136, 343, 48), saved_normalized=True)
    extract('daily-received', soup/'20260924-162553-874492Z-bxh-shop.png', (592, 212, 94, 80), saved_normalized=True)
    extract('weekly-received', soup/'20260924-162626-792592Z-bxh-shop.png', (614, 314, 96, 85), saved_normalized=True)
    ranking = Path(r"C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\tasks\bxh-shop-fixed\20260924-164739-729787Z\11\20260924-164912-070155Z-bxh-shop.png")
    extract('ranking-empty-slot', ranking, (85, 100, 115, 80), saved_normalized=True)
    # Preserve only the invariant border; erase every avatar/level/badge pixel.
    raw = cv2.imread(str(SOURCE/'02-home.png'))[66:150, 19:106].copy()
    mask = np.zeros(raw.shape[:2], np.uint8)
    mask[3:8, 8:70] = 255
    mask[12:60, 2:7] = 255
    mask[12:60, 79:84] = 255
    raw[mask == 0] = 0
    for name, array in [('avatar-frame', raw), ('avatar-mask', mask)]:
        image = cv2.rotate(array, cv2.ROTATE_90_CLOCKWISE)
        (DEST/f'{name}.png').write_bytes(cv2.imencode('.png', image)[1].tobytes())
    fleet = soup.parent.parent/'20260924-171957-687304Z'
    floral = cv2.imread(str(fleet/'3/20260924-172339-007819Z-bxh-shop.png'))
    floral = cv2.rotate(floral, cv2.ROTATE_90_COUNTERCLOCKWISE)[64:155, 17:110].copy()
    mask = np.zeros(floral.shape[:2], np.uint8)
    mask[5:12, 20:65] = 255
    mask[4:17, 4:16] = 255
    mask[24:53, 2:9] = 255
    mask[24:53, 80:88] = 255
    floral[mask == 0] = 0
    for name, array in [('avatar-floral-frame', floral), ('avatar-floral-mask', mask)]:
        image = cv2.rotate(array, cv2.ROTATE_90_CLOCKWISE)
        (DEST/f'{name}.png').write_bytes(cv2.imencode('.png', image)[1].tobytes())
    receipt = cv2.imread(str(fleet/'4/20260924-172551-007060Z-bxh-shop.png'))
    receipt = cv2.rotate(receipt, cv2.ROTATE_90_COUNTERCLOCKWISE)
    overlays = DEST.parent/'overlays'
    for name, (x, y, w, h) in {
        'ranking-receipt-title': (207, 279, 224, 45),
        'ranking-receipt-gem': (326, 414, 63, 58),
        'ranking-receipt-continue': (259, 916, 204, 32),
    }.items():
        crop = cv2.rotate(receipt[y:y+h, x:x+w], cv2.ROTATE_90_CLOCKWISE)
        (overlays/f'{name}.png').write_bytes(cv2.imencode('.png', crop)[1].tobytes())
        (overlays/f'{name}.json').write_text(json.dumps(dict(
            id=name, state='REWARD_RECEIPT', template=f'{name}.png',
            expected_region=[0, 0, 1, 1], threshold=.98, required=True,
            variant='ranking-receipt', notes='Paired rank reward receipt. Excludes rank/amount/account pixels; dismissal only.'
        ), indent=2)+'\n', encoding='utf-8', newline='\n')
    shop = fleet.parent/'20260924-180234-771324Z/5/20260924-180839-162046Z-bxh-shop.png'
    receipt = cv2.rotate(cv2.imread(str(shop)), cv2.ROTATE_90_COUNTERCLOCKWISE)
    name = 'receipt-continue-dim'
    crop = cv2.rotate(receipt[996:1028, 258:465], cv2.ROTATE_90_CLOCKWISE)
    (overlays/f'{name}.png').write_bytes(cv2.imencode('.png', crop)[1].tobytes())
    (overlays/f'{name}.json').write_text(json.dumps(dict(
        id=name, state='REWARD_RECEIPT', template=f'{name}.png', expected_region=[0, 0, 1, 1],
        threshold=.98, required=True, variant='continue-alternative',
        notes='Clean dim continue-text phase. Requires the existing independent congratulations title.'
    ), indent=2)+'\n', encoding='utf-8', newline='\n')
