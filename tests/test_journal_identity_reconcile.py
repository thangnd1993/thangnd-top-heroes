import json
from types import SimpleNamespace

import pytest

from top_heroes_auto.app.journal_identity_reconcile import reconcile
from top_heroes_auto.automation.vip_period import cycle_key


@pytest.fixture
def legacy(rig):
    m, process, store = rig
    task = store.create_task_run(m.namespace, "vip-reward", 7, "old display")
    before = dict(index=7, name="old display", adb_target="fixture-explicit", boot_id="original-boot")
    claim = store.reserve_reward_claim(
        task, "vip-daily", "old-period", json.dumps(before), not_dispatched=True
    )
    store.mark_reward_dispatch(claim, task)
    path = store.path.parent / "diagnostics/tasks/automation/original/7/vip/account-report.json"
    path.parent.mkdir(parents=True)
    report = dict(index=7, name="old display", task_run_id=task, claim_id=claim, before_evidence=before)
    path.write_text(json.dumps(report), encoding="utf-8")
    fleet_path = path.parents[2] / "fleet-report.json"
    fleet = dict(
        schema="instance-first-v1",
        targets=[dict(index=7, name="old display", protected=False, persistent_identity="fixture-disk-7")],
        accounts=[dict(index=7, flows={"vip": report})],
    )
    fleet_path.write_text(json.dumps(fleet), encoding="utf-8")
    store.finish_task_run(task, "ACTION_DISPATCHED_UNVERIFIED", report_path=str(path))
    with store.connect() as db:
        db.execute("UPDATE journal_identities SET stable_id='',state='AMBIGUOUS' WHERE claim_id=?", (claim,))
    return SimpleNamespace(
        m=m,
        process=process,
        store=store,
        task=task,
        claim=claim,
        path=path,
        fleet_path=fleet_path,
        fleet=fleet,
        report=report,
    )


def test_non_name_original_fleet_proof_binds_sidecar_only(legacy):
    x = legacy
    before = x.store.reward_claims(x.m.namespace, 7)
    x.process.listing = x.process.listing.replace("Farm-007", "new label")
    x.m.refresh()
    result = reconcile(x.m, x.claim)
    assert result["result"] == "IDENTITY_BOUND" and result["claim_status"] == "RESERVED"
    assert not result["claim_redispatched"]
    assert x.store.reward_claims(x.m.namespace, 7) == before
    assert json.loads(x.store.get(f"journal_identity_reconciliation:{x.claim}"))["sources"]
    with pytest.raises(ValueError, match="already attempted"):
        fresh = x.store.create_task_run(x.m.namespace, "vip", 7, "new label")
        x.store.reserve_reward_claim(fresh, "vip-daily", "old-period", "{}")
    assert reconcile(x.m, x.claim)["result"] == "ALREADY_BOUND"
    assert all(c[1] == "list2" for c in x.process.calls)


@pytest.mark.parametrize("corruption", [None, "disk", "claim", "shape", "concurrency"])
def test_original_phase6_report_requires_exact_claim_and_disk(legacy, corruption):
    x = legacy
    path = x.store.path.parent / "diagnostics/tasks/phase6-final/original/7/vip/account-report.json"
    path.parent.mkdir(parents=True)
    x.fleet.pop("schema")
    x.fleet.update(
        mode="random-test",
        max_concurrency=1,
        required_rewards=[
            "vip-upper-gift",
            "vip-daily",
            "ranking-chest",
            "shop-daily-gift",
            "shop-weekly-card-gift",
            "shop-permanent-privilege-gift",
            "shop-monthly-privilege-gift",
        ],
    )
    if corruption == "disk":
        x.fleet["targets"][0]["persistent_identity"] = "different-disk"
    if corruption == "claim":
        x.report["claim_id"] += 1
    if corruption == "shape":
        x.fleet["required_rewards"].pop()
    if corruption == "concurrency":
        x.fleet["max_concurrency"] = 2
    path.write_text(json.dumps(x.report), encoding="utf-8")
    (path.parents[2] / "fleet-report.json").write_text(json.dumps(x.fleet), encoding="utf-8")
    with x.store.connect() as db:
        db.execute("UPDATE task_runs SET report_path=? WHERE id=?", (str(path), x.task))
    original = x.store.reward_claims(x.m.namespace, 7)
    if corruption:
        with pytest.raises(ValueError):
            reconcile(x.m, x.claim)
    else:
        assert reconcile(x.m, x.claim)["result"] == "IDENTITY_BOUND"
    assert x.store.reward_claims(x.m.namespace, 7) == original
    assert all(c[1] == "list2" for c in x.process.calls)


