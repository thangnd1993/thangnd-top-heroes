"""Late qualified popup transitions from the Oct14 standalone run."""
from dataclasses import replace
from pathlib import Path

import pytest

from top_heroes_auto.automation.recovery import HomeRecoveryEngine, RecoveryObservation, RecoveryStatus
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, ScreenDetection, ScreenState


class TimedPort:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.time = 0.0
        self.inputs = []
        self.captures = 0

    def observe(self, step):
        at, state, key, boot = next(self.frames)
        self.time = max(self.time, at)
        self.captures += 1
        anchors = tuple(AnchorEvidence(f'{key}-{i}', state, .99, .98, True,
                         device_box=BoundingBox(i*100, 20, 40, 40)) for i in range(2))
        detected = ScreenDetection(state, .99, anchors, str(at), None, 0)
        return RecoveryObservation(detected, Path(f'{step}.png'), 'explicit-target', boot)

    def dismiss_overlay(self, observation):
        self.inputs.append((self.time, observation.detection.state))
        return 58, 1203

    def sleep(self, seconds):
        self.time += seconds


def run(port, **kwargs):
    return HomeRecoveryEngine(clock=lambda:port.time, sleep=port.sleep, **kwargs).ensure_game_home(port)


def frame(at, state, key='pair', boot='same-boot'):
    return at, state, key, boot


def test_loading_to_two_distinct_known_popups_has_one_bounded_navigation_window():
    port = TimedPort([
        frame(90, ScreenState.GAME_LOADING),
        frame(119, ScreenState.EVENT_PROMO), frame(130, ScreenState.EVENT_PROMO),
        frame(145, ScreenState.HOME_OVERLAY), frame(160, ScreenState.HOME_OVERLAY),
        frame(180, ScreenState.GAME_HOME),
    ])
    result = run(port)
    assert result.status == RecoveryStatus.SUCCESS
    assert result.actions.count('qualified_post_loading_overlay_window') == 1
    assert len(port.inputs) == 2
    assert result.duration == 180  # One post-input frame may finish after deadline.


@pytest.mark.parametrize('variant', ['unknown', 'weak', 'missing-box', 'different-boot'])
def test_unqualified_transition_does_not_extend_or_dispatch(variant):
    state = ScreenState.UNKNOWN if variant == 'unknown' else ScreenState.EVENT_PROMO
    port = TimedPort([frame(90, ScreenState.GAME_LOADING),
                      frame(119, state, boot='other' if variant=='different-boot' else 'same-boot')])
    original = port.observe

    def observe(step):
        observation = original(step)
        if step==2 and variant in {'weak','missing-box'}:
            evidence = tuple(replace(e, score=.5) if variant=='weak' else replace(e, device_box=None)
                             for e in observation.detection.evidence)
            return replace(observation, detection=replace(observation.detection, evidence=evidence))
        return observation

    port.observe = observe
    result = run(port)
    assert result.status == RecoveryStatus.LIMIT_REACHED
    assert 'qualified_post_loading_overlay_window' not in result.actions
    assert not port.inputs


def test_persistent_popup_preserves_two_dismissal_limit():
    port = TimedPort([frame(90, ScreenState.GAME_LOADING)] +
                     [frame(t, ScreenState.EVENT_PROMO) for t in (119,130,140,150)])
    result = run(port)
    assert result.status == RecoveryStatus.PROMO_BLOCKING
    assert len(port.inputs) == 2
    assert result.actions.count('qualified_post_loading_overlay_window') == 1


def test_different_popups_cannot_renew_window_or_send_input_after_deadline():
    port = TimedPort([frame(90, ScreenState.GAME_LOADING),
                      frame(119, ScreenState.EVENT_PROMO), frame(130, ScreenState.EVENT_PROMO),
                      frame(150, ScreenState.HOME_OVERLAY), frame(170, ScreenState.HOME_OVERLAY),
                      frame(185, ScreenState.EVENT_PROMO, 'new-popup')])
    result = run(port)
    assert result.status == RecoveryStatus.LIMIT_REACHED
    assert result.actions.count('qualified_post_loading_overlay_window') == 1
    assert len(port.inputs) == 2


def test_post_dismissal_frame_is_captured_but_changed_runtime_cannot_succeed():
    port = TimedPort([frame(90, ScreenState.GAME_LOADING),
                      frame(119, ScreenState.EVENT_PROMO), frame(130, ScreenState.EVENT_PROMO),
                      frame(180, ScreenState.GAME_HOME, boot='replacement')])
    assert run(port).status == RecoveryStatus.ADB_ERROR
    assert len(port.inputs)==1 and port.captures==4


def test_popup_without_prior_loading_keeps_original_deadline():
    port = TimedPort([frame(119, ScreenState.EVENT_PROMO)])
    result = run(port)
    assert result.status == RecoveryStatus.LIMIT_REACHED
    assert 'qualified_post_loading_overlay_window' not in result.actions
    assert not port.inputs


def test_step_bound_still_requires_room_for_post_action_capture():
    port = TimedPort([frame(90, ScreenState.GAME_LOADING),
                      frame(119, ScreenState.EVENT_PROMO), frame(130, ScreenState.EVENT_PROMO)])
    result = run(port, max_steps=3)
    assert result.status == RecoveryStatus.LIMIT_REACHED
    assert not port.inputs


def test_slow_confirmation_capture_cannot_dispatch_after_window_ends():
    port = TimedPort([frame(90, ScreenState.GAME_LOADING),
                      frame(119, ScreenState.EVENT_PROMO), frame(185, ScreenState.EVENT_PROMO)])
    assert run(port).status == RecoveryStatus.LIMIT_REACHED
    assert not port.inputs


def test_unknown_after_dismissal_never_gets_input_or_another_window():
    port = TimedPort([frame(90, ScreenState.GAME_LOADING),
                      frame(119, ScreenState.EVENT_PROMO), frame(130, ScreenState.EVENT_PROMO),
                      frame(145, ScreenState.UNKNOWN), frame(155, ScreenState.UNKNOWN)])
    result = run(port)
    assert result.status == RecoveryStatus.UNKNOWN_SCREEN
    assert len(port.inputs)==1
    assert result.actions.count('qualified_post_loading_overlay_window')==1
