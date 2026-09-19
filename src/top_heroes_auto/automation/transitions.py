from __future__ import annotations

from dataclasses import dataclass

from top_heroes_auto.vision.models import ScreenState


@dataclass(frozen=True)
class TransitionRule:
    source: ScreenState
    action: str
    expected: tuple[ScreenState, ...]
    retry_limit: int


CORE_TRANSITIONS = (
    TransitionRule(
        ScreenState.ANDROID_HOME,
        "launch_game",
        (ScreenState.GAME_LOADING, ScreenState.GAME_HOME),
        1,
    ),
    TransitionRule(
        ScreenState.GAME_LOADING,
        "wait",
        (ScreenState.GAME_LOADING, ScreenState.GAME_HOME),
        24,
    ),
    TransitionRule(ScreenState.GAME_HOME, "none", (ScreenState.GAME_HOME,), 0),
    TransitionRule(ScreenState.UNKNOWN, "confirm_only", (ScreenState.UNKNOWN,), 1),
)
