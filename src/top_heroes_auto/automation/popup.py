from __future__ import annotations

from dataclasses import dataclass

from top_heroes_auto.vision.models import ScreenState


@dataclass(frozen=True)
class PopupHandler:
    popup_type: ScreenState
    required_anchor: str
    safe_action: str
    expected_states: tuple[ScreenState, ...]


# Intentionally empty until a real, unambiguous safe popup fixture is captured.
POPUP_HANDLERS: tuple[PopupHandler, ...] = ()
