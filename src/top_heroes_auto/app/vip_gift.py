"""The separately journalled upper gift explicitly authorized by the VIP reference."""

import json
import time
from dataclasses import replace

from top_heroes_auto.app.phase6_runtime import phase6_asset_root, reward_port_factory
from top_heroes_auto.automation.free_rewards import FreeRewardGuard
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.phase6_visual import RewardRule
from top_heroes_auto.automation.reward_journal import evidence_json
from top_heroes_auto.automation.vip_period import current_attempts, cycle_key
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.models import ScreenState


def gift_profile(daily_profile):
    anchors = {a.id: a for a in load_anchors(phase6_asset_root() / "vip-gift")}
    return replace(daily_profile, task="vip-upper-gift", anchors=(
        ("page", daily_profile.anchor_map["page"]),
        ("paid", daily_profile.anchor_map["paid"]),
        ("claim", anchors["gift-core"]), ("free", anchors["gift-coins"]),
        ("available", anchors["gift-badge"]),
        ("unavailable", anchors["gift-unavailable"]),
    ), rewards=(RewardRule("vip-upper-gift"),))


def gift_state(screen):
    evidence = {e.anchor_id: e for e in screen.detection.evidence}
    if screen.detection.state != ScreenState.FREE_REWARD_PAGE:
        return "UNKNOWN"
    core, coins, badge = (evidence[k] for k in ("gift-core", "gift-coins", "gift-badge"))
    unavailable = evidence.get("gift-unavailable")
    # Positive, unique full-icon evidence includes the clear badge area. A
    # missing/weak badge alone can never establish unavailability.
    if unavailable and unavailable.matched and unavailable.score >= .98 and unavailable.device_box:
        box = unavailable.device_box
        if badge.score >= badge.threshold:
            if not badge.matched or badge.device_box is None:
                return "UNKNOWN"
            x, y = badge.device_box.center
            if box.x <= x < box.x + box.width and box.y <= y < box.y + box.height:
                return "UNKNOWN"
        return "NOT_AVAILABLE"
    if not core.matched or not coins.matched:
        return "UNKNOWN"
    a, b = core.device_box, coins.device_box
    if a is None or b is None or abs(a.center[0] - b.center[0]) > a.width or abs(a.center[1] - b.center[1]) > a.height:
        return "UNKNOWN"
    if not badge.matched:
        return "UNKNOWN"
    c = badge.device_box
    if c is None or max(abs(a.center[0] - c.center[0]), abs(a.center[1] - c.center[1])) > 2*max(a.width, a.height):
        return "UNKNOWN"
    return "FREE_CLAIMABLE"


def run_upper_gift(manager, snapshot, index, name, profile, folder, entry, task_id, row):
    """Mutates the supplied report so uncertain input survives any exception."""
    row.update(result="UNKNOWN", claim_dispatched=False, journal_state="NONE")
    prior = current_attempts(manager.store.reward_claims(manager.namespace, index), "vip-upper-gift")
    if prior:
        row.update(result="ALREADY_VERIFIED" if prior[-1]["status"] == "VERIFIED" else "ALREADY_ATTEMPTED",
                   journal_state=prior[-1]["status"], previous_claim_id=prior[-1]["id"],
                   dispatch_state=prior[-1]["dispatch_state"])
        return
    port = reward_port_factory(manager, snapshot, index, name, gift_profile(profile), folder)
    port.set_entry_geometry(entry)
    before = port.observe()
    guard = FreeRewardGuard(index, name)
    guard.observe(before)
    row["qualification_captures"] = [before.capture_id]
    for _ in range(2):
        if gift_state(before) != "UNKNOWN" or before.detection.state != ScreenState.FREE_REWARD_PAGE:
            break
        # The gift pulses. Observe only; never tap an unqualified phase of the icon.
        time.sleep(.5)
        before = port.observe()
        guard.observe(before)
        row["qualification_captures"].append(before.capture_id)
    row.update(before=json.loads(evidence_json(before)), availability=gift_state(before))
    if row["availability"] != "FREE_CLAIMABLE":
        row["result"] = row["availability"]
        return
    reward = before.rewards[0]
    point = guard.claim(before, reward)
    port.validate_claim(before, reward, point)
    row["geometry"] = port.geometry_report
    claim_id = manager.store.reserve_reward_claim(task_id, reward.reward_id,
        cycle_key("vip-upper-gift"), evidence_json(before),
        expected_instance=(index, name), not_dispatched=True, vip_daily_period=True)
    row.update(claim_id=claim_id, journal_state="RESERVED")

    def before_input():
        manager.store.mark_reward_dispatch(claim_id, task_id)
        row.update(claim_dispatched="POSSIBLE", result="ACTION_DISPATCHED_UNVERIFIED")

    try:
        port.claim(before, reward, point, before_input=before_input)
        row["claim_dispatched"] = True
        after = port.observe()
        guard.observe(after)
        row["immediate_after"] = json.loads(evidence_json(after))
        after = port.dismiss_receipts(after)
        row["overlay_events"] = port.overlay_events
        if after.capture_id != row["immediate_after"]["capture_id"]:
            guard.observe(after)
        row["after"] = json.loads(evidence_json(after))
        # AVAILABLE before input -> identifiable inactive gift afterwards.
        if gift_state(after) == "NOT_AVAILABLE":
            manager.store.verify_reward_claim(claim_id, task_id, evidence_json(after))
            row.update(result="SUCCESS", post_condition="VERIFIED", journal_state="VERIFIED")
        else:
            row.update(result="ACTION_DISPATCHED_UNVERIFIED", post_condition="UNKNOWN")
    except (OSError, RuntimeError, ValueError, SafetyError) as exc:
        row["error"] = str(exc)
        if row["claim_dispatched"]:
            row["result"] = "ACTION_DISPATCHED_UNVERIFIED"
        raise
    finally:
        receipt = next(r for r in manager.store.reward_claims(manager.namespace, index) if r["id"] == claim_id)
        row.update(journal_state=receipt["status"], dispatch_state=receipt["dispatch_state"])
        if receipt["dispatch_state"] == "NOT_DISPATCHED":
            manager.store.release_undispatched_reward(claim_id, task_id, "VIP dispatch hook was never entered.")
            row["journal_state"] = "NONE"
