"""Bounded runtime for qualified, fixed Phase 6 flows.

Coordinates are derived only from semantic evidence in the current frame.
Packaged flows remain disabled until their complete qualification is recorded;
tests and future adapters may inject fully-qualified profiles.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from top_heroes_auto.automation.phase6_fixed_flows import (
    FixedFlowSpec,
    FixedStepKind,
)
from top_heroes_auto.storage.store import Store
from top_heroes_auto.vision.models import BoundingBox


class FixedFlowStatus(StrEnum):
    SUCCESS = "SUCCESS"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    UNKNOWN = "UNKNOWN"
    FORBIDDEN = "FORBIDDEN"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    ACTION_RESULT_UNCERTAIN = "ACTION_RESULT_UNCERTAIN"
    CANCELLED = "CANCELLED"
    BOUNDS_EXCEEDED = "BOUNDS_EXCEEDED"
    ALREADY_ATTEMPTED = "ALREADY_ATTEMPTED"


@dataclass(frozen=True)
class FixedRoleEvidence:
    role: str
    box: BoundingBox
    score: float = 1.0


@dataclass(frozen=True)
class FixedFlowFrame:
    index: int
    name: str
    serial: str
    boot_id: str
    capture_id: str
    evidence: tuple[FixedRoleEvidence, ...]

    def matches(self, role: str) -> tuple[FixedRoleEvidence, ...]:
        return tuple(item for item in self.evidence if item.role == role and item.score >= 0.9)


class FixedFlowPort(Protocol):
    def observe(self) -> FixedFlowFrame: ...

    def tap(
        self,
        frame: FixedFlowFrame,
        role: str,
        point: tuple[int, int],
        kind: FixedStepKind,
    ) -> None: ...


class FixedFlowAttemptJournal(Protocol):
    """Durable claim-attempt boundary supplied by the task integration."""

    def is_attempted(self, key: FixedAttemptKey) -> bool: ...

    def reserve(self, key: FixedAttemptKey, capture_id: str) -> bool: ...

    def verify(self, key: FixedAttemptKey, capture_id: str) -> None: ...


@dataclass(frozen=True)
class FixedAttemptKey:
    index: int
    name: str
    flow_id: str
    cycle_key: str

    def __post_init__(self):
        if self.index < 0 or not self.name or not self.flow_id or not self.cycle_key:
            raise ValueError("A fixed claim attempt requires account, reward and proven cycle scope.")


class StoreFixedFlowAttemptJournal:
    """Persist fixed-flow intent through the existing RESERVED/VERIFIED ledger."""

    def __init__(
        self,
        store: Store,
        namespace: str,
        task_run_id: int,
        index: int,
        name: str,
    ):
        self.store = store
        self.namespace = namespace
        self.task_run_id = task_run_id
        self.identity = index, name
        self.pending: dict[FixedAttemptKey, int] = {}

    def _check(self, key: FixedAttemptKey) -> None:
        if (key.index, key.name) != self.identity:
            raise ValueError("Fixed-flow journal identity changed.")

    def is_attempted(self, key: FixedAttemptKey) -> bool:
        self._check(key)
        return any(
            row["reward_id"] == key.flow_id
            and (row["cycle_key"] == key.cycle_key or row["status"] == "RESERVED")
            for row in self.store.reward_claims(self.namespace, key.index)
        )

    def reserve(self, key: FixedAttemptKey, capture_id: str) -> bool:
        self._check(key)
        if key in self.pending or self.is_attempted(key):
            return False
        evidence = json.dumps(
            {
                "index": key.index,
                "name": key.name,
                "flow_id": key.flow_id,
                "cycle_key": key.cycle_key,
                "capture_id": capture_id,
            },
            ensure_ascii=False,
            allow_nan=False,
        )
        claim_id = self.store.reserve_reward_claim(
            self.task_run_id,
            key.flow_id,
            key.cycle_key,
            evidence,
            expected_instance=self.identity,
        )
        self.pending[key] = claim_id
        return True

    def verify(self, key: FixedAttemptKey, capture_id: str) -> None:
        self._check(key)
        claim_id = self.pending.get(key)
        if claim_id is None:
            raise ValueError("Fixed-flow claim has no reservation in this task run.")
        evidence = json.dumps(
            {
                "index": key.index,
                "name": key.name,
                "flow_id": key.flow_id,
                "cycle_key": key.cycle_key,
                "capture_id": capture_id,
            },
            ensure_ascii=False,
            allow_nan=False,
        )
        self.store.verify_reward_claim(claim_id, self.task_run_id, evidence)


@dataclass
class FixedFlowResult:
    status: FixedFlowStatus
    actions: list[str] = field(default_factory=list)
    captures: list[str] = field(default_factory=list)
    error: str | None = None


def _intersects(first: BoundingBox, second: BoundingBox) -> bool:
    return not (
        first.x + first.width <= second.x
        or second.x + second.width <= first.x
        or first.y + first.height <= second.y
        or second.y + second.height <= first.y
    )


class FixedFlowRunner:
    """Execute only explicit steps, each authorized by one fresh frame."""

    def __init__(
        self,
        *,
        max_actions: int = 6,
        journal: FixedFlowAttemptJournal | None = None,
        cycle_key: str | None = None,
    ):
        if max_actions <= 0:
            raise ValueError("Fixed-flow action bound must be positive.")
        self.max_actions = max_actions
        self.journal = journal
        self.cycle_key = cycle_key

    def run(
        self,
        port: FixedFlowPort,
        spec: FixedFlowSpec,
        index: int,
        name: str,
        cancelled=lambda: False,
    ) -> FixedFlowResult:
        if not spec.qualification.activation_ready or not spec.steps:
            return FixedFlowResult(
                FixedFlowStatus.NOT_IMPLEMENTED,
                error="Flow lacks qualified clean anchors, zero-cost, availability, or postcondition proof.",
            )
        if len(spec.steps) > self.max_actions:
            return FixedFlowResult(FixedFlowStatus.BOUNDS_EXCEEDED)
        has_claim = any(step.kind == FixedStepKind.CLAIM for step in spec.steps)
        if has_claim and (self.journal is None or not self.cycle_key):
            return FixedFlowResult(
                FixedFlowStatus.NOT_IMPLEMENTED,
                error="A durable account/reward/cycle journal is required before observation.",
            )
        attempt_key = FixedAttemptKey(index, name, spec.id, self.cycle_key) if has_claim else None
        try:
            if self.journal is not None and attempt_key and self.journal.is_attempted(attempt_key):
                return FixedFlowResult(FixedFlowStatus.ALREADY_ATTEMPTED)
        except Exception as exc:  # noqa: BLE001 - unknown journal state forbids input
            return FixedFlowResult(FixedFlowStatus.ACTION_RESULT_UNCERTAIN, error=str(exc))

        result = FixedFlowResult(FixedFlowStatus.UNKNOWN)
        seen: set[str] = set()
        transport: tuple[str, str] | None = None
        expected_destination: str | None = None
        claim_reserved = False

        for step in spec.steps:
            if cancelled():
                result.status = FixedFlowStatus.CANCELLED
                return result
            try:
                frame = port.observe()
            except Exception as exc:  # noqa: BLE001 - capture failure after claim is uncertain
                result.status = (
                    FixedFlowStatus.ACTION_RESULT_UNCERTAIN
                    if claim_reserved
                    else FixedFlowStatus.UNKNOWN
                )
                result.error = str(exc)
                return result
            result.captures.append(frame.capture_id)
            identity_error = self._validate_frame(frame, index, name, seen, transport)
            if identity_error:
                result.status = identity_error
                return result
            transport = frame.serial, frame.boot_id
            seen.add(frame.capture_id)
            if expected_destination is not None and len(frame.matches(expected_destination)) != 1:
                result.error = f"Expected destination {expected_destination!r} was not uniquely verified."
                return result

            if step.kind == FixedStepKind.CLAIM and step.unavailable_role:
                unavailable = frame.matches(step.unavailable_role)
                claim_evidence = {
                    step.target_role,
                    spec.free_role,
                    spec.available_role,
                }
                claimable_present = any(frame.matches(role) for role in claim_evidence)
                if len(unavailable) == 1 and not claimable_present:
                    result.status = FixedFlowStatus.NOT_AVAILABLE
                    return result
                if unavailable:
                    result.error = "Unavailable and claimable evidence overlap or are ambiguous."
                    return result

            required = {role: frame.matches(role) for role in step.required_roles}
            if any(len(matches) != 1 for matches in required.values()):
                result.error = f"Step {step.id!r} lacks unique current-frame evidence."
                return result
            target = required[step.target_role][0]
            forbidden = tuple(
                item
                for role in spec.forbidden_roles
                for item in frame.matches(role)
                if _intersects(target.box, item.box)
            )
            if forbidden:
                result.status = FixedFlowStatus.FORBIDDEN
                result.error = f"Target {step.target_role!r} overlaps forbidden evidence."
                return result
            if step.kind == FixedStepKind.CLAIM:
                try:
                    reserved = bool(
                        self.journal
                        and attempt_key
                        and self.journal.reserve(attempt_key, frame.capture_id)
                    )
                except Exception as exc:  # noqa: BLE001 - unknown reservation state forbids input
                    result.status = FixedFlowStatus.ACTION_RESULT_UNCERTAIN
                    result.error = str(exc)
                    return result
                if not reserved:
                    result.status = FixedFlowStatus.ALREADY_ATTEMPTED
                    return result
                claim_reserved = True
            try:
                port.tap(frame, step.target_role, target.box.center, step.kind)
            except Exception as exc:  # noqa: BLE001 - an input result must never be retried
                result.status = FixedFlowStatus.ACTION_RESULT_UNCERTAIN
                result.error = str(exc)
                return result
            result.actions.append(step.id)
            expected_destination = step.destination_role

        if cancelled():
            result.status = FixedFlowStatus.CANCELLED
            return result
        try:
            after = port.observe()
        except Exception as exc:  # noqa: BLE001 - a claim was already reserved/dispatched
            result.status = FixedFlowStatus.ACTION_RESULT_UNCERTAIN
            result.error = str(exc)
            return result
        result.captures.append(after.capture_id)
        identity_error = self._validate_frame(after, index, name, seen, transport)
        if identity_error:
            result.status = identity_error
            return result
        if expected_destination is None or len(after.matches(expected_destination)) != 1:
            result.status = (
                FixedFlowStatus.ACTION_RESULT_UNCERTAIN if claim_reserved else FixedFlowStatus.UNKNOWN
            )
            result.error = "Fresh postcondition was not uniquely verified."
            return result
        if spec.task == "vip-reward":
            if len(after.matches(spec.page_role)) != 1:
                result.status = FixedFlowStatus.ACTION_RESULT_UNCERTAIN
                result.error = "VIP claim postcondition lacks the independent VIP page anchor."
                return result
            if after.matches(spec.action_role) or after.matches(spec.available_role):
                result.status = FixedFlowStatus.ACTION_RESULT_UNCERTAIN
                result.error = "VIP claimable action remains after dispatch; success is unverified."
                return result
        try:
            if self.journal is not None and attempt_key:
                self.journal.verify(attempt_key, after.capture_id)
        except Exception as exc:  # noqa: BLE001 - reservation stays durable and non-repeatable
            result.status = FixedFlowStatus.ACTION_RESULT_UNCERTAIN
            result.error = str(exc)
            return result
        result.status = FixedFlowStatus.SUCCESS
        return result

    @staticmethod
    def _validate_frame(
        frame: FixedFlowFrame,
        index: int,
        name: str,
        seen: set[str],
        transport: tuple[str, str] | None,
    ) -> FixedFlowStatus | None:
        if (frame.index, frame.name) != (index, name):
            return FixedFlowStatus.IDENTITY_MISMATCH
        current_transport = frame.serial, frame.boot_id
        if not all(current_transport) or (transport is not None and current_transport != transport):
            return FixedFlowStatus.IDENTITY_MISMATCH
        if not frame.capture_id or frame.capture_id in seen:
            return FixedFlowStatus.UNKNOWN
        return None
