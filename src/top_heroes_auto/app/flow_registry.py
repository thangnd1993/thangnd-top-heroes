"""Feature registration only; scheduling has no knowledge of feature names/phases."""
from dataclasses import dataclass
from typing import Callable

from top_heroes_auto.automation.guard import SafetyError

COMPLETE = frozenset({'SUCCESS', 'NOT_AVAILABLE', 'ALREADY_VERIFIED', 'SUCCESS_WITH_RECOVERY_WARNING',
                      'DISABLED', 'NOT_APPLICABLE'})


@dataclass(frozen=True)
class Flow:
    id: str
    rewards: tuple[str, ...]
    run: Callable
    enabled: bool = True
    supported: bool = True
    applicable: Callable = lambda target: True
    # Read-only feature-owned journal qualification before lifecycle/navigation.
    completed: Callable = lambda session, rewards: {}


class FlowRegistry:
    def __init__(self):
        self._flows = {}

    def register(self, flow):
        existing = {reward for item in self._flows.values() for reward in item.rewards}
        if not flow.id or not flow.rewards or flow.id in self._flows or existing.intersection(flow.rewards):
            raise ValueError('Flow/reward registrations must be unique and nonempty.')
        self._flows[flow.id] = flow
        return flow

    def snapshot(self, enabled=None):
        enabled = enabled or {}
        if any(type(value) is not bool for value in enabled.values()):
            raise SafetyError('Enabled configuration must be explicit booleans.')
        if set(enabled)-self._flows.keys():
            raise SafetyError('Unknown configured automation flow.')
        # Frozen per-instance snapshot; changes during execution apply next instance.
        from dataclasses import replace

        return tuple(replace(flow, enabled=enabled.get(flow.id, flow.enabled)) for flow in self._flows.values())


REGISTRY = FlowRegistry()


def production_registry():
    # Feature modules register themselves; future modules use the same extension
    # point without changing automation_fleet or its instance-first lifecycle.
    from top_heroes_auto.app import reward_flows  # noqa: F401

    return REGISTRY