@pytest.mark.parametrize("reward", ["vip-daily", "vip-upper-gift"])
@pytest.mark.parametrize("status", ["VERIFIED", "RESERVED"])
def test_binding_preserves_state_and_only_allows_distinct_supported_period(legacy, reward, status):
    x = legacy
    if reward == "vip-upper-gift":
        x.report["upper_gift"] = dict(claim_id=x.claim, before=x.report.pop("before_evidence"))
        x.report.pop("claim_id")
    with x.store.connect() as db:
        db.execute(
            "UPDATE reward_claims SET reward_id=?,status=?,reserved_at=? WHERE id=?",
            (reward, status, "2020-01-01T03:00:00+00:00", x.claim),
        )
    x.path.write_text(json.dumps(x.report), encoding="utf-8")
    x.fleet_path.write_text(json.dumps(x.fleet), encoding="utf-8")
    original = x.store.reward_claims(x.m.namespace, 7)
    assert reconcile(x.m, x.claim)["claim_status"] == status
    assert x.store.reward_claims(x.m.namespace, 7) == original
    task = x.store.create_task_run(x.m.namespace, "vip", 7, "renamed")
    with pytest.raises(ValueError, match="already attempted"):
        x.store.reserve_reward_claim(task, reward, "old-period", "{}")
    assert x.store.reserve_reward_claim(
        task,
        reward,
        cycle_key(reward),
        json.dumps({"persistent_identity": "fixture-disk-7"}),
        not_dispatched=True,
        vip_daily_period=True,
    )


@pytest.mark.parametrize(
    "corruption",
    ["disk", "duplicate", "claim", "before", "task", "source", "no_disk", "protected", "binding", "replaced"],
)
def test_incomplete_or_conflicting_proof_stays_locked(legacy, corruption):
    x = legacy
    if corruption == "disk":
        x.fleet["targets"][0]["persistent_identity"] = "another-disk"
    if corruption == "duplicate":
        x.fleet["targets"].append(dict(x.fleet["targets"][0]))
    if corruption == "claim":
        x.report["claim_id"] += 100
    if corruption == "before":
        x.report["before_evidence"]["boot_id"] = "other-boot"
    if corruption == "task":
        x.report["task_run_id"] += 100
    if corruption == "no_disk":
        x.fleet["targets"][0].pop("persistent_identity")
    if corruption == "protected":
        x.m.protect(7, True)
    if corruption == "binding":
        with x.store.connect() as db:
            db.execute("UPDATE journal_identities SET stable_id='foreign-disk' WHERE claim_id=?", (x.claim,))
    if corruption == "replaced":
        x.m.identity_reader = lambda console, index: "replacement" if index == 7 else f"fixture-disk-{index}"
        x.m.refresh()
    x.fleet_path.write_text(json.dumps(x.fleet), encoding="utf-8")
    if corruption != "source":
        x.path.write_text(json.dumps(x.report), encoding="utf-8")
    else:
        x.report["claim_id"] += 10
        x.path.write_text(json.dumps(x.report), encoding="utf-8")
    before = x.store.reward_claims(x.m.namespace, 7)
    with pytest.raises((ValueError, RuntimeError)):
        reconcile(x.m, x.claim)
    assert x.store.reward_claims(x.m.namespace, 7) == before
    assert x.store.get(f"journal_identity_reconciliation:{x.claim}") == ""
    assert all(c[1] == "list2" for c in x.process.calls)


@pytest.mark.parametrize("change", ["protected", "journal"])
def test_concurrent_change_after_identity_probe_aborts_binding(legacy, monkeypatch, change):
    x = legacy

    def probe(manager, index):
        with x.store.connect() as db:
            if change == "protected":
                db.execute(
                    "UPDATE instances SET selected=0,protected=1 WHERE namespace=? AND idx=7",
                    (x.m.namespace,),
                )
            else:
                db.execute(
                    "UPDATE reward_claims SET after_evidence='concurrent proof' WHERE id=?", (x.claim,)
                )
        return "fixture-disk-7"

    monkeypatch.setattr("top_heroes_auto.app.journal_identity_reconcile.persistent_identity", probe)
    with pytest.raises(ValueError):
        reconcile(x.m, x.claim)
    with x.store.connect() as db:
        assert db.execute(
            "SELECT stable_id,state FROM journal_identities WHERE claim_id=?", (x.claim,)
        ).fetchone() == ("", "AMBIGUOUS")
    assert not x.store.get(f"journal_identity_reconciliation:{x.claim}")
