import json
from dataclasses import replace
from pathlib import Path

import pytest

from top_heroes_auto.automation.phase6_fixed_flows import (
    RANKING_CHEST,
    SHOP_DAILY,
    VIP_DAILY,
    FlowQualification,
)
from top_heroes_auto.automation.phase6_fixed_runtime import (
    FixedAttemptKey,
    FixedFlowFrame,
    FixedFlowRunner,
    FixedFlowStatus,
    FixedRoleEvidence,
    StoreFixedFlowAttemptJournal,
)
from top_heroes_auto.storage.store import Store
from top_heroes_auto.vision.models import BoundingBox

IDENTITY = (2, "5-Emmmmm", "emulator-5558", "boot-2")
QUALIFIED = FlowQualification(True, True, True, True)


def _role(role, x, y=10, size=12):
    return FixedRoleEvidence(role, BoundingBox(x, y, size, size))


def _frame(stamp, *roles, identity=IDENTITY, shift=0, scale=1):
    evidence = tuple(
        _role(role, (10 + number * 24 + shift) * scale, size=12 * scale)
        for number, role in enumerate(roles)
    )
    return FixedFlowFrame(*identity, stamp, evidence)


class Port:
    def __init__(self, *frames, fail_at=None, fail_observe_at=None):
        self.frames = iter(frames)
        self.actions = []
        self.fail_at = fail_at
        self.fail_observe_at = fail_observe_at
        self.observations = 0

    def observe(self):
        self.observations += 1
        if self.observations == self.fail_observe_at:
            raise OSError("capture failed")
        return next(self.frames)

    def tap(self, frame, role, point, kind):
        self.actions.append((role, point, kind.value, frame.capture_id))
        if role == self.fail_at:
            raise OSError("input result unknown")


class Journal:
    def __init__(self, fail_reserve=False):
        self.reserved = {}
        self.verified = {}
        self.fail_reserve = fail_reserve

    def is_attempted(self, key):
        return key in self.reserved

    def reserve(self, key, capture_id):
        if self.fail_reserve:
            raise OSError("journal unavailable")
        if key in self.reserved:
            return False
        self.reserved[key] = capture_id
        return True

    def verify(self, key, capture_id):
        assert key in self.reserved
        self.verified[key] = capture_id


def _runner(**kwargs):
    return FixedFlowRunner(
        journal=kwargs.pop("journal", Journal()),
        cycle_key=kwargs.pop("cycle_key", "proven-daily-cycle"),
        **kwargs,
    )


def _qualified(spec):
    return replace(spec, qualification=QUALIFIED)


def _vip_frames(*, shift=0, scale=1, paid_box=None):
    home = _frame("home", "home-vip-entry", shift=shift, scale=scale)
    page = _frame(
        "vip",
        "vip-page",
        "vip-daily-claim",
        "vip-daily-free-label",
        "vip-daily-available",
        shift=shift,
        scale=scale,
    )
    if paid_box is not None:
        page = replace(page, evidence=page.evidence + (FixedRoleEvidence("vip-paid-upgrade", paid_box),))
    post = _frame("post", "vip-daily-postcondition", shift=shift, scale=scale)
    return home, page, post


