from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from test_free_rewards import Port, reward, screen

from top_heroes_auto.automation.free_rewards import ClaimOutcome, FreeRewardExplorer
from top_heroes_auto.automation.reward_journal import JournalledExplorerPort, RewardCycle
from top_heroes_auto.storage.store import Store


def run(store, index=2, name="5-Emmmmm", namespace="installation"):
    return store.create_task_run(namespace, "vip-reward", index, name)


def test_reserved_intent_survives_interruption_and_blocks_new_cycle_and_rename(tmp_path):
    path = tmp_path / "claims.sqlite3"
    store = Store(path)
    first = run(store)
    claim = store.reserve_reward_claim(first, "vip-daily", "proven-cycle-A", "before.png")
    restarted = Store(path)
    second = run(restarted, name="renamed")
    for cycle in ("proven-cycle-A", "proven-cycle-B"):
        with pytest.raises(ValueError, match="retry forbidden"):
            restarted.reserve_reward_claim(second, "vip-daily", cycle, "new.png")
    receipt = restarted.reward_claims("installation", 2)[0]
    assert receipt["id"] == claim and receipt["status"] == "RESERVED"
    assert receipt["instance_name"] == "5-Emmmmm"


def test_verified_claim_requires_own_receipt_and_retains_evidence(tmp_path):
    store = Store(tmp_path / "claims.sqlite3")
    first, other = run(store), run(store)
    claim = store.reserve_reward_claim(first, "vip-daily", "cycle-A", "before.png")
    with pytest.raises(ValueError):
        store.verify_reward_claim(claim, other, "wrong.png")
    with pytest.raises(ValueError):
        store.verify_reward_claim(claim, first, "")
    store.verify_reward_claim(claim, first, "verified-after.png")
    with pytest.raises(ValueError):
        store.verify_reward_claim(claim, first, "overwrite.png")
    with pytest.raises(ValueError, match="retry forbidden"):
        store.reserve_reward_claim(other, "vip-daily", "cycle-A", "new.png")
    store.reserve_reward_claim(other, "vip-daily", "proven-next-cycle", "next.png")
    receipts = store.reward_claims("installation", 2)
    assert receipts[0]["status"] == "VERIFIED"
    assert receipts[0]["after_evidence"] == "verified-after.png"
    assert len(receipts) == 2


def test_verified_index5_idle_claim_cannot_be_reserved_again(tmp_path):
    store = Store(tmp_path / "claims.sqlite3")
    first = store.create_task_run("installation", "idle-reward", 5, "4-Em Pé")
    claim = store.reserve_reward_claim(
        first,
        "idle-reward",
        "idle-conservative-opportunity",
        "claimable-frame.png",
        expected_instance=(5, "4-Em Pé"),
        not_dispatched=True,
    )
    store.mark_reward_dispatch(claim, first)
    store.verify_reward_claim(claim, first, "claimed-frame.png")

    retry = store.create_task_run("installation", "idle-reward", 5, "4-Em Pé")
    with pytest.raises(ValueError, match="retry forbidden"):
        store.reserve_reward_claim(
            retry,
            "idle-reward",
            "idle-conservative-opportunity",
            "later-frame.png",
            expected_instance=(5, "4-Em Pé"),
        )

    rows = store.reward_claims("installation", 5)
    assert len(rows) == 1
    assert rows[0]["status"] == "VERIFIED"
    assert rows[0]["after_evidence"] == "claimed-frame.png"


def test_concurrent_reservations_commit_only_one_intent(tmp_path):
    store = Store(tmp_path / "claims.sqlite3")
    runs = [run(store), run(store)]

    def reserve(task):
        try:
            return store.reserve_reward_claim(task, "free-recruit", str(task), "before.png")
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, runs))
    assert sum(value is not None for value in results) == 1
    assert len(store.reward_claims("installation", 2)) == 1


def test_receipts_are_scoped_to_account_and_installation(tmp_path):
    store = Store(tmp_path / "claims.sqlite3")
    for task in (run(store), run(store, index=3), run(store, namespace="other")):
        store.reserve_reward_claim(task, "vip", "cycle", "before.png")
    assert len(store.reward_claims("installation", 2)) == 1


