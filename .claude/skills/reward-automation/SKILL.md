---
name: reward-automation
description: Rules and checklist for changing or reviewing Top Heroes reward-claiming automation (badges, free/claim/receive controls, Treasure Hunt missions, Guild donation, tab traversal, verification). Use before touching flows under src/top_heroes_auto/automation or app/*_port.py.
---

# Reward automation rules

- Architecture: frozen per-instance plan -> flow registry -> one visit per feature -> verify -> cleanup once (`app/automation_fleet.py`, `automation/execution_plan.py`).
  Target = LDPlayer Multi index + stable non-name identity + explicit indexed ADB serial + boot id. Re-check Protection before each consequential action.
- Discover menus with red dots / numbered badges AND explicit free controls (NHẬN / MIỄN PHÍ / RECEIVE / CLAIM and Vietnamese equivalents), even without a badge.
  A red pixel alone is never permission; the owning icon/page must be qualified. `UNKNOWN` screen = no input.
- In one feature visit traverse every eligible tab/submenu once; do not close and reopen the feature per reward.
- Treasure Hunt / Event missions: **collect finished missions first** (`Nhận`), then dispatch new ones with the qualified quick-send (`Gửi Nhanh`); never conflate
  them (`automation/expedition.py`). Guild Technology/donation: WOOD only - qualified quick contribution first, or one ordinary then quick; never stones/diamonds.
  Never enter Sảnh Thí Luyện without explicit authorization.
- A click is not a claim. Required: fresh screenshot, independent postcondition (button gone / `Đã nhận` / counter change), then journal VERIFIED.
  Unverified = POSSIBLE and stays locked forever; never retry it. Monthly aggregate NONE must not hide independent child rewards.
- A failing reward isolates itself only with fresh safe evidence; feature errors recover boundedly; target failures isolate that worker; Stop stops new input.
- Tests: add a fixture-based regression for every recognition/flow change; use the `rig` fakes, never a live emulator in tests.