@pytest.mark.parametrize(
    ("spec", "frames", "expected_actions"),
    (
        (
            VIP_DAILY,
            _vip_frames(),
            ("home-vip-entry", "vip-daily-claim"),
        ),
        (
            SHOP_DAILY,
            (
                _frame("home", "home-shop-entry"),
                _frame(
                    "shop",
                    "shop-daily-offer-page",
                    "shop-daily-gift",
                    "shop-daily-gift-free-label",
                    "shop-daily-gift-available",
                ),
                _frame("post", "shop-daily-gift-postcondition"),
            ),
            ("home-shop-entry", "shop-daily-gift"),
        ),
        (
            RANKING_CHEST,
            (
                _frame("home", "home-avatar-entry"),
                _frame("profile", "profile-page", "profile-ranking-tab"),
                _frame(
                    "ranking",
                    "ranking-page",
                    "ranking-top-left-chest",
                    "ranking-chest-free-proof",
                    "ranking-chest-available",
                ),
                _frame("post", "ranking-chest-postcondition"),
            ),
            ("home-avatar-entry", "profile-ranking-tab", "ranking-top-left-chest"),
        ),
    ),
)
def test_three_injectable_fixed_flows_verify_every_destination_and_postcondition(
    spec, frames, expected_actions
):
    port = Port(*frames)
    result = _runner().run(port, _qualified(spec), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.SUCCESS
    assert tuple(action[0] for action in port.actions) == expected_actions
    assert len(set(result.captures)) == len(result.captures)


@pytest.mark.parametrize(("shift", "scale"), ((0, 1), (37, 1), (10, 2)))
def test_current_frame_targets_shift_and_scale_without_global_coordinates(shift, scale):
    port = Port(*_vip_frames(shift=shift, scale=scale))
    result = _runner().run(port, _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.SUCCESS
    expected_x = (10 + 24 + shift) * scale + (12 * scale) // 2
    assert port.actions[1][1][0] == expected_x


def test_paid_offer_elsewhere_does_not_block_free_target_but_overlap_always_blocks():
    far_paid = BoundingBox(260, 120, 40, 30)
    allowed = Port(*_vip_frames(paid_box=far_paid))
    assert _runner().run(allowed, _qualified(VIP_DAILY), 2, "5-Emmmmm").status == FixedFlowStatus.SUCCESS

    overlap = BoundingBox(30, 8, 20, 20)
    blocked = Port(*_vip_frames(paid_box=overlap))
    result = _runner().run(blocked, _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.FORBIDDEN
    assert tuple(action[0] for action in blocked.actions) == ("home-vip-entry",)


def test_attention_marker_alone_is_discovery_not_claim_authority():
    port = Port(
        _frame("home", "home-shop-entry"),
        _frame("shop", "shop-daily-offer-page", "shop-attention-dot"),
    )
    result = _runner().run(port, _qualified(SHOP_DAILY), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.UNKNOWN
    assert tuple(action[0] for action in port.actions) == ("home-shop-entry",)


def test_positive_unavailable_is_not_inferred_from_missing_controls():
    positive = Port(
        _frame("home", "home-vip-entry"),
        _frame("vip", "vip-page", "vip-daily-unavailable"),
    )
    result = _runner().run(positive, _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.NOT_AVAILABLE

    missing = Port(_frame("home", "home-vip-entry"), _frame("vip", "vip-page"))
    result = _runner().run(missing, _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.UNKNOWN


@pytest.mark.parametrize(
    "changed",
    (
        (7, "Other", "emulator-5558", "boot-2"),
        (2, "5-Emmmmm", "emulator-5560", "boot-2"),
        (2, "5-Emmmmm", "emulator-5558", "boot-new"),
    ),
)
def test_identity_or_transport_change_stops_before_follow_up_input(changed):
    home, page, _ = _vip_frames()
    page = replace(page, index=changed[0], name=changed[1], serial=changed[2], boot_id=changed[3])
    port = Port(home, page)
    result = _runner().run(port, _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.IDENTITY_MISMATCH
    assert tuple(action[0] for action in port.actions) == ("home-vip-entry",)


def test_stale_frame_and_uncertain_input_are_never_retried():
    home, page, _ = _vip_frames()
    stale = replace(page, capture_id="home")
    stale_port = Port(home, stale)
    assert _runner().run(stale_port, _qualified(VIP_DAILY), 2, "5-Emmmmm").status == FixedFlowStatus.UNKNOWN
    assert len(stale_port.actions) == 1

    uncertain = Port(home, page, fail_at="vip-daily-claim")
    journal = Journal()
    result = _runner(journal=journal).run(uncertain, _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.ACTION_RESULT_UNCERTAIN
    assert len(uncertain.actions) == 2
    retry = _runner(journal=journal).run(Port(), _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert retry.status == FixedFlowStatus.ALREADY_ATTEMPTED


def test_bounds_and_persisted_attempt_block_before_observation():
    never = Port()
    result = _runner(max_actions=1).run(never, _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.BOUNDS_EXCEEDED
    journal = Journal()
    key = FixedAttemptKey(2, "5-Emmmmm", VIP_DAILY.id, "proven-daily-cycle")
    assert journal.reserve(key, "historical")
    result = _runner(journal=journal).run(never, _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.ALREADY_ATTEMPTED


@pytest.mark.parametrize("spec", (VIP_DAILY, SHOP_DAILY, RANKING_CHEST))
def test_packaged_unqualified_flows_stop_before_device_observation(spec):
    result = _runner().run(Port(), spec, 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.NOT_IMPLEMENTED


def test_qualified_claim_without_durable_journal_stops_before_observation():
    result = FixedFlowRunner().run(Port(), _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert result.status == FixedFlowStatus.NOT_IMPLEMENTED


def test_journal_reservation_failure_prevents_claim_input():
    home, page, _ = _vip_frames()
    port = Port(home, page)
    result = _runner(journal=Journal(fail_reserve=True)).run(
        port, _qualified(VIP_DAILY), 2, "5-Emmmmm"
    )
    assert result.status == FixedFlowStatus.ACTION_RESULT_UNCERTAIN
    assert tuple(action[0] for action in port.actions) == ("home-vip-entry",)


def test_post_claim_capture_failure_is_structured_and_blocks_restart():
    journal = Journal()
    home, page, _ = _vip_frames()
    port = Port(home, page, fail_observe_at=3)
    first = _runner(journal=journal).run(port, _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert first.status == FixedFlowStatus.ACTION_RESULT_UNCERTAIN
    assert tuple(action[0] for action in port.actions) == ("home-vip-entry", "vip-daily-claim")
    retry = _runner(journal=journal).run(Port(), _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert retry.status == FixedFlowStatus.ALREADY_ATTEMPTED


def test_successful_claim_is_also_non_repeatable_for_same_account_reward_cycle():
    journal = Journal()
    first = _runner(journal=journal).run(
        Port(*_vip_frames()), _qualified(VIP_DAILY), 2, "5-Emmmmm"
    )
    assert first.status == FixedFlowStatus.SUCCESS
    retry = _runner(journal=journal).run(Port(), _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert retry.status == FixedFlowStatus.ALREADY_ATTEMPTED


def test_store_journal_persists_verified_claim_and_blocks_new_task_run(tmp_path):
    store = Store(tmp_path / "verified.sqlite3")
    namespace = "ldplayer:test"
    first_run = store.create_task_run(namespace, "ranking-chest", 2, "5-Emmmmm")
    first_journal = StoreFixedFlowAttemptJournal(
        store, namespace, first_run, 2, "5-Emmmmm"
    )
    result = _runner(journal=first_journal).run(
        Port(*_vip_frames()), _qualified(VIP_DAILY), 2, "5-Emmmmm"
    )
    assert result.status == FixedFlowStatus.SUCCESS
    rows = store.reward_claims(namespace, 2)
    assert len(rows) == 1 and rows[0]["status"] == "VERIFIED"

    second_run = store.create_task_run(namespace, "ranking-chest", 2, "5-Emmmmm")
    restarted = StoreFixedFlowAttemptJournal(store, namespace, second_run, 2, "5-Emmmmm")
    retry = _runner(journal=restarted).run(Port(), _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert retry.status == FixedFlowStatus.ALREADY_ATTEMPTED


def test_store_journal_retains_reserved_after_uncertain_dispatch(tmp_path):
    store = Store(tmp_path / "reserved.sqlite3")
    namespace = "ldplayer:test"
    task_run = store.create_task_run(namespace, "vip-reward", 2, "5-Emmmmm")
    journal = StoreFixedFlowAttemptJournal(store, namespace, task_run, 2, "5-Emmmmm")
    home, page, _ = _vip_frames()
    result = _runner(journal=journal).run(
        Port(home, page, fail_at="vip-daily-claim"),
        _qualified(VIP_DAILY),
        2,
        "5-Emmmmm",
    )
    assert result.status == FixedFlowStatus.ACTION_RESULT_UNCERTAIN
    rows = store.reward_claims(namespace, 2)
    assert len(rows) == 1 and rows[0]["status"] == "RESERVED"


def test_missing_postcondition_keeps_reservation_and_blocks_restart():
    journal = Journal()
    home, page, _ = _vip_frames()
    missing = _frame("after", "vip-page")
    first = _runner(journal=journal).run(
        Port(home, page, missing), _qualified(VIP_DAILY), 2, "5-Emmmmm"
    )
    assert first.status == FixedFlowStatus.UNKNOWN
    second = _runner(journal=journal).run(Port(), _qualified(VIP_DAILY), 2, "5-Emmmmm")
    assert second.status == FixedFlowStatus.ALREADY_ATTEMPTED


def test_reference_manifest_is_versioned_hashed_and_never_runtime_input():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "assets" / "tasks" / "phase6" / "reference-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["version"] == "phase6-annotated-references-v1"
    assert manifest["runtime_input"] is False
    assert len(manifest["references"]) == 7
    assert all(len(item["sha256"]) == 64 for item in manifest["references"])
    assert all("Desktop" not in item["file"] for item in manifest["references"])