def test_finished_run_and_missing_identity_cannot_reserve(tmp_path):
    store = Store(tmp_path / "claims.sqlite3")
    task = run(store)
    with pytest.raises(ValueError, match="account"):
        store.reserve_reward_claim(task, "vip", "cycle", "before", expected_instance=(4, "other"))
    for values in (("", "cycle", "before"), ("vip", "", "before"), ("vip", "cycle", "")):
        with pytest.raises(ValueError):
            store.reserve_reward_claim(task, *values)
    store.finish_task_run(task, "CANCELLED")
    with pytest.raises(ValueError, match="active task"):
        store.reserve_reward_claim(task, "vip", "cycle", "before")


def observation(capture, **kwargs):
    return replace(screen(capture, coverage_known=True, **kwargs), index=2, name="5-Emmmmm")


def journal(port, store, task=None):
    return JournalledExplorerPort(
        port, store, task or run(store), 2, "5-Emmmmm",
        lambda before, item: RewardCycle("conservative-opportunity", "available"),
    )


def test_journal_commits_before_dispatch_and_verifies_before_success(tmp_path):
    store = Store(tmp_path / "claims.sqlite3")

    class InspectPort(Port):
        def claim(self, before, item, point):
            receipts = store.reward_claims("installation", 2)
            assert len(receipts) == 1 and receipts[0]["status"] == "RESERVED"
            super().claim(before, item, point)

    port = InspectPort([observation("1", rewards=(reward(),)), observation("2")])
    result = FreeRewardExplorer().run(journal(port, store), 2, "5-Emmmmm")
    assert result.status == "SUCCESS"
    assert store.reward_claims("installation", 2)[0]["status"] == "VERIFIED"


def test_cooldown_result_remains_reserved_across_restart_and_blocks_replay(tmp_path):
    path = tmp_path / "cooldown.sqlite3"
    store = Store(path)

    class CooldownPort(Port):
        def classify_claim(self, before, after, item):
            return ClaimOutcome.COOLDOWN

    port = CooldownPort([observation("1", rewards=(reward(),)), observation("2")])
    result = FreeRewardExplorer().run(journal(port, store), 2, "5-Emmmmm")
    assert result.cooldown == ["gift"]
    assert result.claimed == []
    assert result.claim_outcomes == [{"reward_id": "gift", "outcome": "COOLDOWN"}]
    assert store.reward_claims("installation", 2)[0]["status"] == "RESERVED"

    restarted = Store(path)
    retry = Port([observation("retry", rewards=(reward(),))])
    retry_result = FreeRewardExplorer().run(journal(retry, restarted), 2, "5-Emmmmm")
    assert retry_result.status == "ACTION_RESULT_UNCERTAIN"
    assert retry.actions == []


def test_receipt_result_is_the_only_outcome_that_verifies_journal(tmp_path):
    store = Store(tmp_path / "receipt.sqlite3")

    class ReceiptPort(Port):
        def classify_claim(self, before, after, item):
            return ClaimOutcome.CLAIMED

    port = ReceiptPort([observation("1", rewards=(reward(),)), observation("2")])
    result = FreeRewardExplorer().run(journal(port, store), 2, "5-Emmmmm")
    assert result.claimed == ["gift"]
    assert store.reward_claims("installation", 2)[0]["status"] == "VERIFIED"


@pytest.mark.parametrize("dispatch_fails", [False, True])
def test_uncertain_dispatch_is_not_replayed_after_restart(tmp_path, dispatch_fails):
    path = tmp_path / "claims.sqlite3"
    store = Store(path)
    port = Port([observation("1", rewards=(reward(),)), observation("2")],
                failure=dispatch_fails, verified=False)
    result = FreeRewardExplorer().run(journal(port, store), 2, "5-Emmmmm")
    assert result.status == "ACTION_RESULT_UNCERTAIN"
    restarted = Store(path)
    retry = Port([observation("new", rewards=(reward(),))])
    result = FreeRewardExplorer().run(journal(retry, restarted), 2, "5-Emmmmm")
    assert result.status == "ACTION_RESULT_UNCERTAIN"
    assert not retry.actions
    assert len(restarted.reward_claims("installation", 2)) == 1


def test_wrong_task_account_blocks_real_port(tmp_path):
    store = Store(tmp_path / "claims.sqlite3")
    port = Port([observation("1", rewards=(reward(),))])
    result = FreeRewardExplorer().run(journal(port, store, run(store, index=7)), 2, "5-Emmmmm")
    assert result.status == "ACTION_RESULT_UNCERTAIN"
    assert not port.actions
    assert not store.reward_claims("installation", 7)
